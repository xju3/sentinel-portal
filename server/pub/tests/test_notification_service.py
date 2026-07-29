from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import mysql

from pub.models.diagnosis import (
    DiagnosisNotificationDelivery,
    DiagnosisNotificationDeliveryStatus,
)
from pub.services.notification.notification_service import (
    DiagnosisNotificationEvent,
    NotificationRecipient,
    NotificationRouteResolution,
    NotificationService,
)


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeExecuteResult:
    def __init__(self, rows=None, rowcount: int = 0):
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)

    def one_or_none(self):
        if not self._rows:
            return None
        if len(self._rows) != 1:
            raise AssertionError("Expected at most one row")
        return self._rows[0]

    def scalars(self):
        return FakeScalarResult(self._rows)


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.statements = []
        self.commit_calls = 0

    async def execute(self, stmt):
        self.statements.append(stmt)
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        response = self._responses.pop(0)
        if callable(response):
            response = response(stmt)
        return response

    async def commit(self):
        self.commit_calls += 1


def _event() -> DiagnosisNotificationEvent:
    return DiagnosisNotificationEvent.model_validate(
        {
            "event_id": str(uuid4()),
            "diagnosis_id": str(uuid4()),
            "report_id": str(uuid4()),
            "device_id": str(uuid4()),
            "sensor_sn": "SN-001",
            "overall_level": 3,
            "device_category_id": str(uuid4()),
            "process_device_id": str(uuid4()),
            "diagnosed_at": "2026-07-29T16:05:00+00:00",
        }
    )


def test_delivery_model_has_daily_unique_constraint():
    unique_constraints = [
        constraint
        for constraint in DiagnosisNotificationDelivery.__table__.constraints
        if getattr(constraint, "name", None) == "uq_diagnosis_notification_delivery_daily"
    ]
    assert len(unique_constraints) == 1
    constraint = unique_constraints[0]
    assert [column.name for column in constraint.columns] == [
        "device_id",
        "overall_level",
        "employee_id",
        "notification_date",
    ]


def test_parse_event_normalizes_beijing_notification_date():
    event = _event()

    assert event.diagnosed_at.isoformat() == "2026-07-29T16:05:00+00:00"
    assert event.notification_date == date(2026, 7, 30)


@pytest.mark.asyncio
async def test_route_resolution_prefers_current_device_relations():
    event = _event()
    current_category_id = uuid4()
    current_process_device_id = uuid4()
    session = FakeSession(
        [
            FakeExecuteResult(
                rows=[
                    SimpleNamespace(
                        device_category_id=current_category_id,
                        process_device_id=current_process_device_id,
                    )
                ]
            )
        ]
    )

    route = await NotificationService.resolve_route_ids(session, event)

    assert route.device_category_id == current_category_id
    assert route.process_device_id == current_process_device_id
    assert route.device_category_source == "device"
    assert route.process_device_source == "device"


@pytest.mark.asyncio
async def test_route_resolution_does_not_guess_ambiguous_process_device():
    event = _event()
    category_id = uuid4()
    session = FakeSession(
        [
            FakeExecuteResult(
                rows=[
                    SimpleNamespace(
                        device_category_id=category_id,
                        process_device_id=uuid4(),
                    ),
                    SimpleNamespace(
                        device_category_id=category_id,
                        process_device_id=uuid4(),
                    ),
                ]
            )
        ]
    )

    route = await NotificationService.resolve_route_ids(session, event)

    assert route.device_category_id == category_id
    assert route.process_device_id is None
    assert route.process_device_source == "ambiguous"


@pytest.mark.asyncio
async def test_list_recipients_merges_employee_ids(monkeypatch):
    event = _event()
    employee_a = uuid4()
    employee_b = uuid4()
    employee_c = uuid4()

    async def fake_resolve_route_ids(*_args, **_kwargs):
        return NotificationRouteResolution(
            device_category_id=uuid4(),
            process_device_id=uuid4(),
            device_category_source="device",
            process_device_source="device",
        )

    async def fake_category_rows(*_args, **_kwargs):
        return [
            SimpleNamespace(id=employee_a, name="Alice", wx_user_id="wx-alice"),
            SimpleNamespace(id=employee_b, name="Bob", wx_user_id="wx-bob"),
        ]

    async def fake_process_rows(*_args, **_kwargs):
        return [
            SimpleNamespace(id=employee_a, name="Alice", wx_user_id="wx-alice"),
            SimpleNamespace(id=employee_c, name="Cindy", wx_user_id="wx-cindy"),
        ]

    monkeypatch.setattr(NotificationService, "resolve_route_ids", fake_resolve_route_ids)
    monkeypatch.setattr(
        NotificationService,
        "_recipient_rows_for_device_category",
        fake_category_rows,
    )
    monkeypatch.setattr(
        NotificationService,
        "_recipient_rows_for_process_device",
        fake_process_rows,
    )

    recipients = await NotificationService.list_recipients(session=None, event=event)
    recipient_map = {recipient.employee_id: recipient for recipient in recipients}

    assert set(recipient_map) == {employee_a, employee_b, employee_c}
    assert recipient_map[employee_a].route_sources == (
        "device_category",
        "process_device",
    )
    assert recipient_map[employee_b].route_sources == ("device_category",)
    assert recipient_map[employee_c].route_sources == ("process_device",)


@pytest.mark.asyncio
async def test_prepare_delivery_targets_keeps_failed_rows_out_of_send_queue(monkeypatch):
    event = _event()
    employee_pending = uuid4()
    employee_failed = uuid4()

    async def fake_resolve_route_ids(*_args, **_kwargs):
        return NotificationRouteResolution(
            device_category_id=uuid4(),
            process_device_id=uuid4(),
            device_category_source="device",
            process_device_source="event",
        )

    async def fake_list_recipients(*_args, **_kwargs):
        return [
            NotificationRecipient(
                employee_id=employee_pending,
                employee_name="Pending User",
                wx_user_id="wx-pending",
                route_sources=("device_category",),
            ),
            NotificationRecipient(
                employee_id=employee_failed,
                employee_name="Failed User",
                wx_user_id="wx-failed",
                route_sources=("process_device",),
            ),
        ]

    monkeypatch.setattr(NotificationService, "resolve_route_ids", fake_resolve_route_ids)
    monkeypatch.setattr(NotificationService, "list_recipients", fake_list_recipients)

    responses = [
        FakeExecuteResult(rowcount=2),
        FakeExecuteResult(
            rows=[
                SimpleNamespace(
                    id=uuid4(),
                    employee_id=employee_pending,
                    wx_user_id="wx-pending",
                    status=int(DiagnosisNotificationDeliveryStatus.PENDING),
                ),
                SimpleNamespace(
                    id=uuid4(),
                    employee_id=employee_failed,
                    wx_user_id="wx-failed",
                    status=int(DiagnosisNotificationDeliveryStatus.FAILED),
                ),
            ]
        ),
    ]
    session = FakeSession(responses)

    targets = await NotificationService.prepare_delivery_targets(session, event)
    target_map = {target.employee_id: target for target in targets}

    assert session.commit_calls == 1
    assert target_map[employee_pending].should_send is True
    assert target_map[employee_pending].status == DiagnosisNotificationDeliveryStatus.PENDING
    assert target_map[employee_failed].should_send is False
    assert target_map[employee_failed].status == DiagnosisNotificationDeliveryStatus.FAILED
    assert target_map[employee_failed].skip_reason == "failed"
    assert session.statements[0].table.name == "diagnosis_notification_delivery"


@pytest.mark.asyncio
async def test_mark_delivery_sending_guards_pending_state():
    delivery_id = uuid4()
    session = FakeSession([FakeExecuteResult(rowcount=1)])

    claimed = await NotificationService.mark_delivery_sending(session, delivery_id)

    compiled = str(
        session.statements[0].compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert claimed is True
    assert "UPDATE diagnosis_notification_delivery" in compiled
    assert "status=0" in compiled or "status = 0" in compiled
    assert "WHERE diagnosis_notification_delivery.id" in compiled
    assert session.commit_calls == 1

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
    DiagnosisNotificationFaultEvent,
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

    async def scalar(self, stmt):
        self.statements.append(stmt)
        if not self._responses:
            raise AssertionError("Unexpected scalar call")
        return self._responses.pop(0)


def _event(
    *,
    fault_type: str = "legacy_aggregate",
    fault_level: int = 3,
) -> DiagnosisNotificationFaultEvent:
    return DiagnosisNotificationFaultEvent.model_validate(
        {
            "source_schema_version": 1 if fault_type == "legacy_aggregate" else 2,
            "event_id": str(uuid4()),
            "diagnosis_id": str(uuid4()),
            "report_id": str(uuid4()),
            "device_id": str(uuid4()),
            "sensor_sn": "SN-001",
            "fault_type": fault_type,
            "fault_level": fault_level,
            "overall_level": fault_level if fault_type == "legacy_aggregate" else None,
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
        "fault_type",
        "fault_level",
        "employee_id",
        "notification_date",
    ]


def test_parse_event_normalizes_beijing_notification_date():
    event = _event()

    assert event.diagnosed_at.isoformat() == "2026-07-29T16:05:00+00:00"
    assert event.notification_date == date(2026, 7, 30)


def test_parse_event_accepts_bearing_fault():
    event = NotificationService.parse_event(
        {
            "schema_version": 2,
            "event_id": str(uuid4()),
            "diagnosis_id": str(uuid4()),
            "report_id": str(uuid4()),
            "device_id": str(uuid4()),
            "sensor_sn": "SN-001",
            "diagnosed_at": "2026-07-30T00:00:00Z",
            "faults": [
                {
                    "fault_type": "bearing_bpfi",
                    "fault_level": 2,
                }
            ],
        }
    )

    assert event.fault_events[0].fault_type == "bearing_bpfi"
    assert event.fault_events[0].fault_label == "轴承内圈"


@pytest.mark.asyncio
async def test_bearing_notification_timing_policy_belongs_to_notification_service():
    attention = _event(fault_type="bearing_bpfi", fault_level=2)

    assert not await NotificationService.should_notify_fault(
        FakeSession([0]),
        attention,
        confirmation_count=2,
        window_hours=3,
        immediate_level=3,
    )
    assert await NotificationService.should_notify_fault(
        FakeSession([1]),
        attention,
        confirmation_count=2,
        window_hours=3,
        immediate_level=3,
    )
    assert await NotificationService.should_notify_fault(
        FakeSession([]),
        _event(fault_type="bearing_bpfi", fault_level=3),
        confirmation_count=2,
        window_hours=3,
        immediate_level=3,
    )


def test_parse_event_dispatches_v1_and_v2():
    v1 = NotificationService.parse_event(
        {
            "event_id": str(uuid4()),
            "diagnosis_id": str(uuid4()),
            "report_id": str(uuid4()),
            "device_id": str(uuid4()),
            "sensor_sn": "SN-001",
            "overall_level": 3,
            "diagnosed_at": "2026-07-29T16:05:00+00:00",
        }
    )
    v2 = NotificationService.parse_event(
        {
            "schema_version": 2,
            "event_id": str(uuid4()),
            "diagnosis_id": str(uuid4()),
            "report_id": str(uuid4()),
            "device_id": str(uuid4()),
            "sensor_sn": "SN-001",
            "diagnosed_at": "2026-07-29T16:05:00+00:00",
            "faults": [
                {
                    "diagnosis_item_id": str(uuid4()),
                    "fault_type": "temperature",
                    "fault_level": 2,
                },
                {
                    "diagnosis_item_id": str(uuid4()),
                    "fault_type": "vibration",
                    "fault_level": 3,
                },
            ],
        }
    )

    assert v1.schema_version == 1
    assert [fault.fault_type for fault in v1.expanded_faults()] == ["legacy_aggregate"]
    assert v2.schema_version == 2
    assert [fault.fault_type for fault in v2.expanded_faults()] == [
        "temperature",
        "vibration",
    ]


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
async def test_route_resolution_keeps_all_process_devices():
    event = _event()
    category_id = uuid4()
    process_device_a = uuid4()
    process_device_b = uuid4()
    session = FakeSession(
        [
            FakeExecuteResult(
                rows=[
                    SimpleNamespace(
                        device_category_id=category_id,
                        process_device_id=process_device_a,
                    ),
                    SimpleNamespace(
                        device_category_id=category_id,
                        process_device_id=process_device_b,
                    ),
                ]
            )
        ]
    )

    route = await NotificationService.resolve_route_ids(session, event)

    assert route.device_category_id == category_id
    assert route.process_device_id is None
    assert set(route.process_device_ids) == {process_device_a, process_device_b}
    assert route.process_device_source == "device"


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
async def test_list_recipients_reads_all_process_device_groups(monkeypatch):
    event = _event()
    process_device_a = uuid4()
    process_device_b = uuid4()
    employee_a = uuid4()
    employee_b = uuid4()
    queried_process_devices = []

    async def fake_resolve_route_ids(*_args, **_kwargs):
        return NotificationRouteResolution(
            process_device_ids=(process_device_a, process_device_b),
            process_device_source="device",
        )

    async def fake_process_rows(_session, process_device_id):
        queried_process_devices.append(process_device_id)
        employee_id = employee_a if process_device_id == process_device_a else employee_b
        return [
            SimpleNamespace(
                id=employee_id,
                name=str(employee_id),
                wx_user_id=f"wx-{employee_id}",
            )
        ]

    monkeypatch.setattr(NotificationService, "resolve_route_ids", fake_resolve_route_ids)
    monkeypatch.setattr(
        NotificationService,
        "_recipient_rows_for_process_device",
        fake_process_rows,
    )

    recipients = await NotificationService.list_recipients(session=None, event=event)

    assert set(queried_process_devices) == {process_device_a, process_device_b}
    assert {recipient.employee_id for recipient in recipients} == {employee_a, employee_b}


@pytest.mark.asyncio
async def test_prepare_delivery_targets_retries_failed_rows(monkeypatch):
    event = _event(fault_type="vibration")
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
        FakeExecuteResult(rows=[]),
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
                    attempt_count=1,
                    next_attempt_at=None,
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
    assert target_map[employee_failed].should_send is True
    assert target_map[employee_failed].status == DiagnosisNotificationDeliveryStatus.FAILED
    assert target_map[employee_failed].skip_reason is None
    insert_stmt = next(
        stmt for stmt in session.statements if hasattr(stmt, "table")
    )
    assert insert_stmt.table.name == "notification_delivery"


@pytest.mark.asyncio
async def test_prepare_delivery_targets_suppresses_v2_when_legacy_row_exists(monkeypatch):
    event = _event(fault_type="temperature")
    employee_id = uuid4()
    legacy_delivery_id = uuid4()

    async def fake_resolve_route_ids(*_args, **_kwargs):
        return NotificationRouteResolution(
            device_category_id=uuid4(),
            process_device_id=uuid4(),
            device_category_source="device",
            process_device_source="device",
        )

    async def fake_list_recipients(*_args, **_kwargs):
        return [
            NotificationRecipient(
                employee_id=employee_id,
                employee_name="Legacy User",
                wx_user_id="wx-legacy",
                route_sources=("device_category",),
            )
        ]

    monkeypatch.setattr(NotificationService, "resolve_route_ids", fake_resolve_route_ids)
    monkeypatch.setattr(NotificationService, "list_recipients", fake_list_recipients)

    session = FakeSession(
        [
            FakeExecuteResult(
                rows=[
                    SimpleNamespace(
                        id=legacy_delivery_id,
                        employee_id=employee_id,
                        wx_user_id="wx-legacy",
                        status=int(DiagnosisNotificationDeliveryStatus.SENT),
                    )
                ]
            )
        ]
    )

    targets = await NotificationService.prepare_delivery_targets(session, event)

    assert session.commit_calls == 0
    assert len(targets) == 1
    assert targets[0].delivery_id == legacy_delivery_id
    assert targets[0].should_send is False
    assert targets[0].skip_reason == "legacy_aggregate_suppressed"


@pytest.mark.asyncio
async def test_mark_delivery_sending_claims_pending_or_failed_state():
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
    assert "UPDATE notification_delivery" in compiled
    assert "status IN (0, 3)" in compiled or "status IN (__[POSTCOMPILE_status_1])" in compiled
    assert "attempt_count < 3" in compiled
    assert "WHERE notification_delivery.id" in compiled
    assert session.commit_calls == 1

from types import SimpleNamespace
from uuid import uuid4

import pytest

from pub.services.customer.location_service import LocationService


class _FakeSession:
    def __init__(self):
        self.commit_count = 0
        self.refresh_count = 0
        self.deleted = []

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _obj):
        self.refresh_count += 1

    async def delete(self, obj):
        self.deleted.append(obj)


class _ScalarResult:
    def scalar_one_or_none(self):
        return None


class _CaptureSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _ScalarResult()


@pytest.mark.asyncio
async def test_disabling_location_keeps_the_referenced_row():
    session = _FakeSession()
    location = SimpleNamespace(id=uuid4(), status=1)

    result = await LocationService.disable_location(session, location)

    assert result is location
    assert location.status == 0
    assert session.deleted == []
    assert session.commit_count == 1
    assert session.refresh_count == 1


@pytest.mark.asyncio
async def test_active_location_validation_rejects_disabled_locations():
    session = _CaptureSession()

    await LocationService.is_tenant_location(
        session,
        tenant_id=uuid4(),
        location_id=uuid4(),
        active_only=True,
    )

    assert "location.status" in str(session.statement)

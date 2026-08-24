import inspect
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.routers import customers, devices, thresholds

from pub.services.customer.area_service import AreaService
from pub.services.customer.health_check_freq_service import HealthCheckFreqService
from pub.services.customer.iso_standard_service import IsoStandardService
from pub.services.customer.location_service import LocationService
from pub.services.customer.supplier_service import SupplierService
from pub.services.customer.tenant_service import TenantService
from pub.services.device.bearing_service import BearingService
from pub.services.device.device_category_service import DeviceCategoryService
from pub.services.device.device_inst_service import DeviceInstService
from pub.services.sensor.sensor_monitoring_service import SensorMonitoringService
from pub.services.sensor.sensor_threshold_service import SensorThresholdService


@pytest.mark.parametrize(
    "route",
    [
        customers.list_suppliers,
        customers.list_areas,
        customers.list_locations,
        customers.list_health_check_freqs,
        customers.list_iso_standards,
        devices.list_device_categories,
        devices.list_bearings,
        devices.list_device_specs,
        devices.list_grouped_device_specs,
        devices.list_device_insts,
        devices.list_sensor_monitorings,
        thresholds.list_sensor_thresholds,
    ],
)
def test_management_list_routes_default_to_twenty(route):
    limit = inspect.signature(route).parameters["limit"].default
    assert limit.default == 20


def _count_result(total: int) -> Mock:
    result = Mock()
    result.scalar.return_value = total
    return result


def _rows_result(rows: list) -> Mock:
    result = Mock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_call", "expected_fragments"),
    [
        (
            lambda session, tenant_id: TenantService.get_tenants(
                session,
                20,
                20,
                code="acme",
                name="factory",
                active=True,
                email="ops@example.com",
                region_id="330100",
            ),
            (
                "lower(tenant.code)",
                "lower(tenant.name)",
                "tenant.active",
                "lower(tenant.email)",
                "tenant.region_id",
                "LIMIT",
            ),
        ),
        (
            lambda session, tenant_id: SupplierService.get_suppliers(
                session, tenant_id, 20, 20, keyword="acme"
            ),
            ("supplier.tenant_id", "lower(supplier.name)", "LIMIT"),
        ),
        (
            lambda session, tenant_id: AreaService.get_areas(
                session, tenant_id, 20, 20, keyword="plant"
            ),
            ("area.tenant_id", "lower(area.name)", "LIMIT"),
        ),
        (
            lambda session, tenant_id: LocationService.get_locations(
                session,
                tenant_id,
                20,
                20,
                keyword="motor",
                bearing_only=True,
                active_only=True,
            ),
            (
                "location.tenant_id",
                "lower(location.name)",
                "location.is_bearing_point",
                "location.status",
                "LIMIT",
            ),
        ),
        (
            lambda session, tenant_id: IsoStandardService.get_iso_standards(
                session, tenant_id, 20, 20, keyword="20816"
            ),
            ("iso_standard.tenant_id", "lower(iso_standard.code)", "LIMIT"),
        ),
        (
            lambda session, tenant_id: HealthCheckFreqService.get_health_check_freqs(
                session, tenant_id, 20, 20, status=True
            ),
            ("health_check_freq.tenant_id", "health_check_freq.status", "LIMIT"),
        ),
        (
            lambda session, tenant_id: BearingService.list_models(
                session, tenant_id, 20, 20, keyword="skf"
            ),
            ("bearing_model.tenant_id", "lower(bearing_model.brand)", "LIMIT"),
        ),
        (
            lambda session, tenant_id: DeviceCategoryService.get_device_categories(
                session, tenant_id, 20, 20, keyword="pump"
            ),
            (
                "device_category.tenant_id",
                "lower(device_category.name)",
                "LIMIT",
            ),
        ),
        (
            lambda session, tenant_id: DeviceInstService.get_tenant_device_insts_paged(
                session, tenant_id, 2, 20, keyword="motor"
            ),
            (
                "device_category.tenant_id",
                "lower(device_inst.name)",
                "LIMIT",
            ),
        ),
        (
            lambda session, tenant_id: SensorMonitoringService.get_all_by_tenant(
                session, tenant_id, 20, 20, status=1
            ),
            (
                "device_category.tenant_id",
                "sensor_monitoring.status",
                "LIMIT",
            ),
        ),
        (
            lambda session, tenant_id: SensorThresholdService.get_by_tenant(
                session, tenant_id, 20, 20, code="vib", metric=2
            ),
            (
                "sensor_threshold.tenant_id",
                "lower(sensor_threshold.code)",
                "sensor_threshold.metric",
                "LIMIT",
            ),
        ),
    ],
)
async def test_list_services_filter_before_pagination_and_return_total(
    service_call, expected_fragments
):
    tenant_id = uuid4()
    rows = [Mock(id=uuid4())]
    session = Mock()
    session.execute = AsyncMock(
        side_effect=[_count_result(41), _rows_result(rows)]
    )

    items, total = await service_call(session, tenant_id)

    assert items == rows
    assert total == 41
    count_sql = str(session.execute.await_args_list[0].args[0]).lower()
    page_sql = str(session.execute.await_args_list[1].args[0]).lower()
    assert " limit " not in count_sql
    assert " offset " not in count_sql
    for fragment in expected_fragments:
        assert fragment.lower() in page_sql

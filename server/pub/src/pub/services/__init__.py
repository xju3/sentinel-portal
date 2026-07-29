"""
Business logic services
"""

from .customer.region_service import RegionService
from .customer.tenant_service import TenantService
from .customer.tenant_sensor_service import TenantSensorService
from .customer.supplier_service import SupplierService
from .customer.contact_service import ContactService
from .customer.account_service import AccountService
from .customer.area_service import AreaService
from .customer.location_service import LocationService
from .customer.health_check_freq_service import HealthCheckFreqService
from .customer.auth_service import AuthService
from .customer.iso_standard_service import IsoStandardService

from .device.device_category_service import DeviceCategoryService
from .device.device_spec_service import DeviceSpecService
from .device.device_inst_service import DeviceInstService
from .sensor.sensor_type_service import SensorTypeService
from .sensor.sensor_db_service import SensorDbService
from .sensor.sim_card_service import SimCardService
from .sensor.sensor_batch_service import SensorBatchService
from .sensor.sensor_threshold_service import SensorThresholdService
from .sensor.sensor_service import SensorService
from .sensor.sensor_config_service import SensorConfigService
from .sensor.sensor_monitoring_service import *
from .device.process_service import (
    ProcessService,
    ProcessItemService,
    ProcessDeviceService,
    ProcessDeviceItemService,
)
from .sensor.firmware_service import SensorFirmwareService
from .sensor.communication_service import SensorCommunicationService
from .sensor.sensor_task_service import *

from .diagnosis.diagnosis_record_service import DiagnosisRecordService
from .diagnosis.device_health_archive_service import DeviceHealthArchiveService
# from .diagnosis.diagnosis_result_service import DiagnosisResultService
# from .diagnosis.patrol_diagnosis_record_service import PatrolDiagnosisRecordService
from .diagnosis.diagnosis_context_service import DiagnosisContextService
from .diagnosis.quick_history_cache import *

from .dashboard.dashboard_health_service import DashboardHealthService
from .dashboard.dashboard_service import DashboardService

from .notification.notification_service import NotificationService
from .wx.wx_service import WxService
from .dispatch.quick_dispatch_service import *
from .config.config_service import *
from .common.crud_factory import *
from .dependencies import *

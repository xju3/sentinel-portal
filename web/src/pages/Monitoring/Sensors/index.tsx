import BusinessPlaceholder from '@/components/BusinessPlaceholder';

const MonitoringSensorsPage = () => (
  <BusinessPlaceholder
    title="传感器"
    description="仅展示当前租户已分配的传感器数据，不管理传感器型号。"
    model="tenant_sensor"
    apiPath="/api/v1/tenant-sensors"
  />
);

export default MonitoringSensorsPage;

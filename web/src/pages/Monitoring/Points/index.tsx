import BusinessPlaceholder from '@/components/BusinessPlaceholder';

const MonitoringPointsPage = () => (
  <BusinessPlaceholder
    title="测点设置"
    description="将传感器绑定至设备实例和故障测点，记录方向与状态。"
    model="sensor_monitoring"
    apiPath="/api/v1/sensor-monitorings"
  />
);

export default MonitoringPointsPage;

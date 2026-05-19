import BusinessPlaceholder from '@/components/BusinessPlaceholder';

const MonitoringPointsPage = () => (
  <BusinessPlaceholder
    title="测点设置"
    description="将传感器绑定至工段实例中的具体设备测点。"
    model="device_inst_tag"
    apiPath="/api/v1/device-inst-tags"
  />
);

export default MonitoringPointsPage;

import BusinessPlaceholder from '@/components/BusinessPlaceholder';

const DeviceSpecPage = () => (
  <BusinessPlaceholder
    title="设备规格"
    description="定义设备规格（同类型设备共享规格参数），用于后续批量实例化。"
    model="device_spec"
    apiPath="/api/v1/device-specs"
  />
);

export default DeviceSpecPage;

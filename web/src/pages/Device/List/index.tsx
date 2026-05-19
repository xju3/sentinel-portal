import BusinessPlaceholder from '@/components/BusinessPlaceholder';

const DeviceListPage = () => (
  <BusinessPlaceholder
    title="设备列表"
    description="管理设备实例（唯一编码、SN、状态等），来源于设备规格。"
    model="device_inst"
    apiPath="/api/v1/device-insts"
  />
);

export default DeviceListPage;

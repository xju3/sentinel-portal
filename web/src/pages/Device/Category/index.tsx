import BusinessPlaceholder from '@/components/BusinessPlaceholder';

const DeviceCategoryPage = () => (
  <BusinessPlaceholder
    title="设备分类"
    description="管理设备分类，并可在分类中选择对应 ISO 标准作为可选项。"
    model="device_category"
    apiPath="/api/v1/device-categories"
  />
);

export default DeviceCategoryPage;

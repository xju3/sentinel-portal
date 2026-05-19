import BusinessPlaceholder from '@/components/BusinessPlaceholder';

const ProcessTemplatePage = () => (
  <BusinessPlaceholder
    title="工段模板"
    description="定义工段模板及其包含的设备组合，不直接对应具体现场实例。"
    model="device_combo_spec + device_combo_spec_item"
    apiPath="/api/v1/device-combo-specs"
  />
);

export default ProcessTemplatePage;

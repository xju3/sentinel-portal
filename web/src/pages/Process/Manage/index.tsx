import BusinessPlaceholder from '@/components/BusinessPlaceholder';

const ProcessManagePage = () => (
  <BusinessPlaceholder
    title="工段管理"
    description="管理工段实例化数据，基于工段模板创建并维护现场工段实例。"
    model="device_combo_inst + device_combo_inst_item"
    apiPath="/api/v1/device-combo-insts"
  />
);

export default ProcessManagePage;

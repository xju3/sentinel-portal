import { useEffect, useRef, useState } from 'react';
import {
  ActionType,
  ModalForm,
  PageContainer,
  ProColumns,
  ProForm,
  ProFormDigit,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Modal, Popconfirm, Space, Table, Tag, Tabs, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from '@umijs/max';
import EntityPicker from '@/components/EntityPicker';
import { BearingModel, queryBearings } from '@/services/bearing';
import { Location, queryLocations } from '@/services/location';
import { DeviceCategory, listAllDeviceCategories, queryDeviceCategories } from '@/services/deviceCategory';
import {
  DeviceSpec,
  DeviceSpecBearingBinding,
  DeviceSpecBearingBindingPayload,
  DeviceSpecPayload,
  createDeviceSpec,
  deleteDeviceSpec,
  getDeviceSpecBearingBindings,
  queryDeviceSpecs,
  updateDeviceSpec,
  updateDeviceSpecBearingBindings,
} from '@/services/deviceSpec';
import { Supplier, querySuppliers } from '@/services/supplier';
import { renderRefSafeTableOptions } from '@/utils/proTableOptions';

type CategoryTreeRow = DeviceCategory & { children?: CategoryTreeRow[] };
type DeviceSpecFormValues = DeviceSpecPayload;
type BearingBindingFormValues = DeviceSpecBearingBindingPayload;
type BearingBindingDraft = DeviceSpecBearingBinding & { draftKey: string };

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const buildCategoryTree = (rows: DeviceCategory[]): CategoryTreeRow[] => {
  const nodeMap = new Map<string, CategoryTreeRow>();
  rows.forEach((item) => nodeMap.set(item.id, { ...item, children: [] }));
  const roots: CategoryTreeRow[] = [];
  rows.forEach((item) => {
    const node = nodeMap.get(item.id);
    if (!node) return;
    if (item.parent_id && nodeMap.has(item.parent_id)) {
      nodeMap.get(item.parent_id)?.children?.push(node);
      return;
    }
    roots.push(node);
  });
  return roots;
};

const DeviceSpecPage = () => {
  const navigate = useNavigate();
  const actionRef = useRef<ActionType>();
  const formRef = useRef<any>();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<DeviceSpec | null>(null);
  const [categoryTreeData, setCategoryTreeData] = useState<CategoryTreeRow[]>([]);
  const [bindingModalOpen, setBindingModalOpen] = useState(false);
  const [bindingEditorOpen, setBindingEditorOpen] = useState(false);
  const [bindingSpec, setBindingSpec] = useState<DeviceSpec | null>(null);
  const [bindingLoading, setBindingLoading] = useState(false);
  const [bindingSaving, setBindingSaving] = useState(false);
  const [bindings, setBindings] = useState<BearingBindingDraft[]>([]);
  const [editingBindingIndex, setEditingBindingIndex] = useState<number | null>(null);
  const [selectedBearing, setSelectedBearing] = useState<BearingModel | undefined>();
  const [selectedLocation, setSelectedLocation] = useState<Pick<Location, 'id' | 'name'> | undefined>();

  useEffect(() => {
    if (!modalOpen || categoryTreeData.length > 0) {
      return;
    }
    void listAllDeviceCategories()
      .then((rows) => setCategoryTreeData(buildCategoryTree(rows)))
      .catch(() => undefined);
  }, [categoryTreeData.length, modalOpen]);

  const columns: ProColumns<DeviceSpec>[] = [
    { title: '序号', valueType: 'indexBorder', width: 68, hideInSearch: true, fixed: 'left' },
    { title: '名称', dataIndex: 'name', width: 180, sorter: true },
    { title: '型号', dataIndex: 'model', width: 120, sorter: true },
    { title: '品牌', dataIndex: 'brand', width: 120, sorter: true },
    { title: '电压', dataIndex: 'voltage', width: 90, valueType: 'digit', sorter: true },
    { title: '转速', dataIndex: 'rpm', width: 90, valueType: 'digit', sorter: true },
    {
      title: '分类',
      dataIndex: 'device_category_id',
      hideInSearch: true,
      render: (_, row) => row.device_category?.name || '-',
    },
    {
      title: '供应商',
      dataIndex: 'supplier_id',
      hideInSearch: true,
      render: (_, row) => row.supplier?.name || '-',
    },
    {
      title: '备注',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '性能标准',
      dataIndex: 'remark',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.remark || '-',
    },
    {
      title: '操作',
      valueType: 'option',
      width: 180,
      fixed: 'right',
      render: (_, row) => (
        <Space size="small">
          <a
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            title="确认删除该设备规格吗？"
            onConfirm={async () => {
              try {
                await deleteDeviceSpec(row.id);
                message.success('删除成功');
                actionRef.current?.reload();
              } catch (error) {
                message.error(toErrorMessage(error));
              }
            }}
          >
            <a style={{ color: '#ff4d4f' }}>删除</a>
          </Popconfirm>
          <a onClick={() => void openBindingModal(row)}>轴承</a>
          {(row.process_device_count || 0) > 0 && (
            <a
              onClick={() => {
                const group = row.process_devices?.[0]?.id;
                const suffix = group ? `?group=${encodeURIComponent(group)}` : '';
                navigate(`/device/specs/${row.id}/comparison${suffix}`);
              }}
            >
              对比
            </a>
          )}
        </Space>
      ),
    },
  ];

  const openBindingModal = async (spec: DeviceSpec) => {
    setBindingSpec(spec);
    setBindingModalOpen(true);
    setBindingLoading(true);
    try {
      const rows: DeviceSpecBearingBinding[] = await getDeviceSpecBearingBindings(spec.id);
      setBindings(
        rows.map((item, index) => ({
          ...item,
          draftKey: item.id || `${item.location_id}-${item.bearing_id}-${index}`,
        })),
      );
    } catch (error) {
      message.error(toErrorMessage(error));
      setBindingModalOpen(false);
      setBindingSpec(null);
    } finally {
      setBindingLoading(false);
    }
  };

  const bindingColumns: ColumnsType<BearingBindingDraft> = [
    { title: '安装位置', dataIndex: 'location_id', render: (_, row) => row.location?.name || row.location_id },
    {
      title: '轴承型号',
      render: (_, row) => (row.bearing ? `${row.bearing.brand} / ${row.bearing.model}` : row.bearing_id),
    },
    { title: '轴转速比', dataIndex: 'shaft_speed_ratio', width: 110 },
    {
      title: '诊断状态',
      dataIndex: 'enabled',
      width: 100,
      render: (_, row) => (row.enabled ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '操作',
      width: 130,
      render: (_, row, index) => (
        <Space>
          <a
            onClick={() => {
              setEditingBindingIndex(index);
              setSelectedBearing(row.bearing);
              setSelectedLocation(row.location);
              setBindingEditorOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            title="确认移除该位置的轴承配置吗？"
            onConfirm={() => setBindings((current) => current.filter((item) => item.draftKey !== row.draftKey))}
          >
            <a style={{ color: '#ff4d4f' }}>移除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="设备规格">
      <ProTable<DeviceSpec>
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        request={queryDeviceSpecs}
        search={{ labelWidth: 'auto' }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        optionsRender={renderRefSafeTableOptions}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            新建设备规格
          </Button>,
        ]}
      />

      <ModalForm<DeviceSpecFormValues>
        title={editing ? '编辑设备规格' : '新建设备规格'}
        formRef={formRef}
        open={modalOpen}
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setModalOpen(false);
            setEditing(null);
          },
        }}
        submitter={{ submitButtonProps: { loading: saving }, searchConfig: { submitText: '保存' } }}
        initialValues={
          editing
            ? {
                name: editing.name,
                model: editing.model,
                description: editing.description,
                brand: editing.brand,
                voltage: editing.voltage,
                rpm: editing.rpm,
                supplier_id: editing.supplier_id,
                device_category_id: editing.device_category_id,
                remark: editing.remark,
              }
            : { voltage: 0, rpm: 0 }
        }
        onFinish={async (values) => {
          const payload: DeviceSpecPayload = {
            name: values.name.trim(),
            model: values.model.trim(),
            description: values.description?.trim() || undefined,
            brand: values.brand.trim(),
            voltage: values.voltage,
            rpm: values.rpm,
            supplier_id: values.supplier_id,
            device_category_id: values.device_category_id,
            remark: values.remark?.trim() || undefined,
          };
          setSaving(true);
          try {
            if (editing) {
              await updateDeviceSpec(editing.id, payload);
            } else {
              await createDeviceSpec(payload);
            }
            message.success('保存成功');
            setModalOpen(false);
            setEditing(null);
            actionRef.current?.reload();
            return true;
          } catch (error) {
            message.error(toErrorMessage(error));
            return false;
          } finally {
            setSaving(false);
          }
        }}
      >
        <Tabs
          defaultActiveKey="1"
          items={[
            {
              key: '1',
              label: '基本信息',
              children: (
                <>
                  <ProFormText name="name" label="名称" rules={[{ required: true, message: '请输入规格名称' }]} />
                  <ProForm.Item name="device_category_id" label="设备分类" rules={[{ required: true, message: '请选择设备分类' }]}>
                    <EntityPicker<DeviceCategory>
                      placeholder="请点击选择设备分类"
                      modalTitle="选择设备分类"
                      triggerText="选择"
                      valueLabel={editing?.device_category?.name}
                      columns={[
                        { title: '分类名称', dataIndex: 'name' },
                        { title: '描述', dataIndex: 'description', render: (_, row) => row.description || '-' },
                      ]}
                      getRecordLabel={(record) => record.name}
                      fetcher={async ({ current, pageSize, keyword }) => {
                        const result = await queryDeviceCategories({ current, pageSize, keyword });
                        return { items: result.data, total: result.total };
                      }}
                      treeData={categoryTreeData}
                    />
                  </ProForm.Item>
                  <ProForm.Item name="supplier_id" label="供应商" rules={[{ required: true, message: '请选择供应商' }]}>
                    <EntityPicker<Supplier>
                      placeholder="请点击选择供应商"
                      modalTitle="选择供应商"
                      triggerText="选择"
                      valueLabel={editing?.supplier?.name}
                      columns={[
                        { title: '名称', dataIndex: 'name' },
                        { title: '品牌', dataIndex: 'brand' },
                        { title: '联系方式', dataIndex: 'contact_info', render: (_, row) => row.contact_info || '-' },
                      ]}
                      getRecordLabel={(record) => record.name}
                      fetcher={async ({ current, pageSize, keyword }) => {
                        const result = await querySuppliers({ current, pageSize, keyword });
                        return { items: result.data, total: result.total };
                      }}
                      onRecordChange={(record) => formRef.current?.setFieldsValue({ brand: record?.brand || '' })}
                    />
                  </ProForm.Item>
                  <ProFormDigit name="rpm" label="转速(RPM)" min={0} fieldProps={{ precision: 0 }} rules={[{ required: true, message: '请输入转速' }]} />
                  <ProFormDigit name="voltage" label="电压(V)" min={0} fieldProps={{ precision: 2 }} rules={[{ required: true, message: '请输入电压' }]} />
                  <ProFormText name="model" label="型号" />
                  <ProFormText name="brand" label="品牌" fieldProps={{ readOnly: true }} />
                  <ProFormText name="description" label="备注" />
                </>
              ),
            },
            {
              key: '2',
              label: '电气性能标准',
              children: <ProFormTextArea name="remark" label="" fieldProps={{ rows: 14 }} placeholder="请输入该设备规格的电气性能标准" />,
            },
          ]}
        />
      </ModalForm>

      <Modal
        title={bindingSpec ? `${bindingSpec.name} - 轴承配置` : '轴承配置'}
        open={bindingModalOpen}
        width={960}
        destroyOnClose
        confirmLoading={bindingSaving}
        okText="保存配置"
        onCancel={() => {
          setBindingModalOpen(false);
          setBindingSpec(null);
          setBindings([]);
        }}
        onOk={async () => {
          if (!bindingSpec) return;
          setBindingSaving(true);
          try {
            await updateDeviceSpecBearingBindings(
              bindingSpec.id,
              bindings.map((item) => ({
                bearing_id: item.bearing_id,
                location_id: item.location_id,
                shaft_speed_ratio: item.shaft_speed_ratio,
                enabled: item.enabled,
              })),
            );
            message.success('轴承配置保存成功');
            setBindingModalOpen(false);
            setBindingSpec(null);
            setBindings([]);
          } catch (error) {
            message.error(toErrorMessage(error));
          } finally {
            setBindingSaving(false);
          }
        }}
      >
        <Space style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            onClick={() => {
              setEditingBindingIndex(null);
              setSelectedBearing(undefined);
              setSelectedLocation(undefined);
              setBindingEditorOpen(true);
            }}
          >
            安装位置
          </Button>
          <span style={{ color: '#8c8c8c' }}>轴转速比 = 测点轴承所在轴转速 ÷ 设备规格转速。</span>
        </Space>
        <Table<BearingBindingDraft> rowKey="draftKey" loading={bindingLoading} columns={bindingColumns} dataSource={bindings} pagination={false} size="small" />
      </Modal>

      <ModalForm<BearingBindingFormValues>
        key={editingBindingIndex === null ? 'new-bearing-binding' : `edit-bearing-binding-${editingBindingIndex}`}
        title={editingBindingIndex === null ? '添加轴承位置' : '编辑轴承位置'}
        open={bindingEditorOpen}
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setBindingEditorOpen(false);
            setEditingBindingIndex(null);
            setSelectedBearing(undefined);
            setSelectedLocation(undefined);
          },
        }}
        initialValues={
          editingBindingIndex === null
            ? { shaft_speed_ratio: 1, enabled: true }
            : bindings[editingBindingIndex]
        }
        onFinish={async (values) => {
          const previous = editingBindingIndex === null ? undefined : bindings[editingBindingIndex];
          const next: BearingBindingDraft = {
            id: previous?.id,
            device_spec_id: bindingSpec?.id || '',
            bearing_id: values.bearing_id,
            location_id: values.location_id,
            shaft_speed_ratio: values.shaft_speed_ratio,
            enabled: values.enabled ?? true,
            bearing: selectedBearing,
            location: selectedLocation,
            draftKey: previous?.draftKey || `${values.location_id}-${values.bearing_id}-${Date.now().toString(36)}`,
          };
          setBindings((current) =>
            editingBindingIndex === null
              ? [...current, next]
              : current.map((item, index) => (index === editingBindingIndex ? next : item)),
          );
          setBindingEditorOpen(false);
          setEditingBindingIndex(null);
          setSelectedBearing(undefined);
          setSelectedLocation(undefined);
          return true;
        }}
      >
        <ProForm.Item name="location_id" label="故障测点" rules={[{ required: true, message: '请选择故障测点' }]}>
          <EntityPicker<Location>
            placeholder="请点击选择故障测点"
            modalTitle="选择故障测点"
            triggerText="选择"
            valueLabel={selectedLocation?.name}
            columns={[{ title: '名称', dataIndex: 'name', width: 200 }]}
            getRecordLabel={(record) => record.name}
            fetcher={async ({ current, pageSize, keyword }) => {
              const result = await queryLocations(current, pageSize, keyword, true);
              return { items: result.data, total: result.total };
            }}
            onRecordChange={setSelectedLocation}
          />
        </ProForm.Item>
        <ProForm.Item name="bearing_id" label="轴承型号" rules={[{ required: true, message: '请选择轴承型号' }]}>
          <EntityPicker<BearingModel>
            placeholder="请点击选择轴承型号"
            modalTitle="选择轴承型号"
            triggerText="选择"
            valueLabel={selectedBearing ? `${selectedBearing.brand} / ${selectedBearing.model}` : undefined}
            columns={[
              { title: '品牌', dataIndex: 'brand' },
              { title: '型号', dataIndex: 'model' },
              { title: '轴承类型', dataIndex: 'bearing_type' },
            ]}
            getRecordLabel={(record) => `${record.brand} / ${record.model}`}
            fetcher={async ({ current, pageSize, keyword }) => {
              const result = await queryBearings({ current, pageSize, keyword, activeOnly: true });
              return { items: result.data, total: result.total };
            }}
            onRecordChange={setSelectedBearing}
          />
        </ProForm.Item>
        <ProFormDigit name="shaft_speed_ratio" label="轴转速比" min={0.0001} max={1000} fieldProps={{ precision: 4 }} rules={[{ required: true, message: '请输入轴转速比' }]} />
        <ProFormSwitch name="enabled" label="参与诊断" />
      </ModalForm>
    </PageContainer>
  );
};

export default DeviceSpecPage;

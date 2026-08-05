import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ProForm,
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormSwitch,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Modal, Popconfirm, Space, Table, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from '@umijs/max';

import EntityPicker from '@/components/EntityPicker';
import { BearingModel, queryBearings } from '@/services/bearing';
import { Location, queryLocations } from '@/services/location';
import {
  DeviceCategory,
  queryDeviceCategories,
} from '@/services/deviceCategory';
import {
  DeviceSpec,
  DeviceSpecPayload,
  createDeviceSpec,
  deleteDeviceSpec,
  DeviceSpecBearingBinding,
  DeviceSpecBearingBindingPayload,
  getDeviceSpecBearingBindings,
  listAllDeviceSpecs,
  updateDeviceSpec,
  updateDeviceSpecBearingBindings,
} from '@/services/deviceSpec';
import { Supplier, querySuppliers } from '@/services/supplier';
import {
  ProcessDevice,
  listAllProcessDevices,
} from '@/services/process';

import { renderRefSafeTableOptions } from '@/utils/proTableOptions';

type CategoryTreeRow = DeviceCategory & {
  children?: CategoryTreeRow[];
};

type DeviceSpecFormValues = {
  name: string;
  model: string;
  description?: string;
  brand: string;
  voltage: number;
  rpm: number;
  supplier_id: string;
  device_category_id: string;
};

type BearingBindingFormValues = DeviceSpecBearingBindingPayload;

type BearingBindingDraft = DeviceSpecBearingBinding & {
  draftKey: string;
};


const toErrorMessage = (error: unknown): string => {
  const e = error as
    | {
      data?: { detail?: string };
      info?: { errorMessage?: string };
      message?: string;
    }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const buildCategoryTree = (rows: DeviceCategory[]): CategoryTreeRow[] => {
  const nodeMap = new Map<string, CategoryTreeRow>();
  rows.forEach((item) => nodeMap.set(item.id, { ...item, children: [] }));

  const roots: CategoryTreeRow[] = [];
  rows.forEach((item) => {
    const node = nodeMap.get(item.id);
    if (!node) {
      return;
    }
    const pid = item.parent_id || undefined;
    if (pid && nodeMap.has(pid)) {
      const parent = nodeMap.get(pid);
      if (parent) {
        parent.children = parent.children || [];
        parent.children.push(node);
      }
      return;
    }
    roots.push(node);
  });

  const sortTree = (nodes: CategoryTreeRow[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
    nodes.forEach((item) => {
      if (item.children && item.children.length > 0) {
        sortTree(item.children);
      }
    });
  };
  sortTree(roots);
  return roots;
};

const DeviceSpecPage = () => {
  const navigate = useNavigate();
  const formRef = useRef<import('@ant-design/pro-components').ProFormInstance>();

  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<DeviceSpec[]>([]);
  const [processDevices, setProcessDevices] = useState<ProcessDevice[]>([]);
  const [editing, setEditing] = useState<DeviceSpec | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [bindingModalOpen, setBindingModalOpen] = useState(false);
  const [bindingEditorOpen, setBindingEditorOpen] = useState(false);
  const [bindingLoading, setBindingLoading] = useState(false);
  const [bindingSaving, setBindingSaving] = useState(false);
  const [bindingSpec, setBindingSpec] = useState<DeviceSpec | null>(null);
  const [bindings, setBindings] = useState<BearingBindingDraft[]>([]);
  const [editingBindingIndex, setEditingBindingIndex] = useState<number | null>(null);
  const [selectedBearing, setSelectedBearing] = useState<BearingModel | undefined>();
  const [selectedLocation, setSelectedLocation] =
    useState<Pick<Location, 'id' | 'name'> | undefined>();

  const loadRows = async (processDeviceId?: string) => {
    setLoading(true);
    try {
      const specs = await listAllDeviceSpecs(processDeviceId);
      setRows(specs);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows();
    listAllProcessDevices()
      .then(setProcessDevices)
      .catch((error) => message.error(toErrorMessage(error)));
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.name && !norm(row.name).includes(norm(query.name))) {
        return false;
      }
      if (query.model && !norm(row.model).includes(norm(query.model))) {
        return false;
      }
      if (query.brand && !norm(row.brand).includes(norm(query.brand))) {
        return false;
      }
      if (query.supplier_id) {
        const supplierName = row.supplier?.name || '';
        const hit =
          norm(supplierName).includes(norm(query.supplier_id)) ||
          norm(row.supplier_id).includes(norm(query.supplier_id));
        if (!hit) {
          return false;
        }
      }
      if (query.device_category_id) {
        const categoryName = row.device_category?.name || '';
        const hit =
          norm(categoryName).includes(norm(query.device_category_id)) ||
          norm(row.device_category_id).includes(norm(query.device_category_id));
        if (!hit) {
          return false;
        }
      }
      if (query.rpm !== undefined && query.rpm !== null && String(row.rpm) !== String(query.rpm)) {
        return false;
      }
      if (
        query.voltage !== undefined &&
        query.voltage !== null &&
        String(row.voltage) !== String(query.voltage)
      ) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const supplierPickerColumns: ColumnsType<Supplier> = [
    { title: '名称', dataIndex: 'name' },
    { title: '品牌', dataIndex: 'brand' },
    {
      title: '联系方式',
      dataIndex: 'contact_info',
      render: (_, row) => row.contact_info || '-',
    },
    {
      title: '状态',
      dataIndex: 'active',
      width: 80,
      render: (_, row) => (row.active ? '启用' : '停用'),
    },
  ];

  const categoryPickerColumns: ColumnsType<DeviceCategory> = [
    { title: '分类名称', dataIndex: 'name' },
    {
      title: '描述',
      dataIndex: 'description',
      render: (_, row) => row.description || '-',
    },
  ];

  const bearingPickerColumns: ColumnsType<BearingModel> = [
    { title: '品牌', dataIndex: 'brand', width: 130 },
    { title: '型号', dataIndex: 'model', width: 160 },
    {
      title: '轴承类型',
      dataIndex: 'bearing_type',
      render: (_, row) => row.bearing_type || '-',
    },
    { title: '滚动体数量', dataIndex: 'rolling_element_count', width: 110 },
    {
      title: '状态',
      dataIndex: 'active',
      width: 80,
      render: (_, row) => (row.active ? '启用' : '停用'),
    },
  ];

  const openBindingModal = async (spec: DeviceSpec) => {
    setBindingSpec(spec);
    setBindingModalOpen(true);
    setBindingLoading(true);
    try {
      const data: DeviceSpecBearingBinding[] =
        await getDeviceSpecBearingBindings(spec.id);
      setBindings(
        data.map((item, index) => ({
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
    {
      title: '安装位置',
      dataIndex: 'location_id',
      width: 140,
      render: (_, row) => row.location?.name || row.location_id,
    },
    {
      title: '轴承型号',
      render: (_, row) =>
        row.bearing ? `${row.bearing.brand} / ${row.bearing.model}` : row.bearing_id,
    },
    {
      title: '轴转速比',
      dataIndex: 'shaft_speed_ratio',
      width: 110,
    },
    {
      title: '诊断状态',
      dataIndex: 'enabled',
      width: 100,
      render: (_, row) =>
        row.enabled ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '操作',
      width: 130,
      align: 'center',
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
            onConfirm={() =>
              setBindings((current) => current.filter((item) => item.draftKey !== row.draftKey))
            }
          >
            <a style={{ color: '#ff4d4f' }}>移除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const columns: ProColumns<DeviceSpec>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },

    {
      title: '名称',
      dataIndex: 'name',
      width: 180,
      sorter: (a, b) => (a.name || '').localeCompare(b.name || '', 'zh-CN'),
    },
    {
      title: '设备分组',
      dataIndex: 'process_device_id',
      hideInTable: true,
      valueType: 'select',
      fieldProps: {
        allowClear: true,
        showSearch: true,
        options: processDevices.map((item) => ({
          value: item.id,
          label: [
            item.code,
            item.sn,
            item.process?.name,
            item.status === 1 ? undefined : '已停用',
          ]
            .filter(Boolean)
            .join(' / '),
        })),
        optionFilterProp: 'label',
        placeholder: '请选择设备分组',
      },
    },
    {
      title: '型号',
      dataIndex: 'model',
      width: 100,
      ellipsis: true,
      sorter: (a, b) => (a.model || '').localeCompare(b.model || '', 'zh-CN'),
    },
    {
      title: '电压',
      dataIndex: 'voltage',
      width: 80,
      valueType: 'digit',
      sorter: (a, b) => Number(a.voltage) - Number(b.voltage),
    },
    {
      title: '转速',
      dataIndex: 'rpm',
      width: 80,
      valueType: 'digit',
      sorter: (a, b) => Number(a.rpm) - Number(b.rpm),
    },
    {
      title: '分类',
      dataIndex: 'device_category_id',
      width: 100,
      render: (_, row) => row.device_category?.name || '-',
      sorter: (a, b) => {
        const labelA = a.device_category?.name || '';
        const labelB = b.device_category?.name || '';
        return labelA.localeCompare(labelB, 'zh-CN');
      },
    },
    {
      title: '供应商',
      dataIndex: 'supplier_id',
      width: 160,
      ellipsis: true,
      render: (_, row) => row.supplier?.name || '-',
      sorter: (a, b) => {
        const labelA = a.supplier?.name || '';
        const labelB = b.supplier?.name || '';
        return labelA.localeCompare(labelB, 'zh-CN');
      },
    },
    {
      title: '品牌',
      dataIndex: 'brand',
      width: 100,
      sorter: (a, b) => (a.brand || '').localeCompare(b.brand || '', 'zh-CN'),
    },
    {
      title: '备注',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
      hideInSearch: true,
      sorter: (a, b) => (a.description || '').localeCompare(b.description || '', 'zh-CN'),
    },
    {
      title: '操作',
      valueType: 'option',
      width: 180,
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="middle">
          <a
            key="comparison"
            onClick={() => {
              const groupQuery = query.process_device_id
                ? `?group=${encodeURIComponent(query.process_device_id)}`
                : '';
              navigate(`/device/specs/${row.id}/comparison${groupQuery}`);
            }}
          >
            对比
          </a>
          <a key="bearing" onClick={() => void openBindingModal(row)}>
            轴承
          </a>
          <a
            key="edit"
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            key="delete"
            title="确认删除该设备规格吗？"
            onConfirm={async () => {
              try {
                await deleteDeviceSpec(row.id);
                message.success('删除成功');
                await loadRows(query.process_device_id);
              } catch (error) {
                message.error(toErrorMessage(error));
              }
            }}
          >
            <a style={{ color: '#ff4d4f' }}>
              删除
            </a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="设备规格">
      <ProTable<DeviceSpec>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={async (values) => {
          setQuery(values);
          await loadRows(values.process_device_id);
        }}
        onReset={() => {
          setQuery({});
          void loadRows();
        }}
        options={{ reload: () => loadRows(query.process_device_id) }}
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
        submitter={{
          submitButtonProps: { loading: saving },
          searchConfig: { submitText: '保存' },
        }}
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
            }
            : { voltage: 0, rpm: 0 }
        }
        onFinish={async (values) => {
          const payload: DeviceSpecPayload = {
            name: values.name.trim(),
            model: values.model.trim(),
            description: values.description || undefined,
            brand: values.brand.trim(),
            voltage: values.voltage,
            rpm: values.rpm,
            supplier_id: values.supplier_id,
            device_category_id: values.device_category_id,
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
            await loadRows(query.process_device_id);
            return true;
          } catch (error) {
            message.error(toErrorMessage(error));
            return false;
          } finally {
            setSaving(false);
          }
        }}
      >
        <ProFormText name="name" label="名称" rules={[{ required: true, message: '请输入规格名称' }]} />
        <ProForm.Item
          name="device_category_id"
          label="设备分类"
          rules={[{ required: true, message: '请选择设备分类' }]}
        >
          <EntityPicker<DeviceCategory>
            placeholder="请点击选择设备分类"
            modalTitle="选择设备分类"
            triggerText="选择"
            valueLabel={editing?.device_category?.name}
            columns={categoryPickerColumns}
            getRecordLabel={(record) => record.name}
            fetcher={({ current, pageSize, keyword }) =>
              queryDeviceCategories({ current, pageSize, keyword })
            }
          />
        </ProForm.Item>
        <ProForm.Item name="supplier_id" label="供应商" rules={[{ required: true, message: '请选择供应商' }]}>
          <EntityPicker<Supplier>
            placeholder="请点击选择供应商"
            modalTitle="选择供应商"
            triggerText="选择"
            valueLabel={editing?.supplier?.name}
            columns={supplierPickerColumns}
            getRecordLabel={(record) => record.name}
            fetcher={({ current, pageSize, keyword }) =>
              querySuppliers({ current, pageSize, keyword })
            }
            onRecordChange={(record) => {
              formRef.current?.setFieldsValue({ brand: record?.brand || '' });
            }}
          />
        </ProForm.Item>
        <ProFormDigit
          name="rpm"
          label="转速(RPM)"
          min={0}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入转速' }]}
        />
        <ProFormDigit
          name="voltage"
          label="电压(V)"
          min={0}
          fieldProps={{ precision: 2 }}
          rules={[{required: true,  message: '请输入电压' }]}
        />

        <ProFormText name="model" label="型号" rules={[{ message: '请输入型号' }]} />
        <ProFormText
          name="brand"
          label="品牌"
          disabled={true}
          rules={[{ message: '品牌将自动填写' }]}
          fieldProps={{ readOnly: true, placeholder: '选择供应商后自动填写' }}
        />
        <ProFormText name="description" label="备注" />
      </ModalForm>

      <Modal
        title={bindingSpec ? `${bindingSpec.name} - 轴承配置` : '轴承配置'}
        open={bindingModalOpen}
        width={960}
        destroyOnHidden
        confirmLoading={bindingSaving}
        okText="保存配置"
        onCancel={() => {
          setBindingModalOpen(false);
          setBindingSpec(null);
          setBindings([]);
        }}
        onOk={async () => {
          if (!bindingSpec) {
            return;
          }
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
          <span style={{ color: '#8c8c8c' }}>
            轴转速比 = 该测点轴承所在轴转速 ÷ 设备规格转速，直联设备填写 1。
          </span>
        </Space>
        <Table<BearingBindingDraft>
          rowKey="draftKey"
          loading={bindingLoading}
          columns={bindingColumns}
          dataSource={bindings}
          pagination={false}
          size="small"
        />
      </Modal>

      <ModalForm<BearingBindingFormValues>
        key={
          bindingEditorOpen
            ? editingBindingIndex === null
              ? 'new-bearing-binding'
              : `edit-bearing-binding-${bindings[editingBindingIndex]?.draftKey}`
            : 'closed-bearing-binding'
        }
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
            ? {
                shaft_speed_ratio: 1,
                enabled: true,
              }
            : bindings[editingBindingIndex]
        }
        onFinish={async (values) => {
          const locationId = values.location_id;
          const duplicate = bindings.some(
            (item, index) =>
              index !== editingBindingIndex &&
              item.location_id === locationId,
          );
          if (duplicate) {
            message.error(`测点“${selectedLocation?.name || locationId}”已配置轴承`);
            return false;
          }
          const previous =
            editingBindingIndex === null ? undefined : bindings[editingBindingIndex];
          const next: BearingBindingDraft = {
            id: previous?.id,
            device_spec_id: bindingSpec?.id || '',
            bearing_id: values.bearing_id,
            location_id: locationId,
            shaft_speed_ratio: values.shaft_speed_ratio,
            enabled: values.enabled ?? true,
            bearing:
              selectedBearing?.id === values.bearing_id
                ? selectedBearing
                : previous?.bearing?.id === values.bearing_id
                  ? previous.bearing
                  : undefined,
            location:
              selectedLocation?.id === locationId
                ? selectedLocation
                : previous?.location?.id === locationId
                  ? previous.location
                  : undefined,
            draftKey:
              previous?.draftKey ||
              `${locationId}-${values.bearing_id}-${Date.now().toString(36)}`,
          };
          setBindings((current) => {
            if (editingBindingIndex === null) {
              return [...current, next];
            }
            return current.map((item, index) =>
              index === editingBindingIndex ? next : item,
            );
          });
          setBindingEditorOpen(false);
          setEditingBindingIndex(null);
          setSelectedBearing(undefined);
          setSelectedLocation(undefined);
          return true;
        }}
      >
        <ProForm.Item
          name="location_id"
          label="故障测点"
          rules={[{ required: true, message: '请选择故障测点' }]}
        >
          <EntityPicker<Location>
            placeholder="请点击选择故障测点"
            modalTitle="选择故障测点"
            triggerText="选择"
            valueLabel={selectedLocation?.name}
            columns={[{ title: '名称', dataIndex: 'name', width: 200 }]}
            getRecordLabel={(record) => record.name}
            fetcher={({ current, pageSize, keyword }) =>
              queryLocations(current, pageSize, keyword, true)
            }
            onRecordChange={setSelectedLocation}
          />
        </ProForm.Item>
        <ProForm.Item
          name="bearing_id"
          label="轴承型号"
          rules={[{ required: true, message: '请选择轴承型号' }]}
        >
          <EntityPicker<BearingModel>
            placeholder="请点击选择轴承型号"
            modalTitle="选择轴承型号"
            triggerText="选择"
            valueLabel={
              selectedBearing
                ? `${selectedBearing.brand} / ${selectedBearing.model}`
                : undefined
            }
            columns={bearingPickerColumns}
            getRecordLabel={(record) => `${record.brand} / ${record.model}`}
            fetcher={({ current, pageSize, keyword }) =>
              queryBearings({ current, pageSize, keyword, activeOnly: true })
            }
            onRecordChange={setSelectedBearing}
          />
        </ProForm.Item>
        <ProFormDigit
          name="shaft_speed_ratio"
          label="轴转速比"
          min={0.0001}
          max={1000}
          fieldProps={{ precision: 4 }}
          tooltip="该轴承所在轴转速 ÷ 设备规格转速"
          rules={[{ required: true, message: '请输入轴转速比' }]}
        />
        <ProFormSwitch name="enabled" label="参与诊断" />
      </ModalForm>
    </PageContainer>
  );
};

export default DeviceSpecPage;

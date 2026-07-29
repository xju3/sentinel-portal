import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ProForm,
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import EntityPicker from '@/components/EntityPicker';
import {
  DeviceCategory,
  queryDeviceCategories,
} from '@/services/deviceCategory';
import {
  DeviceSpec,
  DeviceSpecPayload,
  createDeviceSpec,
  deleteDeviceSpec,
  listAllDeviceSpecs,
  updateDeviceSpec,
} from '@/services/deviceSpec';
import { Supplier, querySuppliers } from '@/services/supplier';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

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
  const formRef = useRef<import('@ant-design/pro-components').ProFormInstance>();

  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<DeviceSpec[]>([]);
  const [editing, setEditing] = useState<DeviceSpec | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});

  const loadRows = async () => {
    setLoading(true);
    try {
      const specs = await listAllDeviceSpecs();
      setRows(specs);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows();
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
      title: '型号',
      dataIndex: 'model',
      width: 100,
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
      width: OPERATION_COL_WIDTH,
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="middle">
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
                await loadRows();
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
        scroll={{ x: 'max-content' }}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadRows }}
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
            await loadRows();
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
    </PageContainer>
  );
};

export default DeviceSpecPage;

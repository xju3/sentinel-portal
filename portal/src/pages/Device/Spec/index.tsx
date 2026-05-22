import { useEffect, useMemo, useState } from 'react';
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
  listAllDeviceCategories,
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
import { Supplier, listAllSuppliers, querySuppliers } from '@/services/supplier';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
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

const DeviceSpecPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<DeviceSpec[]>([]);
  const [editing, setEditing] = useState<DeviceSpec | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});

  const [categories, setCategories] = useState<DeviceCategory[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  const categoryMap = useMemo(
    () => new Map(categories.map((item) => [item.id, item.name])),
    [categories],
  );
  const supplierMap = useMemo(
    () => new Map(suppliers.map((item) => [item.id, item.name])),
    [suppliers],
  );

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listAllDeviceSpecs());
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const loadReferences = async () => {
    try {
      const [cates, sups] = await Promise.all([listAllDeviceCategories(), listAllSuppliers()]);
      setCategories(cates || []);
      setSuppliers(sups || []);
    } catch (error) {
      message.error(toErrorMessage(error));
    }
  };

  useEffect(() => {
    loadRows();
    loadReferences();
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
        const supplierName = supplierMap.get(row.supplier_id) || '';
        const hit =
          norm(supplierName).includes(norm(query.supplier_id)) ||
          norm(row.supplier_id).includes(norm(query.supplier_id));
        if (!hit) {
          return false;
        }
      }
      if (query.device_category_id) {
        const categoryName = categoryMap.get(row.device_category_id) || '';
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
  }, [categoryMap, query, rows, supplierMap]);

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
      title: '规格名称',
      dataIndex: 'name',
      width: 180,
    },
    {
      title: '型号',
      dataIndex: 'model',
      width: 100,
    },
    {
      title: '品牌',
      dataIndex: 'brand',
      width: 100,
    },
    {
      title: '电压(V)',
      dataIndex: 'voltage',
      width: 100,
      valueType: 'digit',
    },
    {
      title: '转速(RPM)',
      dataIndex: 'rpm',
      width: 100,
      valueType: 'digit',
    },
    {
      title: '供应商',
      dataIndex: 'supplier_id',
      width: 180,
      render: (_, row) => supplierMap.get(row.supplier_id) || row.supplier_id,
    },
    {
      title: '分类',
      dataIndex: 'device_category_id',
      width: 180,
      render: (_, row) => categoryMap.get(row.device_category_id) || row.device_category_id,
    },
    {
      title: '备注',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
      hideInSearch: true,
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
        <ProFormText name="name" label="规格名称" rules={[{ required: true, message: '请输入规格名称' }]} />
        <ProFormText name="model" label="型号" rules={[{ required: true, message: '请输入型号' }]} />
        <ProFormText name="brand" label="品牌" rules={[{ required: true, message: '请输入品牌' }]} />
        <ProFormDigit
          name="voltage"
          label="电压(V)"
          min={0}
          fieldProps={{ precision: 2 }}
          rules={[{ required: true, message: '请输入电压' }]}
        />
        <ProFormDigit
          name="rpm"
          label="转速(RPM)"
          min={0}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入转速' }]}
        />
        <ProForm.Item name="supplier_id" label="供应商" rules={[{ required: true, message: '请选择供应商' }]}>
          <EntityPicker<Supplier>
            placeholder="请点击选择供应商"
            modalTitle="选择供应商"
            triggerText="选择"
            valueLabel={editing ? supplierMap.get(editing.supplier_id) : undefined}
            columns={supplierPickerColumns}
            getRecordLabel={(record) => record.name}
            fetcher={({ current, pageSize, keyword }) =>
              querySuppliers({ current, pageSize, keyword })
            }
          />
        </ProForm.Item>
        <ProForm.Item
          name="device_category_id"
          label="设备分类"
          rules={[{ required: true, message: '请选择设备分类' }]}
        >
          <EntityPicker<DeviceCategory>
            placeholder="请点击选择设备分类"
            modalTitle="选择设备分类"
            triggerText="选择"
            valueLabel={editing ? categoryMap.get(editing.device_category_id) : undefined}
            columns={categoryPickerColumns}
            getRecordLabel={(record) => record.name}
            fetcher={({ current, pageSize, keyword }) =>
              queryDeviceCategories({ current, pageSize, keyword })
            }
          />
        </ProForm.Item>
        <ProFormText name="description" label="备注" />
      </ModalForm>
    </PageContainer>
  );
};

export default DeviceSpecPage;

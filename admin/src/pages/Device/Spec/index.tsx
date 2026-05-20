import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, message } from 'antd';

import {
  DeviceSpec,
  DeviceSpecPayload,
  createDeviceSpec,
  deleteDeviceSpec,
  listDeviceSpecs,
  updateDeviceSpec,
} from '@/services/deviceSpec';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const DeviceSpecPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<DeviceSpec[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<DeviceSpec | null>(null);

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listDeviceSpecs());
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
      return true;
    });
  }, [query, rows]);

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
      width: 160,
    },
    {
      title: '型号',
      dataIndex: 'model',
      width: 140,
    },
    {
      title: '品牌',
      dataIndex: 'brand',
      width: 140,
    },
    {
      title: '电压(V)',
      dataIndex: 'voltage',
      width: 100,
      valueType: 'digit',
      hideInSearch: true,
    },
    {
      title: '转速(RPM)',
      dataIndex: 'rpm',
      width: 110,
      valueType: 'digit',
      hideInSearch: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '操作',
      valueType: 'option',
      width: 160,
      render: (_, row) => [
        <Button
          key="edit"
          type="link"
          onClick={() => {
            setEditing(row);
            setModalOpen(true);
          }}
        >
          编辑
        </Button>,
        <Popconfirm
          key="delete"
          title="确认删除该设备型号吗？"
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
          <Button danger type="link">
            删除
          </Button>
        </Popconfirm>,
      ],
    },
  ];

  return (
    <PageContainer
      title="设备型号管理"
      subTitle="管理所有设备型号规格"
    >
      <ProTable<DeviceSpec>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        scroll={{ x: 900 }}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadRows }}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            新建型号
          </Button>,
        ]}
      />

      <ModalForm<DeviceSpecPayload>
        title={editing ? '编辑设备型号' : '新建设备型号'}
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
                brand: editing.brand,
                description: editing.description,
                voltage: editing.voltage,
                rpm: editing.rpm,
                supplier_id: editing.supplier_id,
                device_category_id: editing.device_category_id,
              }
            : {
                voltage: 0,
                rpm: 0,
              }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: DeviceSpecPayload = {
              name: values.name.trim(),
              model: values.model.trim(),
              brand: values.brand.trim(),
              description: values.description?.trim(),
              voltage: Number(values.voltage ?? 0),
              rpm: Number(values.rpm ?? 0),
              supplier_id: values.supplier_id,
              device_category_id: values.device_category_id,
            };

            if (editing) {
              await updateDeviceSpec(editing.id, payload);
              message.success('更新成功');
            } else {
              await createDeviceSpec(payload);
              message.success('创建成功');
            }
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
        <ProFormText
          name="name"
          label="规格名称"
          rules={[
            { required: true, message: '请输入规格名称' },
            { max: 64, message: '名称最多64个字符' },
          ]}
        />
        <ProFormText
          name="model"
          label="型号"
          rules={[
            { required: true, message: '请输入型号' },
            { max: 32, message: '型号最多32个字符' },
          ]}
        />
        <ProFormText
          name="brand"
          label="品牌"
          rules={[
            { required: true, message: '请输入品牌' },
            { max: 64, message: '品牌最多64个字符' },
          ]}
        />
        <ProFormText
          name="description"
          label="描述"
          rules={[{ max: 255, message: '描述最多255个字符' }]}
        />
        <ProFormDigit
          name="voltage"
          label="电压(V)"
          min={0}
          fieldProps={{ precision: 1 }}
        />
        <ProFormDigit
          name="rpm"
          label="转速(RPM)"
          min={0}
          fieldProps={{ precision: 0 }}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default DeviceSpecPage;

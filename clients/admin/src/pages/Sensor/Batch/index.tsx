import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Tag, message } from 'antd';

import {
  SensorBatch,
  SensorBatchPayload,
  createSensorBatch,
  deleteSensorBatch,
  listSensorBatches,
  updateSensorBatch,
} from '@/services/sensorBatch';
import { listSensorTypes, SensorType } from '@/services/sensorType';
import { listTenants, Tenant } from '@/services/tenant';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const STATUS_MAP: Record<number, { text: string; color: string }> = {
  0: { text: '计划中', color: 'default' },
  1: { text: '生产中', color: 'processing' },
  2: { text: '交付中', color: 'warning' },
  3: { text: '已交付', color: 'success' },
};

const STATUS_OPTIONS = [
  { label: '计划中', value: 0 },
  { label: '生产中', value: 1 },
  { label: '交付中', value: 2 },
  { label: '已交付', value: 3 },
];

const SensorBatchPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<SensorBatch[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<SensorBatch | null>(null);
  const [sensorTypes, setSensorTypes] = useState<SensorType[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listSensorBatches());
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const loadSensorTypes = async () => {
    try {
      setSensorTypes(await listSensorTypes());
    } catch (error) {
      message.error(toErrorMessage(error));
    }
  };

  const loadTenants = async () => {
    try {
      setTenants(await listTenants());
    } catch (error) {
      message.error(toErrorMessage(error));
    }
  };

  useEffect(() => {
    loadRows();
    loadSensorTypes();
    loadTenants();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.code && !norm(row.code).includes(norm(query.code))) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const sensorTypeOptions = useMemo(
    () => sensorTypes.map((t) => ({ label: t.name, value: t.id })),
    [sensorTypes],
  );

  const tenantOptions = useMemo(
    () => tenants.map((t) => ({ label: `${t.name} (${t.code})`, value: t.id })),
    [tenants],
  );

  const getSensorTypeName = (id: string) => {
    const found = sensorTypes.find((t) => t.id === id);
    return found ? found.name : id;
  };

  const getTenantName = (id: string) => {
    const found = tenants.find((t) => t.id === id);
    return found ? `${found.name} (${found.code})` : id;
  };

  const columns: ProColumns<SensorBatch>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '所属租户',
      dataIndex: 'tenant_id',
      width: 300,
      hideInSearch: true,
      render: (_, row) => getTenantName(row.tenant_id),
    },
    {
      title: '型号',
      dataIndex: 'sensor_type_id',
      width: 80,
      hideInSearch: true,
      render: (_, row) => getSensorTypeName(row.sensor_type_id),
    },
    {
      title: '批次',
      dataIndex: 'code',
      width: 80,
    },
    {
      title: '序列号',
      dataIndex: 'sn',
      width: 80,
      hideInSearch: true,
      render: (_, row) => <Tag>{row.sn}</Tag>,
    },
    {
      title: '数量',
      dataIndex: 'qty',
      width: 80,
      hideInSearch: true,
      render: (_, row) => <Tag color="blue">{row.qty}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      valueType: 'select',
      valueEnum: {
        0: { text: '计划中', status: 'Default' },
        1: { text: '生产中', status: 'Processing' },
        2: { text: '交付中', status: 'Warning' },
        3: { text: '已交付', status: 'Success' },
      },
      render: (_, row) => {
        const info = STATUS_MAP[row.status] || { text: `${row.status}`, color: 'default' };
        return <Tag color={info.color}>{info.text}</Tag>;
      },
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      valueType: 'dateTime',
      hideInSearch: true,
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
          title="确认删除该批次吗？"
          onConfirm={async () => {
            try {
              await deleteSensorBatch(row.id);
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
      title="传感器批次管理"
      subTitle="管理所有传感器批次"
    >
      <ProTable<SensorBatch>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        scroll={{ x: 1400 }}
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
            新建批次
          </Button>,
        ]}
      />

      <ModalForm<SensorBatchPayload & { tenant_id: string }>
        title={editing ? '编辑传感器批次' : '新建传感器批次'}
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
              code: editing.code,
              qty: editing.qty,
              sn: editing.sn,
              status: editing.status,
              description: editing.description,
              sensor_type_id: editing.sensor_type_id,
              tenant_id: editing.tenant_id,
            }
            : { qty: 0, sn: 0, status: 0 }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: SensorBatchPayload & { tenant_id: string } = {
              code: values.code.trim(),
              qty: Number(values.qty ?? 0),
              sn: Number(values.sn ?? 0),
              status: Number(values.status ?? 0),
              description: values.description?.trim(),
              sensor_type_id: values.sensor_type_id,
              tenant_id: values.tenant_id,
            };

            if (editing) {
              await updateSensorBatch(editing.id, payload);
              message.success('更新成功');
            } else {
              await createSensorBatch(payload);
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
          name="code"
          label="批次编码"
          rules={[
            { required: true, message: '请输入批次编码' },
            { max: 255, message: '编码最多255个字符' },
          ]}
        />
        <ProFormDigit
          name="qty"
          label="数量"
          min={0}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入数量' }]}
        />
        <ProFormDigit
          name="sn"
          label="序列号前缀"
          min={0}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入序列号前缀' }]}
        />
        <ProFormSelect
          name="status"
          label="状态"
          options={STATUS_OPTIONS}
          rules={[{ required: true, message: '请选择状态' }]}
        />
        <ProFormSelect
          name="sensor_type_id"
          label="传感器型号"
          options={sensorTypeOptions}
          rules={[{ required: true, message: '请选择传感器型号' }]}
        />
        <ProFormSelect
          name="tenant_id"
          label="所属租户"
          options={tenantOptions}
          rules={[{ required: true, message: '请选择所属租户' }]}
        />
        <ProFormTextArea
          name="description"
          label="描述"
        />
      </ModalForm>
    </PageContainer>
  );
};

export default SensorBatchPage;

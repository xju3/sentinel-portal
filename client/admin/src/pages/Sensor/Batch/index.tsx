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
import { Button, Popconfirm, Tag, message, Form } from 'antd';

import { listProvinces, Region } from '@/services/region';
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
  const [provinces, setProvinces] = useState<Region[]>([]);
  const [form] = Form.useForm<SensorBatchPayload & { tenant_id: string }>();

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

  const loadProvinces = async () => {
    try {
      setProvinces(await listProvinces());
    } catch (error) {
      console.error(error);
    }
  };

  useEffect(() => {
    loadRows();
    loadSensorTypes();
    loadTenants();
    loadProvinces();
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

  const handleUpgradeStatus = async (row: SensorBatch) => {
    const nextStatus = row.status + 1;
    if (nextStatus > 3) return;
    try {
      setLoading(true);
      await updateSensorBatch(row.id, {
        code: row.code,
        qty: row.qty,
        sn: row.sn,
        status: nextStatus,
        description: row.description,
        sensor_type_id: row.sensor_type_id,
        tenant_id: row.tenant_id,
      } as SensorBatchPayload & { tenant_id: string });
      message.success(`已升级为: ${STATUS_MAP[nextStatus].text}`);
      await loadRows();
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const handleTenantChange = (tenantId: string) => {
    if (editing) return;
    const tenant = tenants.find((t) => t.id === tenantId);
    if (tenant) {
      const provinceId = tenant.region_id ? tenant.region_id.slice(0, 2) : '';
      const region = provinces.find((p) => p.id === provinceId);
      const abbr = region?.abbreviation || '';
      const year = new Date().getFullYear().toString().slice(-2);
      const prefix = `${year}${abbr}`;

      const tenantBatches = rows.filter((r) => r.tenant_id === tenantId);
      let maxCode = 0;
      tenantBatches.forEach((b) => {
        const c = parseInt(b.code, 10);
        if (!isNaN(c) && c > maxCode) {
          maxCode = c;
        }
      });
      const nextCode = String(maxCode + 1).padStart(2, '0');

      form.setFieldsValue({ sn: prefix, code: nextCode });
    }
  };

  const columns: ProColumns<SensorBatch>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 40,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '所属租户',
      dataIndex: 'tenant_id',
      width: 160,
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => getTenantName(row.tenant_id),
    },
    {
      title: '批次',
      dataIndex: 'code',
      width: 60,
    },
    {
      title: '型号',
      dataIndex: 'sensor_type_id',
      width: 120,
      hideInSearch: true,
      render: (_, row) => getSensorTypeName(row.sensor_type_id),
    },

    {
      title: '序列号',
      dataIndex: 'sn',
      width: 60,
      hideInSearch: true,
      render: (_, row) => <Tag>{row.sn}</Tag>,
    },
    {
      title: '数量',
      dataIndex: 'qty',
      width: 60,
      hideInSearch: true,
      render: (_, row) => <Tag color="blue">{row.qty}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      align: 'center',
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
      title: '创建时间',
      dataIndex: 'created_at',
      width: 150,
      valueType: 'dateTime',
      hideInSearch: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      width: 120,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '操作',
      valueType: 'option',
      // fixed: 'right',
      width: 160,
      render: (_, row) => [
        row.status <= 1 && (
          <a
            key="edit"
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>),
        row.status <= 1 && (
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
            <a style={{ color: 'red' }}>
              删除
            </a>
          </Popconfirm>
        ),


        row.status < 3 && (
          <Popconfirm
            key="upgrade"
            title={`确定要推进至【${STATUS_MAP[row.status + 1]?.text}】吗？`}
            onConfirm={() => handleUpgradeStatus(row)}
          >
            <a style={{ color: '#faad14' }}>
              推进
            </a>
          </Popconfirm>
        ),
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
        // scroll={{ x: 1400 }}
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
        form={form}
        open={modalOpen}
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setModalOpen(false);
            setEditing(null);
            form.resetFields();
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
            : { qty: 0, sn: '', status: 0 }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: SensorBatchPayload & { tenant_id: string } = {
              code: values.code.trim(),
              qty: Number(values.qty ?? 0),
              sn: String(values.sn ?? '').trim(),
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
            form.resetFields();
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
        <ProFormSelect
          name="tenant_id"
          label="所属租户"
          options={tenantOptions}
          fieldProps={{
            onChange: handleTenantChange,
          }}
          rules={[{ required: true, message: '请选择所属租户' }]}
        />

        <ProFormText
          name="sn"
          label="序列号前缀"
          disabled={true}
          rules={[{ required: true, message: '请输入序列号前缀' }]}
        />
        <ProFormText
          name="code"
          label="批次编码"
          disabled={true}
          rules={[
            { required: true, message: '请输入批次编码' },
            { max: 255, message: '编码最多255个字符' },
          ]}
        />
        <ProFormSelect
          name="sensor_type_id"
          label="传感器型号"
          options={sensorTypeOptions}
          rules={[{ required: true, message: '请选择传感器型号' }]}
        />
        <ProFormDigit
          name="qty"
          label="数量"
          min={0}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入数量' }]}
        />
        <ProFormSelect
          name="status"
          label="状态"
          disabled={true}
          options={STATUS_OPTIONS.filter(opt => {
            if (!editing) return opt.value === 0;
            return opt.value === editing.status || opt.value === editing.status + 1;
          })}
          rules={[{ required: true, message: '请选择状态' }]}
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

import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, Tag, message } from 'antd';

import {
  SensorThreshold,
  SensorThresholdPayload,
  createSensorThreshold,
  deleteSensorThreshold,
  listSensorThresholds,
  updateSensorThreshold,
} from '@/services/sensorThreshold';
import { listSensorTypes, SensorType } from '@/services/sensorType';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

const METRIC_MAP: Record<number, { text: string; color: string }> = {
  1: { text: '温度', color: 'volcano' },
  2: { text: '振动', color: 'geekblue' },
};

const METRIC_OPTIONS = [
  { label: '温度', value: 1 },
  { label: '振动', value: 2 },
];

type ThresholdFormValues = {
  code: string;
  metric: number;
  rt_max_delta: number;
  st_max_slope: number;
  st_max_amplitude: number;
  mt_max_slope: number;
  mt_max_amplitude: number;
  baseline: number;
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

const MonitoringThresholdPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<SensorThreshold[]>([]);
  const [editing, setEditing] = useState<SensorThreshold | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [sensorTypes, setSensorTypes] = useState<SensorType[]>([]);

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listSensorThresholds());
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

  useEffect(() => {
    loadRows();
    loadSensorTypes();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.code && !norm(row.code).includes(norm(query.code))) {
        return false;
      }
      if (query.metric !== undefined && query.metric !== null && row.metric !== Number(query.metric)) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const getSensorTypeName = (code: string) => {
    const found = sensorTypes.find((t) => t.name === code);
    return found ? found.name : code;
  };

  const columns: ProColumns<SensorThreshold>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
      align: 'center',
    },
    {
      title: '传感器型号',
      dataIndex: 'code',
      align: 'center',
      width: 120,
      render: (_, row) => <Tag>{getSensorTypeName(row.code)}</Tag>,
    },
    {
      title: '监测指标',
      dataIndex: 'metric',
      width: 60,
      valueType: 'select',
      align: 'center',
      valueEnum: {
        1: { text: '温度', status: 'Default' },
        2: { text: '振动', status: 'Default' },
      },
      render: (_, row) => {
        const info = METRIC_MAP[row.metric] || { text: `${row.metric}`, color: 'default' };
        return <Tag color={info.color}>{info.text}</Tag>;
      },
    },
    {
      title: '最大偏差(实时)',
      dataIndex: 'rt_max_delta',
      width: 100,
      hideInSearch: true,
      align: 'center',
      render: (_, row) => row.rt_max_delta,
    },
    {
      title: '短期(小时)',
      hideInSearch: true,
      children: [{
        title: '最大斜率',
        align: 'center',
        dataIndex: 'st_max_slope',
        width: 60,
        hideInSearch: true,
      },
      {
        title: '最大振幅',
        dataIndex: 'st_max_amplitude',
        width: 60,
        align: 'center',
        hideInSearch: true,
      },]
    },

    {
      title: '中期(3天内)',
      hideInSearch: true,
      children: [{
        title: '最大斜率',
        align: 'center',
        dataIndex: 'mt_max_slope',
        width: 60,
        hideInSearch: true,
      },
      {
        title: '最大振幅',
        align: 'center',
        dataIndex: 'mt_max_amplitude',
        width: 60,
        hideInSearch: true,
      },]
    },

    {
      title: '基线值',
      dataIndex: 'baseline',
      align: 'center',
      width: 60,
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
            title="确认删除该阀值定义吗？"
            onConfirm={async () => {
              try {
                await deleteSensorThreshold(row.id);
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
    <PageContainer title="阀值定义">
      <ProTable<SensorThreshold>
        rowKey="id"
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        loading={loading}
        columns={columns}
        bordered
        scroll={{ x: 'max-content' }}
        dataSource={filteredRows}
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
            新建阀值
          </Button>,
        ]}
      />

      <ModalForm<ThresholdFormValues>
        title={editing ? '编辑阀值定义' : '新建阀值定义'}
        open={modalOpen}
        initialValues={
          editing
            ? {
              code: editing.code,
              metric: editing.metric,
              rt_max_delta: editing.rt_max_delta,
              st_max_slope: editing.st_max_slope,
              st_max_amplitude: editing.st_max_amplitude,
              mt_max_slope: editing.mt_max_slope,
              mt_max_amplitude: editing.mt_max_amplitude,
              baseline: editing.baseline,
            }
            : {
              metric: 1,
              rt_max_delta: 0,
              st_max_slope: 0,
              st_max_amplitude: 0,
              mt_max_slope: 0,
              mt_max_amplitude: 0,
              baseline: 0,
            }
        }
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
        onFinish={async (values) => {
          const payload: SensorThresholdPayload = {
            code: values.code,
            metric: values.metric,
            rt_max_delta: values.rt_max_delta,
            st_max_slope: values.st_max_slope,
            st_max_amplitude: values.st_max_amplitude,
            mt_max_slope: values.mt_max_slope,
            mt_max_amplitude: values.mt_max_amplitude,
            baseline: values.baseline,
          };

          setSaving(true);
          try {
            if (editing) {
              await updateSensorThreshold(editing.id, payload);
            } else {
              await createSensorThreshold(payload);
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
        <ProFormText
          name="code"
          label="传感器型号"
          rules={[{ required: true, message: '请输入传感器型号' }]}
          placeholder="请输入传感器型号编码"
        />
        <ProFormSelect
          name="metric"
          label="监测指标"
          rules={[{ required: true, message: '请选择监测指标' }]}
          options={METRIC_OPTIONS}
        />
        <ProFormDigit
          name="rt_max_delta"
          label="实时最大偏差"
          rules={[{ required: true, message: '请输入实时最大偏差' }]}
          fieldProps={{ precision: 4 }}
        />
        <ProFormDigit
          name="st_max_slope"
          label="短时最大斜率"
          rules={[{ required: true, message: '请输入短时最大斜率' }]}
          fieldProps={{ precision: 4 }}
        />
        <ProFormDigit
          name="st_max_amplitude"
          label="短时最大振幅"
          rules={[{ required: true, message: '请输入短时最大振幅' }]}
          fieldProps={{ precision: 4 }}
        />
        <ProFormDigit
          name="mt_max_slope"
          label="中时最大斜率"
          rules={[{ required: true, message: '请输入中时最大斜率' }]}
          fieldProps={{ precision: 4 }}
        />
        <ProFormDigit
          name="mt_max_amplitude"
          label="中时最大振幅"
          rules={[{ required: true, message: '请输入中时最大振幅' }]}
          fieldProps={{ precision: 4 }}
        />
        <ProFormDigit
          name="baseline"
          label="基线值"
          rules={[{ required: true, message: '请输入基线值' }]}
          fieldProps={{ precision: 4 }}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default MonitoringThresholdPage;

import { useRef, useState } from 'react';
import {
  ActionType,
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
  querySensorThresholds,
  updateSensorThreshold,
} from '@/services/sensorThreshold';
import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

const METRIC_MAP: Record<number, { text: string; color: string }> = {
  1: { text: '振动', color: 'geekblue' },
  2: { text: '温度', color: 'volcano' },
};

const METRIC_OPTIONS = [
  { label: '振动', value: 1 },
  { label: '温度', value: 2 },
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
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const MonitoringThresholdPage = () => {
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<SensorThreshold | null>(null);

  const columns: ProColumns<SensorThreshold>[] = [
    { title: '序号', valueType: 'indexBorder', width: 68, hideInSearch: true, fixed: 'left' },
    { title: '编号', dataIndex: 'code', render: (_, row) => <Tag>{row.code || '-'}</Tag> },
    {
      title: '监测指标',
      dataIndex: 'metric',
      valueType: 'select',
      valueEnum: { 1: { text: '振动' }, 2: { text: '温度' } },
      render: (_, row) => {
        const info = METRIC_MAP[row.metric] || { text: `${row.metric}`, color: 'default' };
        return <Tag color={info.color}>{info.text}</Tag>;
      },
    },
    { title: '突变', dataIndex: 'rt_max_delta', hideInSearch: true },
    { title: '短时最大斜率', dataIndex: 'st_max_slope', hideInSearch: true },
    { title: '短时最大振幅', dataIndex: 'st_max_amplitude', hideInSearch: true },
    { title: '中期最大斜率', dataIndex: 'mt_max_slope', hideInSearch: true },
    { title: '中期最大振幅', dataIndex: 'mt_max_amplitude', hideInSearch: true },
    { title: '阈值', dataIndex: 'baseline', hideInSearch: true },
    {
      title: '操作',
      valueType: 'option',
      width: OPERATION_COL_WIDTH,
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="middle">
          <a
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            title="确认删除该阀值定义吗？"
            onConfirm={async () => {
              try {
                await deleteSensorThreshold(row.id);
                message.success('删除成功');
                actionRef.current?.reload();
              } catch (error) {
                message.error(toErrorMessage(error));
              }
            }}
          >
            <a style={{ color: '#ff4d4f' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="阀值定义">
      <ProTable<SensorThreshold>
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        request={querySensorThresholds}
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
            code: values.code.trim(),
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
        <ProFormText name="code" label="编号" rules={[{ required: true, message: '请输入编号' }]} />
        <ProFormSelect name="metric" label="监测指标" rules={[{ required: true, message: '请选择监测指标' }]} options={METRIC_OPTIONS} />
        <ProFormDigit name="rt_max_delta" label="突变容忍值" rules={[{ required: true, message: '请输入实时最大偏差' }]} fieldProps={{ precision: 4 }} />
        <ProFormDigit name="st_max_slope" label="短时最大斜率 (24h)" rules={[{ required: true, message: '请输入短时最大斜率' }]} fieldProps={{ precision: 4 }} />
        <ProFormDigit name="st_max_amplitude" label="短时最大振幅 (24h)" rules={[{ required: true, message: '请输入短时最大振幅' }]} fieldProps={{ precision: 4 }} />
        <ProFormDigit name="mt_max_slope" label="中期最大斜率 (72h)" rules={[{ required: true, message: '请输入中期最大斜率' }]} fieldProps={{ precision: 4 }} />
        <ProFormDigit name="mt_max_amplitude" label="中期最大振幅 (72h)" rules={[{ required: true, message: '请输入中期最大振幅' }]} fieldProps={{ precision: 4 }} />
        <ProFormDigit name="baseline" label="阈值" rules={[{ required: true, message: '请输入阈值' }]} fieldProps={{ precision: 4 }} />
      </ModalForm>
    </PageContainer>
  );
};

export default MonitoringThresholdPage;

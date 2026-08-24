import { useRef, useState } from 'react';
import {
  ActionType,
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormSwitch,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, Tag, message } from 'antd';
import {
  HealthCheckFreq,
  HealthCheckFreqPayload,
  createHealthCheckFreq,
  deleteHealthCheckFreq,
  queryHealthCheckFreqs,
  updateHealthCheckFreq,
} from '@/services/healthCheckFreq';
import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

type HealthCheckFreqFormValues = {
  patrol: number;
  diagnosis: number;
  report: number;
  status: boolean;
};

const validateMinuteValue = (_: unknown, value: number | undefined) => {
  if (value === undefined || value === null || value === 0) {
    return Promise.reject(new Error('请输入大于0的数值'));
  }
  if (value < 60 && 60 % value !== 0) {
    return Promise.reject(new Error('小于60分钟时，必须为60的约数'));
  }
  if (value >= 60 && value % 60 !== 0) {
    return Promise.reject(new Error('大于等于60分钟时，必须为60的整数倍'));
  }
  return Promise.resolve();
};

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const MonitoringFrequencyPage = () => {
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<HealthCheckFreq | null>(null);

  const columns: ProColumns<HealthCheckFreq>[] = [
    { title: '序号', valueType: 'indexBorder', width: 68, hideInSearch: true, fixed: 'left' },
    { title: '巡检频率', dataIndex: 'patrol', width: 140, valueType: 'digit', render: (_, row) => `${row.patrol} 分钟` },
    { title: '诊断频率', dataIndex: 'diagnosis', width: 140, valueType: 'digit', render: (_, row) => `${row.diagnosis} 分钟` },
    { title: '上报频率', dataIndex: 'report', width: 120, valueType: 'digit', render: (_, row) => `累积${row.report} 次/上报` },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        true: { text: '启用' },
        false: { text: '停用' },
      },
      render: (_, row) => (row.status ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>),
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
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            title="确认删除该监测频率吗？"
            onConfirm={async () => {
              try {
                await deleteHealthCheckFreq(row.id);
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
    <PageContainer title="监测频率">
      <ProTable<HealthCheckFreq>
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        request={queryHealthCheckFreqs}
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
            新建频率
          </Button>,
        ]}
      />

      <ModalForm<HealthCheckFreqFormValues>
        title={editing ? '编辑监测频率' : '新建监测频率'}
        open={modalOpen}
        initialValues={
          editing
            ? {
                patrol: editing.patrol,
                diagnosis: editing.diagnosis,
                report: editing.report,
                status: editing.status,
              }
            : { patrol: 60, diagnosis: 1440, report: 1, status: true }
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
          const payload: HealthCheckFreqPayload = {
            patrol: values.patrol,
            diagnosis: values.diagnosis,
            report: values.report,
            status: values.status ?? true,
          };
          setSaving(true);
          try {
            if (editing) {
              await updateHealthCheckFreq(editing.id, payload);
            } else {
              await createHealthCheckFreq(payload);
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
        <ProFormDigit name="patrol" label="巡检频率(分钟)" min={1} fieldProps={{ precision: 2 }} rules={[{ required: true, message: '请输入巡检频率' }, { validator: validateMinuteValue }]} />
        <ProFormDigit name="diagnosis" label="诊断频率(分钟)" min={1} fieldProps={{ precision: 2 }} rules={[{ required: true, message: '请输入诊断频率' }, { validator: validateMinuteValue }]} />
        <ProFormDigit name="report" label="上报批次" min={1} fieldProps={{ precision: 0 }} rules={[{ required: true, message: '请输入上报批次' }]} />
        <ProFormSwitch name="status" label="启用状态" />
      </ModalForm>
    </PageContainer>
  );
};

export default MonitoringFrequencyPage;

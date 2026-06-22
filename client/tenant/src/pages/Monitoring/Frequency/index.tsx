import { useEffect, useMemo, useState } from 'react';
import {
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
  listAllHealthCheckFreqs,
  updateHealthCheckFreq,
} from '@/services/healthCheckFreq';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
type HealthCheckFreqFormValues = {
  patrol: number;
  diagnosis: number;
  report: number;
  status: boolean;
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

const validateMinuteValue = (_: any, value: number | undefined) => {
  if (value === undefined || value === null || value === 0) {
    return Promise.reject(new Error('请输入大于0的数值'));
  }
  if (value < 60) {
    if (60 % value !== 0) {
      return Promise.reject(new Error('小于60分钟时，必须为60的约数（如1,2,3,4,5,6,10,12,15,20,30）'));
    }
  } else {
    if (value % 60 !== 0) {
      return Promise.reject(new Error('大于等于60分钟时，必须为60的整数倍'));
    }
  }
  return Promise.resolve();
};

const MonitoringFrequencyPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<HealthCheckFreq[]>([]);
  const [editing, setEditing] = useState<HealthCheckFreq | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listAllHealthCheckFreqs());
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
    return rows.filter((row) => {
      if (query.patrol !== undefined && query.patrol !== null && String(row.patrol) !== String(query.patrol)) {
        return false;
      }
      if (
        query.diagnosis !== undefined &&
        query.diagnosis !== null &&
        String(row.diagnosis) !== String(query.diagnosis)
      ) {
        return false;
      }
      if (query.report !== undefined && query.report !== null && String(row.report) !== String(query.report)) {
        return false;
      }
      if (query.status !== undefined && query.status !== null && row.status !== query.status) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<HealthCheckFreq>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '巡检频率',
      dataIndex: 'patrol',
      width: 140,
      valueType: 'digit',
      sorter: (a, b) => Number(a.patrol) - Number(b.patrol),
      render: (_, row) => `${row.patrol} 分钟`,
    },
    {
      title: '诊断频率',
      dataIndex: 'diagnosis',
      width: 140,
      valueType: 'digit',
      sorter: (a, b) => Number(a.diagnosis) - Number(b.diagnosis),
      render: (_, row) => `${row.diagnosis} 分钟`,
    },
    {
      title: '上报频率',
      dataIndex: 'report',
      width: 120,
      valueType: 'digit',
      sorter: (a, b) => Number(a.report) - Number(b.report),
      render: (_, row) => `累积${row.report} 次/上报`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueEnum: {
        true: { text: '启用' },
        false: { text: '停用' },
      },
      render: (_: any, row: any) =>
        row.status ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
      sorter: (a, b) => Number(a.status) - Number(b.status),
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
            title="确认删除该监测频率吗？"
            onConfirm={async () => {
              try {
                await deleteHealthCheckFreq(row.id);
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
    <PageContainer title="监测频率">
      <ProTable<HealthCheckFreq>
        rowKey="id"
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        loading={loading}
        columns={columns}
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
            : {
              patrol: 60,
              diagnosis: 1440,
              report: 1,
              status: true,
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
        <ProFormDigit
          name="patrol"
          label="巡检频率(分钟)"
          min={1}
          fieldProps={{ precision: 2 }}
          rules={[
            { required: true, message: '请输入巡检频率' },
            { validator: validateMinuteValue },
          ]}
        />
        <ProFormDigit
          name="diagnosis"
          label="诊断频率(分钟)"
          min={1}
          fieldProps={{ precision: 2 }}
          rules={[
            { required: true, message: '请输入诊断频率' },
            { validator: validateMinuteValue },
          ]}
        />
        <ProFormDigit
          name="report"
          label="上报批次"
          min={1}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入上报批次' }]}
        />
        <ProFormSwitch name="status" label="启用状态" />
      </ModalForm>
    </PageContainer>
  );
};

export default MonitoringFrequencyPage;

import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormSwitch,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Tag, message } from 'antd';

import {
  HealthCheckFreq,
  HealthCheckFreqPayload,
  createHealthCheckFreq,
  deleteHealthCheckFreq,
  listAllHealthCheckFreqs,
  updateHealthCheckFreq,
} from '@/services/healthCheckFreq';

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
      title: '巡检频率(分钟)',
      dataIndex: 'patrol',
      width: 140,
      valueType: 'digit',
    },
    {
      title: '诊断频率(分钟)',
      dataIndex: 'diagnosis',
      width: 140,
      valueType: 'digit',
    },
    {
      title: '上报批次',
      dataIndex: 'report',
      width: 120,
      valueType: 'digit',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueEnum: {
        true: { text: '启用' },
        false: { text: '停用' },
      },
      render: (_, row) => (row.status ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '操作',
      valueType: 'option',
      width: 180,
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
          <Button danger type="link">
            删除
          </Button>
        </Popconfirm>,
      ],
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
        dataSource={filteredRows}
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
          destroyOnClose: true,
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
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入巡检频率' }]}
        />
        <ProFormDigit
          name="diagnosis"
          label="诊断频率(分钟)"
          min={1}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入诊断频率' }]}
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

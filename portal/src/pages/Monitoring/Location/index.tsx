import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, Tag, message } from 'antd';

import {
  createLocation,
  deleteLocation,
  listAllLocations,
  Location,
  LocationPayload,
  updateLocation,
} from '@/services/location';

import { renderRefSafeTableOptions } from '@/utils/proTableOptions';
type LocationFormValues = {
  name: string;
  description?: string;
  status: number;
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

const MonitoringLocationPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<Location[]>([]);
  const [editing, setEditing] = useState<Location | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listAllLocations());
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
      if (query.description && !norm(row.description).includes(norm(query.description))) {
        return false;
      }
      if (
        query.status !== undefined &&
        query.status !== null &&
        query.status !== '' &&
        String(row.status) !== String(query.status)
      ) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<Location>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '测点名称',
      dataIndex: 'name',
      width: 220,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        1: { text: '启用' },
        0: { text: '停用' },
      },
      render: (_, row) =>
        Number(row.status) === 1 ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '操作',
      valueType: 'option',
      width: 180,
      fixed: 'right',
      render: (_, row) => (
        <Space size="middle">
          <Button
            key="edit"
            type="link"
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </Button>
          <Popconfirm
            key="delete"
            title="确认删除该故障测点吗？"
            onConfirm={async () => {
              try {
                await deleteLocation(row.id);
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
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="故障测点">
      <ProTable<Location>
        rowKey="id"
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        loading={loading}
        columns={columns}
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
            新建测点
          </Button>,
        ]}
      />

      <ModalForm<LocationFormValues>
        title={editing ? '编辑故障测点' : '新建故障测点'}
        open={modalOpen}
        initialValues={
          editing
            ? {
                name: editing.name,
                description: editing.description,
                status: Number(editing.status),
              }
            : {
                status: 1,
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
          const payload: LocationPayload = {
            name: values.name.trim(),
            description: values.description?.trim() || undefined,
            status: Number(values.status ?? 1),
          };

          setSaving(true);
          try {
            if (editing) {
              await updateLocation(editing.id, payload);
            } else {
              await createLocation(payload);
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
          name="name"
          label="测点名称"
          rules={[
            { required: true, message: '请输入测点名称' },
            { max: 64, message: '测点名称最多64个字符' },
          ]}
        />
        <ProFormText
          name="description"
          label="描述"
          rules={[{ max: 255, message: '描述最多255个字符' }]}
        />
        <ProFormSelect
          name="status"
          label="状态"
          options={[
            { label: '启用', value: 1 },
            { label: '停用', value: 0 },
          ]}
          rules={[{ required: true, message: '请选择状态' }]}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default MonitoringLocationPage;

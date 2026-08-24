import { useRef, useState } from 'react';
import {
  ActionType,
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, Tag, message } from 'antd';
import {
  Location,
  LocationPayload,
  createLocation,
  disableLocation,
  queryLocations,
  updateLocation,
} from '@/services/location';
import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

type LocationFormValues = {
  name: string;
  description?: string;
  is_bearing_point: boolean;
  status: number;
};

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const MonitoringLocationPage = () => {
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<Location | null>(null);

  const columns: ProColumns<Location>[] = [
    { title: '序号', valueType: 'indexBorder', width: 68, hideInSearch: true, fixed: 'left' },
    { title: '测点名称', dataIndex: 'name', width: 220, sorter: true },
    { title: '描述', dataIndex: 'description', ellipsis: true, render: (_, row) => row.description || '-' },
    {
      title: '轴承测点',
      dataIndex: 'is_bearing_point',
      width: 110,
      valueType: 'select',
      valueEnum: {
        true: { text: '是' },
        false: { text: '否' },
      },
      render: (_, row) => (row.is_bearing_point ? <Tag color="blue">是</Tag> : <Tag>否</Tag>),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        1: { text: '启用' },
        0: { text: '禁用' },
      },
      render: (_, row) => (Number(row.status) === 1 ? <Tag color="success">启用</Tag> : <Tag>禁用</Tag>),
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
          {Number(row.status) === 1 && (
            <Popconfirm
              title="确认禁用该测点吗？历史引用和诊断数据不会删除。"
              onConfirm={async () => {
                try {
                  await disableLocation(row.id);
                  message.success('测点已禁用');
                  actionRef.current?.reload();
                } catch (error) {
                  message.error(toErrorMessage(error));
                }
              }}
            >
              <a style={{ color: '#fa8c16' }}>禁用</a>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="测点设置">
      <ProTable<Location>
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        request={queryLocations}
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
            新建测点
          </Button>,
        ]}
      />

      <ModalForm<LocationFormValues>
        title={editing ? '编辑测点' : '新建测点'}
        open={modalOpen}
        initialValues={
          editing
            ? {
                name: editing.name,
                description: editing.description,
                is_bearing_point: editing.is_bearing_point,
                status: Number(editing.status),
              }
            : { status: 1, is_bearing_point: false }
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
            is_bearing_point: values.is_bearing_point ?? false,
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
        <ProFormText name="name" label="测点名称" rules={[{ required: true, message: '请输入测点名称' }]} />
        <ProFormText name="description" label="描述" />
        <ProFormSwitch name="is_bearing_point" label="轴承测点" />
        <ProFormSelect
          name="status"
          label="状态"
          options={[
            { label: '启用', value: 1 },
            { label: '禁用', value: 0 },
          ]}
          rules={[{ required: true, message: '请选择状态' }]}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default MonitoringLocationPage;

import { useRef, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ActionType,
  ProColumns,
  ProForm,
  ProFormDependency,
  ProFormSelect,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import EntityPicker from '@/components/EntityPicker';

import { Area, AreaPayload, createArea, deleteArea, queryAreas, updateArea } from '@/services/area';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

const NETWORK_OPTIONS = [
  { label: '4G', value: 1 },
  { label: 'Wi-Fi', value: 2 },
];

type AreaFormValues = {
  name: string;
  description?: string;
  network?: number;
  ssid?: string;
  passwd?: string;
  parent_id?: string;
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

const MonitoringAreaPage = () => {
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<Area | null>(null);
  const [createChildParent, setCreateChildParent] = useState<Area | null>(null);
  const columns: ProColumns<Area>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 100,
      hideInSearch: true,
      fixed: 'left',
    },
    { title: '区域名称', dataIndex: 'name', width: 180, sorter: true },
    {
      title: '网络类型',
      dataIndex: 'network',
      width: 120,
      valueEnum: {
        1: { text: '4G' },
        2: { text: 'Wi-Fi' },
      },
      render: (_, row) => (row.network === 2 ? 'Wi-Fi' : '4G'),
      sorter: true,
    },
    {
      title: '上级区域',
      dataIndex: 'parent_id',
      width: 180,
      render: (_, row) => row.parent?.name || row.parent_id || '-',
    },
    {
      title: 'Wi-Fi SSID',
      dataIndex: 'ssid',
      width: 180,
      render: (_, row) => row.ssid || '-',
      sorter: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
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
            key="create-child"
            onClick={() => {
              setEditing(null);
              setCreateChildParent(row);
              setModalOpen(true);
            }}
          >
            新建
          </a>
          <a
            key="edit"
            onClick={() => {
              setCreateChildParent(null);
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            key="delete"
            title="确认删除该工作区域吗？"
            onConfirm={async () => {
              try {
                await deleteArea(row.id);
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
    <PageContainer title="工作区域">
      <ProTable
        rowKey="id"
        search={{ labelWidth: 'auto' }}
        columns={columns}
        actionRef={actionRef}
        request={queryAreas}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        options={{ reload: () => actionRef.current?.reload() }}
        optionsRender={renderRefSafeTableOptions}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditing(null);
              setCreateChildParent(null);
              setModalOpen(true);
            }}
          >
            新建区域
          </Button>,
        ]}
      />

      <ModalForm<AreaFormValues>
        title={
          editing
            ? '编辑工作区域'
            : createChildParent
              ? `新建子区域（上级：${createChildParent.name}）`
              : '新建工作区域'
        }
        open={modalOpen}
        initialValues={
          editing
            ? {
                name: editing.name,
                description: editing.description,
                network: editing.network,
                ssid: editing.ssid,
                passwd: editing.passwd,
                parent_id: editing.parent_id || undefined,
              }
            : createChildParent
              ? {
                parent_id: createChildParent.id,
              }
              : {}
        }
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setModalOpen(false);
            setEditing(null);
            setCreateChildParent(null);
          },
        }}
        submitter={{
          submitButtonProps: { loading: saving },
          searchConfig: { submitText: '保存' },
        }}
        onFinish={async (values) => {
          const payload: AreaPayload = {
            name: values.name.trim(),
            description: values.description?.trim() || undefined,
            network: values.network ?? 1,
            ssid: values.ssid?.trim() || undefined,
            passwd: values.passwd?.trim() || undefined,
            parent_id: values.parent_id?.trim() || undefined,
          };

          setSaving(true);
          try {
            if (editing) {
              await updateArea(editing.id, payload);
            } else {
              await createArea(payload);
            }
            message.success('保存成功');
            setModalOpen(false);
            setEditing(null);
            setCreateChildParent(null);
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
        <ProFormText
          name="name"
          label="区域名称"
          rules={[
            { required: true, message: '请输入区域名称' },
            { max: 64, message: '区域名称最多64个字符' },
          ]}
        />
        <ProForm.Item name="parent_id" label="上级区域">
          <EntityPicker<Area>
            placeholder="可选，点击选择上级区域"
            modalTitle="选择上级区域"
            triggerText="选择"
            valueLabel={
              editing?.parent
                ? editing.parent.name
                : createChildParent
                  ? createChildParent.name
                  : undefined
            }
            columns={[
              { title: '区域名称', dataIndex: 'name' },
              {
                title: '上级区域',
                dataIndex: 'parent_id',
                render: (_, row) => row.parent?.name || row.parent_id || '-',
              },
              { title: '描述', dataIndex: 'description', render: (_, row) => row.description || '-' },
            ]}
            getRecordLabel={(record) => record.name}
            fetcher={async ({ current, pageSize, keyword }) => {
              const result = await queryAreas({ current, pageSize, keyword });
              return {
                items: result.data,
                total: result.total,
              };
            }}
          />
        </ProForm.Item>
        <ProFormSelect
          name="network"
          label="网络类型"
          options={NETWORK_OPTIONS}
          initialValue={1}
          rules={[{ required: true, message: '请选择网络类型' }]}
        />
        <ProFormDependency name={['network']}>
          {({ network }) => {
            const isWifi = network === 2;
            return (
              <>
                <ProFormText
                  name="ssid"
                  label="Wi-Fi SSID"
                  rules={isWifi ? [{ required: true, message: 'Wi-Fi 模式下请输入 SSID' }] : []}
                />
                <ProFormText
                  name="passwd"
                  label="Wi-Fi 密码"
                  rules={isWifi ? [{ required: true, message: 'Wi-Fi 模式下请输入密码' }] : []}
                />
              </>
            );
          }}
        </ProFormDependency>
        <ProFormText
          name="description"
          label="描述"
          rules={[{ max: 255, message: '描述最多255个字符' }]}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default MonitoringAreaPage;

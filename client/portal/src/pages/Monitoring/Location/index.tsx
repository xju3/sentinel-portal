import { useEffect, useMemo, useState } from 'react';
import {
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
  createLocation,
  deleteLocation,
  listAllLocations,
  Location,
  LocationPayload,
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
  const [sort, setSort] = useState<Record<string, any>>({});

  const loadRows = async (currentSort = sort) => {
    setLoading(true);
    try {
      // 注意：这里需要你同步修改服务层的 listAllLocations 方法，让它把排序参数发给后端
      setRows(await listAllLocations({ sort_field: currentSort.field, sort_order: currentSort.order }));
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
        query.is_bearing_point !== undefined &&
        query.is_bearing_point !== null &&
        query.is_bearing_point !== '' &&
        String(row.is_bearing_point) !== String(query.is_bearing_point)
      ) {
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
      sorter: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
      sorter: true,
    },
    {
      title: '轴承测点',
      dataIndex: 'is_bearing_point',
      width: 110,
      valueType: 'select',
      valueEnum: {
        true: { text: '是' },
        false: { text: '否' },
      },
      render: (_, row) =>
        row.is_bearing_point ? <Tag color="blue">是</Tag> : <Tag>否</Tag>,
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
      sorter: true,
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
            <a style={{ color: '#ff4d4f' }}>
              删除
            </a>
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
        onChange={(pagination, filters, sorter: any) => {
          // 捕获服务端的排序指令并触发数据刷新
          const currentSort = sorter.order ? { field: sorter.field, order: sorter.order } : {};
          setSort(currentSort);
          loadRows(currentSort);
        }}
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
                is_bearing_point: editing.is_bearing_point,
                status: Number(editing.status),
              }
            : {
                status: 1,
                is_bearing_point: false,
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
        <ProFormSwitch
          name="is_bearing_point"
          label="轴承测点"
          tooltip="启用后，该测点可用于设备规格绑定轴承"
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

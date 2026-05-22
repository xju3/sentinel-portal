import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, message } from 'antd';

import { Area, AreaPayload, createArea, deleteArea, listAllAreas, updateArea } from '@/services/area';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
type AreaFormValues = {
  name: string;
  description?: string;
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
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<Area[]>([]);
  const [editing, setEditing] = useState<Area | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});

  const areaMap = useMemo(() => new Map(rows.map((item) => [item.id, item.name])), [rows]);

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listAllAreas());
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
      if (query.ssid && !norm(row.ssid).includes(norm(query.ssid))) {
        return false;
      }
      if (query.parent_id) {
        const parentName = row.parent_id ? areaMap.get(row.parent_id) || '' : '';
        const hit =
          norm(parentName).includes(norm(query.parent_id)) ||
          norm(row.parent_id).includes(norm(query.parent_id));
        if (!hit) {
          return false;
        }
      }
      return true;
    });
  }, [areaMap, query, rows]);

  const columns: ProColumns<Area>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    { title: '区域名称', dataIndex: 'name', width: 180 },
    {
      title: '上级区域',
      dataIndex: 'parent_id',
      width: 180,
      render: (_, row) => (row.parent_id ? areaMap.get(row.parent_id) || row.parent_id : '-'),
    },
    {
      title: 'Wi-Fi SSID',
      dataIndex: 'ssid',
      width: 180,
      render: (_, row) => row.ssid || '-',
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
            title="确认删除该工作区域吗？"
            onConfirm={async () => {
              try {
                await deleteArea(row.id);
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
    <PageContainer title="工作区域">
      <ProTable<Area>
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
            新建区域
          </Button>,
        ]}
      />

      <ModalForm<AreaFormValues>
        title={editing ? '编辑工作区域' : '新建工作区域'}
        open={modalOpen}
        initialValues={
          editing
            ? {
                name: editing.name,
                description: editing.description,
                ssid: editing.ssid,
                passwd: editing.passwd,
                parent_id: editing.parent_id || undefined,
              }
            : {}
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
          const payload: AreaPayload = {
            name: values.name.trim(),
            description: values.description?.trim() || undefined,
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
          label="区域名称"
          rules={[
            { required: true, message: '请输入区域名称' },
            { max: 64, message: '区域名称最多64个字符' },
          ]}
        />
        <ProFormText name="parent_id" label="上级区域ID" />
        <ProFormText name="ssid" label="Wi-Fi SSID" />
        <ProFormText name="passwd" label="Wi-Fi 密码" />
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

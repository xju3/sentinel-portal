import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProForm,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import EntityPicker from '@/components/EntityPicker';

import { Area, AreaPayload, createArea, deleteArea, listAllAreas, updateArea } from '@/services/area';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

type AreaTreeRow = Area & {
  children?: AreaTreeRow[];
};

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

const buildAreaTree = (rows: Area[]): AreaTreeRow[] => {
  const nodeMap = new Map<string, AreaTreeRow>();
  rows.forEach((item) => nodeMap.set(item.id, { ...item, children: [] }));

  const roots: AreaTreeRow[] = [];
  rows.forEach((item) => {
    const node = nodeMap.get(item.id);
    if (!node) {
      return;
    }
    const pid = item.parent_id || undefined;
    if (pid && nodeMap.has(pid)) {
      const parent = nodeMap.get(pid);
      if (parent) {
        parent.children = parent.children || [];
        parent.children.push(node);
      }
      return;
    }
    roots.push(node);
  });

  const sortTree = (nodes: AreaTreeRow[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
    nodes.forEach((item) => {
      if (item.children && item.children.length > 0) {
        sortTree(item.children);
      }
    });
  };
  sortTree(roots);
  return roots;
};

const MonitoringAreaPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<Area[]>([]);
  const [editing, setEditing] = useState<Area | null>(null);
  const [createChildParent, setCreateChildParent] = useState<Area | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});

  const areaMap = useMemo(() => new Map(rows.map((item) => [item.id, item.name])), [rows]);
  const treeData = useMemo(() => buildAreaTree(rows), [rows]);

  // 计算编辑时不能选择的节点（自己和所有子孙节点）
  const blockedAreaIds = useMemo(() => {
    const blockedIds = new Set<string>();
    if (!editing?.id) {
      return blockedIds;
    }

    blockedIds.add(editing.id);
    const childrenMap = new Map<string, string[]>();
    rows.forEach((item) => {
      if (!item.parent_id) {
        return;
      }
      const siblings = childrenMap.get(item.parent_id) || [];
      siblings.push(item.id);
      childrenMap.set(item.parent_id, siblings);
    });

    const queue = [...(childrenMap.get(editing.id) || [])];
    while (queue.length > 0) {
      const current = queue.shift();
      if (!current || blockedIds.has(current)) {
        continue;
      }
      blockedIds.add(current);
      queue.push(...(childrenMap.get(current) || []));
    }
    return blockedIds;
  }, [rows, editing?.id]);

  // 过滤掉被禁用的节点（自己和子孙），用于树形选择器
  const filterBlockedFromTree = (nodes: AreaTreeRow[]): AreaTreeRow[] => {
    return nodes
      .filter((n) => !blockedAreaIds.has(n.id))
      .map((n) => ({
        ...n,
        children: n.children ? filterBlockedFromTree(n.children) : [],
      }));
  };

  const pickerTreeData = useMemo(() => {
    if (blockedAreaIds.size === 0) return treeData;
    return filterBlockedFromTree(treeData);
  }, [treeData, blockedAreaIds]);

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

  const filteredTreeData = useMemo(() => {
    const hasQuery = Object.keys(query).length > 0;
    if (!hasQuery) {
      return treeData;
    }

    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows
      .filter((row) => {
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
      })
      .map((row) => ({ ...row }));
  }, [areaMap, query, rows, treeData]);

  const columns: ProColumns<AreaTreeRow>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 100,
      hideInSearch: true,
      fixed: 'left',
    },
    { title: '区域名称', dataIndex: 'name', width: 180, sorter: (a, b) => (a.name || '').localeCompare(b.name || '', 'zh-CN') },
    {
      title: '上级区域',
      dataIndex: 'parent_id',
      width: 180,
      render: (_, row) => (row.parent_id ? areaMap.get(row.parent_id) || row.parent_id : '-'),
      sorter: (a, b) => {
        const labelA = a.parent_id ? areaMap.get(a.parent_id) || '' : '';
        const labelB = b.parent_id ? areaMap.get(b.parent_id) || '' : '';
        return labelA.localeCompare(labelB, 'zh-CN');
      },
    },
    {
      title: 'Wi-Fi SSID',
      dataIndex: 'ssid',
      width: 180,
      render: (_, row) => row.ssid || '-',
      sorter: (a, b) => (a.ssid || '').localeCompare(b.ssid || '', 'zh-CN'),
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
      hideInSearch: true,
      sorter: (a, b) => (a.description || '').localeCompare(b.description || '', 'zh-CN'),
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
                await loadRows();
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
      <ProTable<AreaTreeRow>
        rowKey="id"
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        loading={loading}
        columns={columns}
        dataSource={filteredTreeData}
        pagination={false}
        expandable={{
          childrenColumnName: 'children',
          defaultExpandAllRows: true,
          rowExpandable: (record) => !!(record.children && record.children.length > 0),
        }}
        options={{ reload: loadRows }}
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
        <ProForm.Item name="parent_id" label="上级区域">
          <EntityPicker<Area>
            placeholder="可选，点击选择上级区域"
            modalTitle="选择上级区域"
            triggerText="选择"
            valueLabel={
              editing?.parent_id
                ? areaMap.get(editing.parent_id)
                : createChildParent
                  ? createChildParent.name
                  : undefined
            }
            columns={[
              { title: '区域名称', dataIndex: 'name' },
              {
                title: '上级区域',
                dataIndex: 'parent_id',
                render: (_, row) => (row.parent_id ? areaMap.get(row.parent_id) || '-' : '-'),
              },
              { title: '描述', dataIndex: 'description', render: (_, row) => row.description || '-' },
            ]}
            treeData={pickerTreeData}
            treeColumns={[
              { title: '区域名称', dataIndex: 'name' },
              { title: '描述', dataIndex: 'description', render: (_, row) => row.description || '-' },
            ]}
            getRecordLabel={(record) => record.name}
            fetcher={async ({ current, pageSize, keyword }) => {
              const limit = pageSize;
              const skip = (current - 1) * limit;
              const items = (await import('@/services/area').then((m) =>
                m.listAllAreas(),
              )).filter((item) => {
                if (!keyword) return true;
                const kw = keyword.toLowerCase();
                return (
                  item.name.toLowerCase().includes(kw) ||
                  (item.description || '').toLowerCase().includes(kw)
                );
              });
              return { items, total: items.length };
            }}
          />
        </ProForm.Item>
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

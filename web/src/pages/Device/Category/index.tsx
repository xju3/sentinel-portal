import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProForm,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import EntityPicker from '@/components/EntityPicker';

import {
  DeviceCategory,
  DeviceCategoryPayload,
  createDeviceCategory,
  deleteDeviceCategory,
  listAllDeviceCategories,
  listHealthCheckFreqs,
  listIsoStandards,
  queryDeviceCategories,
  updateDeviceCategory,
} from '@/services/deviceCategory';

type CategoryTreeRow = DeviceCategory & {
  children?: CategoryTreeRow[];
};

type CategoryFormValues = {
  name: string;
  description?: string;
  parent_id?: string;
  health_check_freq_id: string;
  iso_standard_id?: string;
};

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | {
        data?: { detail?: string };
        info?: { errorMessage?: string };
        message?: string;
      }
    | undefined;
  return (
    e?.data?.detail ||
    e?.info?.errorMessage ||
    e?.message ||
    '请求失败，请稍后重试'
  );
};

const buildCategoryTree = (rows: DeviceCategory[]): CategoryTreeRow[] => {
  const nodeMap = new Map<string, CategoryTreeRow>();
  rows.forEach((item) => nodeMap.set(item.id, { ...item, children: [] }));

  const roots: CategoryTreeRow[] = [];
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

  const sortTree = (nodes: CategoryTreeRow[]) => {
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

const DeviceCategoryPage = () => {
  const [tableLoading, setTableLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<DeviceCategory | null>(null);
  const [createChildParent, setCreateChildParent] = useState<DeviceCategory | null>(null);

  const [categories, setCategories] = useState<DeviceCategory[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [healthFreqOptions, setHealthFreqOptions] = useState<
    { label: string; value: string }[]
  >([]);
  const [isoOptions, setIsoOptions] = useState<{ label: string; value: string }[]>([]);

  const treeData = useMemo(() => buildCategoryTree(categories), [categories]);
  const categoryMap = useMemo(
    () => new Map(categories.map((item) => [item.id, item])),
    [categories],
  );

  const blockedParentIds = useMemo(() => {
    const blockedIds = new Set<string>();
    if (!editing?.id) {
      return blockedIds;
    }

    blockedIds.add(editing.id);
    const childrenMap = new Map<string, string[]>();
    categories.forEach((item) => {
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
  }, [categories, editing?.id]);

  const loadCategories = async () => {
    setTableLoading(true);
    try {
      const data = await listAllDeviceCategories();
      setCategories(data || []);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setTableLoading(false);
    }
  };

  const loadReferences = async () => {
    try {
      const [freqs, isos] = await Promise.all([listHealthCheckFreqs(), listIsoStandards()]);
      setHealthFreqOptions(
        (freqs || []).map((item) => ({
          value: item.id,
          label: `巡检${item.patrol}m / 诊断${item.diagnosis}m / 上报${item.report}`,
        })),
      );
      setIsoOptions(
        (isos || []).map((item) => ({
          value: item.id,
          label: `${item.code} - ${item.name}`,
        })),
      );
    } catch (error) {
      message.error(toErrorMessage(error));
    }
  };

  useEffect(() => {
    loadCategories();
    loadReferences();
  }, []);

  const columns: ProColumns<CategoryTreeRow>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '分类名称',
      dataIndex: 'name',
      width: 220,
    },
    {
      title: '上级分类',
      dataIndex: 'parent_name',
      width: 220,
      render: (_, row) => {
        if (!row.parent_id) {
          return '-';
        }
        return categoryMap.get(row.parent_id)?.name || row.parent_id;
      },
    },
    {
      title: '巡检频率',
      dataIndex: 'health_check_freq_id',
      ellipsis: true,
      render: (_, row) => {
        const freq = row.health_check_freq;
        if (!freq) {
          return row.health_check_freq_id;
        }
        return `巡检${freq.patrol}m / 诊断${freq.diagnosis}m / 上报${freq.report}`;
      },
    },
    {
      title: 'ISO标准',
      dataIndex: 'iso_standard_id',
      ellipsis: true,
      render: (_, row) => row.iso_standard_id || '-',
    },
    {
      title: '备注',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '操作',
      valueType: 'option',
      width: 240,
      render: (_, row) => [
        <Button
          key="create-child"
          type="link"
          onClick={() => {
            setEditing(null);
            setCreateChildParent(row);
            setModalOpen(true);
          }}
        >
          新建
        </Button>,
        <Button
          key="edit"
          type="link"
          onClick={() => {
            setCreateChildParent(null);
            setEditing(row);
            setModalOpen(true);
          }}
        >
          编辑
        </Button>,
        <Popconfirm
          key="delete"
          title="确认删除该分类吗？"
          onConfirm={async () => {
            try {
              await deleteDeviceCategory(row.id);
              message.success('删除成功');
              await loadCategories();
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

  const filteredTreeData = useMemo(() => {
    const hasQuery = Object.keys(query).length > 0;
    if (!hasQuery) {
      return treeData;
    }

    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return categories
      .filter((row) => {
        const parentName = row.parent_id ? categoryMap.get(row.parent_id)?.name || '' : '';
        if (query.name && !norm(row.name).includes(norm(query.name))) {
          return false;
        }
        if (query.parent_name && !norm(parentName).includes(norm(query.parent_name))) {
          return false;
        }
        if (
          query.health_check_freq_id &&
          !norm(
            row.health_check_freq
              ? `巡检${row.health_check_freq.patrol}m 诊断${row.health_check_freq.diagnosis}m 上报${row.health_check_freq.report}`
              : row.health_check_freq_id,
          ).includes(norm(query.health_check_freq_id))
        ) {
          return false;
        }
        if (query.iso_standard_id && !norm(row.iso_standard_id).includes(norm(query.iso_standard_id))) {
          return false;
        }
        if (query.description && !norm(row.description).includes(norm(query.description))) {
          return false;
        }
        return true;
      })
      .map((row) => ({ ...row }));
  }, [categories, categoryMap, query, treeData]);

  const parentPickerColumns: ColumnsType<DeviceCategory> = [
    { title: '分类名称', dataIndex: 'name' },
    {
      title: '上级分类',
      dataIndex: 'parent_id',
      render: (_, row) => (row.parent_id ? categoryMap.get(row.parent_id)?.name || '-' : '-'),
    },
    {
      title: '描述',
      dataIndex: 'description',
      render: (_, row) => row.description || '-',
    },
  ];

  return (
    <PageContainer title="设备分类">
      <ProTable<CategoryTreeRow>
        rowKey="id"
        loading={tableLoading}
        columns={columns}
        dataSource={filteredTreeData}
        pagination={false}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadCategories }}
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
            新建分类
          </Button>,
        ]}
      />

      <ModalForm<CategoryFormValues>
        title={
          editing
            ? '编辑设备分类'
            : createChildParent
              ? `新建子分类（上级：${createChildParent.name}）`
              : '新建设备分类'
        }
        open={modalOpen}
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setModalOpen(false);
            setEditing(null);
            setCreateChildParent(null);
          },
        }}
        submitter={{
          searchConfig: {
            submitText: '保存',
          },
          submitButtonProps: {
            loading: saving,
          },
        }}
        initialValues={
          editing
            ? {
                name: editing.name,
                description: editing.description,
                parent_id: editing.parent_id || undefined,
                health_check_freq_id: editing.health_check_freq_id,
                iso_standard_id: editing.iso_standard_id || undefined,
              }
            : createChildParent
              ? {
                  parent_id: createChildParent.id,
                }
              : undefined
        }
        onFinish={async (values) => {
          const payload: DeviceCategoryPayload = {
            name: values.name.trim(),
            description: values.description || undefined,
            parent_id: values.parent_id || null,
            health_check_freq_id: values.health_check_freq_id,
            iso_standard_id: values.iso_standard_id || null,
          };
          setSaving(true);
          try {
            if (editing) {
              await updateDeviceCategory(editing.id, payload);
            } else {
              await createDeviceCategory(payload);
            }
            message.success('保存成功');
            setModalOpen(false);
            setEditing(null);
            setCreateChildParent(null);
            await loadCategories();
            return true;
          } catch (error) {
            message.error(toErrorMessage(error));
            return false;
          } finally {
            setSaving(false);
          }
        }}
      >
        <ProFormText name="name" label="分类名称" rules={[{ required: true, message: '请输入分类名称' }]} />
        <ProFormText name="description" label="备注" />
        <ProFormSelect
          name="health_check_freq_id"
          label="巡检频率"
          rules={[{ required: true, message: '请选择巡检频率' }]}
          options={healthFreqOptions}
        />
        <ProFormSelect name="iso_standard_id" label="ISO标准" options={isoOptions} />
        <ProForm.Item name="parent_id" label="上级分类">
          <EntityPicker<DeviceCategory>
            placeholder="可选，点击选择上级分类"
            modalTitle="选择上级分类"
            triggerText="选择"
            valueLabel={
              editing?.parent_id
                ? categoryMap.get(editing.parent_id)?.name
                : createChildParent
                  ? createChildParent.name
                  : undefined
            }
            columns={parentPickerColumns}
            getRecordLabel={(record) => record.name}
            fetcher={async ({ current, pageSize, keyword }) => {
              const result = await queryDeviceCategories({ current, pageSize, keyword });
              if (blockedParentIds.size === 0) {
                return result;
              }
              return {
                ...result,
                items: result.items.filter((item) => !blockedParentIds.has(item.id)),
              };
            }}
          />
        </ProForm.Item>
      </ModalForm>
    </PageContainer>
  );
};

export default DeviceCategoryPage;

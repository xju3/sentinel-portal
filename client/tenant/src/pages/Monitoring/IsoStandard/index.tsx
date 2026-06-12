import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Form, FormInstance, Popconfirm, Space, Tag, message } from 'antd';

import {
  IsoStandard,
  IsoStandardPayload,
  createIsoStandard,
  deleteIsoStandard,
  listAllIsoStandards,
  updateIsoStandard,
} from '@/services/isoStandard';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

const VERSION_LABELS: Record<number, string> = {
  1: 'ISO-10816',
  2: 'ISO-20816',
};

const FOUNDATION_LABELS: Record<number, string> = {
  0: '不可用',
  1: '刚性基础',
  2: '柔性基础',
};

// Category labels for version 1 (ISO-10816)
const CATEGORY_V1_LABELS: Record<number, string> = {
  1: 'Class I  — 15 到 75 kW 的小型机械',
  2: 'Class II — 功率不大于 300 kW 的中型机械',
  3: 'Class III — 功率大于 300 kW 的大型机械',
};

// Category labels for version 2 (ISO-20816)
const CATEGORY_V2_LABELS: Record<number, string> = {
  1: '大中型工业电机',
  2: '卧式离心泵',
  3: '立式旋转机械',
  4: '高速透平机械',
};

const getCategoryLabel = (version: number, category: number): string => {
  if (version === 1) return CATEGORY_V1_LABELS[category] || String(category);
  if (version === 2) return CATEGORY_V2_LABELS[category] || String(category);
  return String(category);
};

const getCategoryOptions = (version: number) => {
  if (version === 1) {
    return Object.entries(CATEGORY_V1_LABELS).map(([value, label]) => ({
      label,
      value: Number(value),
    }));
  }
  if (version === 2) {
    return Object.entries(CATEGORY_V2_LABELS).map(([value, label]) => ({
      label,
      value: Number(value),
    }));
  }
  return [];
};

type IsoStandardFormValues = {
  code: string;
  version: number;
  category: number;
  foundation: number;
  description?: string;
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

const IsoStandardPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<IsoStandard[]>([]);
  const [editing, setEditing] = useState<IsoStandard | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [sort, setSort] = useState<Record<string, any>>({});
  const formRef = useRef<FormInstance<IsoStandardFormValues>>();

  const loadRows = async (currentSort = sort) => {
    setLoading(true);
    try {
      setRows(
        await listAllIsoStandards(
          currentSort.field,
          currentSort.order,
        ),
      );
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
      if (query.code && !norm(row.code).includes(norm(query.code))) {
        return false;
      }
      if (query.version !== undefined && query.version !== null && row.version !== query.version) {
        return false;
      }
      if (query.category !== undefined && query.category !== null && row.category !== query.category) {
        return false;
      }
      if (query.foundation !== undefined && query.foundation !== null && row.foundation !== query.foundation) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<IsoStandard>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '标准代号',
      dataIndex: 'code',
      width: 140,
      sorter: true,
    },
    {
      title: '版本',
      dataIndex: 'version',
      width: 120,
      valueEnum: {
        1: { text: 'ISO-10816' },
        2: { text: 'ISO-20816' },
      },
      render: (_, row) => (
        <Tag color={row.version === 1 ? 'blue' : 'green'}>
          {VERSION_LABELS[row.version] || row.version}
        </Tag>
      ),
      sorter: true,
    },
    {
      title: '类别',
      dataIndex: 'category',
      width: 160,
      render: (_, row) => getCategoryLabel(row.version, row.category),
      sorter: true,
    },
    {
      title: '基础类型',
      dataIndex: 'foundation',
      width: 120,
      valueEnum: {
        1: { text: '刚性基础' },
        2: { text: '柔性基础' },
      },
      render: (_, row) => (
        <Tag>{FOUNDATION_LABELS[row.foundation] || row.foundation}</Tag>
      ),
      sorter: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
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
            title="确认删除该国际标准吗？"
            onConfirm={async () => {
              try {
                await deleteIsoStandard(row.id);
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
    <PageContainer title="国际标准">
      <ProTable<IsoStandard>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        onChange={(_pagination, _filters, sorter: any) => {
          const currentSort = sorter.order
            ? { field: sorter.field, order: sorter.order }
            : {};
          setSort(currentSort);
          loadRows(currentSort);
        }}
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
            新建国际标准
          </Button>,
        ]}
      />

      <ModalForm<IsoStandardFormValues>
        title={editing ? '编辑国际标准' : '新建国际标准'}
        open={modalOpen}
        formRef={formRef}
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
        initialValues={
          editing
            ? {
                code: editing.code,
                version: editing.version,
                category: editing.category,
                foundation: editing.foundation,
                description: editing.description,
              }
            : {
                version: 1,
                foundation: 1,
              }
        }
        onFinish={async (values) => {
          const payload: IsoStandardPayload = {
            code: values.code.trim(),
            version: values.version,
            category: values.category,
            foundation: values.foundation,
            description: values.description || undefined,
          };
          setSaving(true);
          try {
            if (editing) {
              await updateIsoStandard(editing.id, payload);
            } else {
              await createIsoStandard(payload);
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
          name="code"
          label="标准代号"
          placeholder="请输入标准代号（不超过8位）"
          fieldProps={{ maxLength: 8 }}
          rules={[
            { required: true, message: '请输入标准代号' },
            { max: 8, message: '标准代号不超过8位' },
          ]}
        />
        <ProFormSelect
          name="version"
          label="版本"
          options={[
            { label: 'ISO-10816', value: 1 },
            { label: 'ISO-20816', value: 2 },
          ]}
          rules={[{ required: true, message: '请选择版本' }]}
          fieldProps={{
            onChange: () => {
              // When version changes, reevaluate foundation
              setTimeout(() => {
                const form = formRef.current;
                if (!form) return;
                const v = form.getFieldValue('version');
                const c = form.getFieldValue('category');
                if (v === 1 && c === 1) {
                  form.setFieldValue('foundation', 0);
                } else {
                  form.setFieldValue('foundation', 1);
                }
              }, 0);
            },
          }}
        />
        <ProFormSelect
          name="category"
          label="类别"
          dependencies={['version']}
          request={async () => {
            const form = formRef.current;
            const v = form?.getFieldValue('version') || 1;
            return getCategoryOptions(v);
          }}
          rules={[{ required: true, message: '请选择类别' }]}
          fieldProps={{
            onChange: () => {
              // When category changes, reevaluate foundation
              setTimeout(() => {
                const form = formRef.current;
                if (!form) return;
                const v = form.getFieldValue('version');
                const c = form.getFieldValue('category');
                if (v === 1 && c === 1) {
                  form.setFieldValue('foundation', 0);
                } else {
                  form.setFieldValue('foundation', 1);
                }
              }, 0);
            },
          }}
        />
        <Form.Item
          noStyle
          shouldUpdate={(prev, cur) =>
            prev.version !== cur.version || prev.category !== cur.category || prev === cur
          }
        >
          {({ getFieldValue }) => {
            const version = getFieldValue('version') || 1;
            const category = getFieldValue('category');
            const isLocked = version === 1 && category === 1;
            const options = isLocked
              ? [{ label: '不可用', value: 0 }]
              : [
                  { label: '刚性基础', value: 1 },
                  { label: '柔性基础', value: 2 },
                ];
            return (
              <ProFormSelect
                name="foundation"
                label="基础类型"
                options={options}
                disabled={isLocked}
                rules={[{ required: true, message: '请选择基础类型' }]}
              />
            );
          }}
        </Form.Item>
        <ProFormTextArea name="description" label="描述" placeholder="可选描述信息" />
      </ModalForm>
    </PageContainer>
  );
};

export default IsoStandardPage;
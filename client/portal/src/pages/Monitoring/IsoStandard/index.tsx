import { useRef, useState } from 'react';
import {
  ActionType,
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, FormInstance, Popconfirm, Space, Tag, message } from 'antd';
import {
  IsoStandard,
  IsoStandardPayload,
  createIsoStandard,
  deleteIsoStandard,
  queryIsoStandards,
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

const CATEGORY_V1_LABELS: Record<number, string> = {
  1: 'Class I',
  2: 'Class II',
  3: 'Class III',
};

const CATEGORY_V2_LABELS: Record<number, string> = {
  1: '大中型工业电机',
  2: '卧式离心泵',
  3: '立式旋转机械',
  4: '高速透平机械',
};

type IsoStandardFormValues = {
  code: string;
  version: number;
  category: number;
  foundation: number;
  description?: string;
};

const getCategoryLabel = (version: number, category: number) => {
  if (version === 1) return CATEGORY_V1_LABELS[category] || String(category);
  if (version === 2) return CATEGORY_V2_LABELS[category] || String(category);
  return String(category);
};

const getCategoryOptions = (version: number) =>
  Object.entries(version === 1 ? CATEGORY_V1_LABELS : CATEGORY_V2_LABELS).map(([value, label]) => ({
    label,
    value: Number(value),
  }));

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const IsoStandardPage = () => {
  const actionRef = useRef<ActionType>();
  const formRef = useRef<FormInstance<IsoStandardFormValues>>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<IsoStandard | null>(null);

  const columns: ProColumns<IsoStandard>[] = [
    { title: '序号', valueType: 'indexBorder', width: 68, hideInSearch: true, fixed: 'left' },
    { title: '标准代号', dataIndex: 'code', width: 120, sorter: true },
    {
      title: '版本',
      dataIndex: 'version',
      width: 100,
      valueType: 'select',
      valueEnum: {
        1: { text: 'ISO-10816' },
        2: { text: 'ISO-20816' },
      },
      render: (_, row) => <Tag color={row.version === 1 ? 'blue' : 'green'}>{VERSION_LABELS[row.version]}</Tag>,
    },
    {
      title: '安装基础',
      dataIndex: 'foundation',
      width: 120,
      valueType: 'select',
      valueEnum: {
        1: { text: '刚性基础' },
        2: { text: '柔性基础' },
      },
      render: (_, row) => <Tag>{FOUNDATION_LABELS[row.foundation] || row.foundation}</Tag>,
    },
    {
      title: '类别',
      dataIndex: 'category',
      render: (_, row) => getCategoryLabel(row.version, row.category),
    },
    {
      title: '描述',
      dataIndex: 'description',
      width: 200,
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
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            title="确认删除该国际标准吗？"
            onConfirm={async () => {
              try {
                await deleteIsoStandard(row.id);
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
    <PageContainer title="国际标准">
      <ProTable<IsoStandard>
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        request={queryIsoStandards}
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
            新建国际标准
          </Button>,
        ]}
      />

      <ModalForm<IsoStandardFormValues>
        title={editing ? '编辑国际标准' : '新建国际标准'}
        open={modalOpen}
        formRef={formRef as any}
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
            : { version: 1, foundation: 1 }
        }
        onFinish={async (values) => {
          const payload: IsoStandardPayload = {
            code: values.code.trim(),
            version: values.version,
            category: values.category,
            foundation: values.foundation,
            description: values.description?.trim() || undefined,
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
        <ProFormText name="code" label="标准代号" rules={[{ required: true, message: '请输入标准代号' }]} />
        <ProFormSelect
          name="version"
          label="版本"
          options={[
            { label: 'ISO-10816', value: 1 },
            { label: 'ISO-20816', value: 2 },
          ]}
          rules={[{ required: true, message: '请选择版本' }]}
        />
        <ProFormSelect
          name="category"
          label="类别"
          dependencies={['version']}
          request={async () => {
            const version = (formRef.current as any)?.getFieldValue?.('version') || editing?.version || 1;
            return getCategoryOptions(version);
          }}
          rules={[{ required: true, message: '请选择类别' }]}
        />
        <ProFormSelect
          name="foundation"
          label="安装基础"
          options={[
            { label: '刚性基础', value: 1 },
            { label: '柔性基础', value: 2 },
          ]}
          rules={[{ required: true, message: '请选择安装基础' }]}
        />
        <ProFormTextArea name="description" label="描述" />
      </ModalForm>
    </PageContainer>
  );
};

export default IsoStandardPage;

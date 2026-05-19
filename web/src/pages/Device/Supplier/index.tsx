import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSwitch,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Tag, message } from 'antd';

import {
  Supplier,
  SupplierPayload,
  createSupplier,
  deleteSupplier,
  listAllSuppliers,
  updateSupplier,
} from '@/services/supplier';

type SupplierFormValues = {
  name: string;
  brand: string;
  contact_info?: string;
  active: boolean;
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

const DeviceSupplierPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<Supplier[]>([]);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listAllSuppliers());
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
      if (query.brand && !norm(row.brand).includes(norm(query.brand))) {
        return false;
      }
      if (query.contact_info && !norm(row.contact_info).includes(norm(query.contact_info))) {
        return false;
      }
      if (query.active !== undefined && query.active !== null && row.active !== query.active) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<Supplier>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '供应商名称',
      dataIndex: 'name',
      width: 180,
    },
    {
      title: '品牌',
      dataIndex: 'brand',
      width: 160,
    },
    {
      title: '联系方式',
      dataIndex: 'contact_info',
      ellipsis: true,
      render: (_, row) => row.contact_info || '-',
    },
    {
      title: '状态',
      dataIndex: 'active',
      width: 100,
      valueEnum: {
        true: { text: '启用' },
        false: { text: '停用' },
      },
      render: (_, row) => (row.active ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '操作',
      valueType: 'option',
      width: 170,
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
          title="确认删除该供应商吗？"
          onConfirm={async () => {
            try {
              await deleteSupplier(row.id);
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
    <PageContainer title="供应商">
      <ProTable<Supplier>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
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
            新建供应商
          </Button>,
        ]}
      />

      <ModalForm<SupplierFormValues>
        title={editing ? '编辑供应商' : '新建供应商'}
        open={modalOpen}
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
                name: editing.name,
                brand: editing.brand,
                contact_info: editing.contact_info,
                active: editing.active,
              }
            : {
                active: true,
              }
        }
        onFinish={async (values) => {
          const payload: SupplierPayload = {
            name: values.name.trim(),
            brand: values.brand.trim(),
            contact_info: values.contact_info || undefined,
            active: values.active ?? true,
          };
          setSaving(true);
          try {
            if (editing) {
              await updateSupplier(editing.id, payload);
            } else {
              await createSupplier(payload);
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
          label="供应商名称"
          rules={[{ required: true, message: '请输入供应商名称' }]}
        />
        <ProFormText name="brand" label="品牌" rules={[{ required: true, message: '请输入品牌' }]} />
        <ProFormText name="contact_info" label="联系方式" />
        <ProFormSwitch name="active" label="启用状态" />
      </ModalForm>
    </PageContainer>
  );
};

export default DeviceSupplierPage;

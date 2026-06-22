import { useEffect, useMemo, useState } from 'react';
import {
  PageContainer,
  ProColumns,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Form, Input, message, Modal, Popconfirm, Select, Switch, Tag, Tooltip } from 'antd';

import {
  Account,
  AccountPayload,
  AccountUpdatePayload,
  createAccount,
  deleteAccount,
  listAccounts,
  updateAccount,
  updateAccountPassword,
} from '@/services/account';
import { getSession } from '@/utils/session';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const AccountPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<Account[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<Account | null>(null);
  const [passwordEditing, setPasswordEditing] = useState<Account | null>(null);
  const [form] = Form.useForm();
  const [passwordForm] = Form.useForm();

  const currentAccountId = getSession()?.account_id;

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listAccounts());
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
      if (query.username && !norm(row.username).includes(norm(query.username))) {
        return false;
      }
      if (query.contact_name && !norm(row.contact_name || '').includes(norm(query.contact_name))) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<Account>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '用户名',
      dataIndex: 'username',
      width: 200,
    },
    {
      title: '联系人',
      dataIndex: 'contact_name',
      width: 150,
      render: (_, row) => row.contact_name || '-',
    },
    {
      title: '账号类型',
      dataIndex: 'flag',
      width: 100,
      hideInSearch: true,
      render: (_, row) => (row.flag === 1 ? <Tag color="blue">邮箱</Tag> : <Tag color="green">手机</Tag>),
    },
    {
      title: '管理员',
      dataIndex: 'admin',
      width: 80,
      hideInSearch: true,
      render: (_, row) => (row.admin ? <Tag color="red">是</Tag> : <Tag color="default">否</Tag>),
    },
    {
      title: '状态',
      dataIndex: 'active',
      width: 80,
      valueType: 'select',
      hideInSearch: true,
      valueEnum: {
        true: { text: '启用', status: 'Success' },
        false: { text: '停用', status: 'Error' },
      },
      render: (_, row) => {
        const isSelf = row.id === currentAccountId;
        const isLast = rows.length <= 1;
        const disabled = isSelf || isLast;
        const tooltipTitle = isSelf ? '不能停用自己的账号' : isLast ? '至少保留一个启用账号' : undefined;

        return (
          <Tooltip title={tooltipTitle}>
            <Switch
              checked={row.active}
              checkedChildren="启用"
              unCheckedChildren="停用"
              disabled={disabled}
              onChange={async (checked) => {
                try {
                  await updateAccount(row.id, { active: checked });
                  message.success('更新成功');
                  await loadRows();
                } catch (error) {
                  message.error(toErrorMessage(error));
                }
              }}
            />
          </Tooltip>
        );
      },
    },
    {
      title: '操作',
      valueType: 'option',
      // fixed: 'right',
      width: 180,
      render: (_, row) => [
        <a
          key="edit"
          onClick={() => {
            setEditing(row);
            setModalOpen(true);
          }}
        >
          编辑
        </a>,
        <a
          key="password"
          onClick={() => {
            setPasswordEditing(row);
            setPasswordModalOpen(true);
          }}
        >
          重置密码
        </a>,
        <Popconfirm
          key="delete"
          title="确认删除该用户吗？"
          onConfirm={async () => {
            try {
              await deleteAccount(row.id);
              message.success('删除成功');
              await loadRows();
            } catch (error) {
              message.error(toErrorMessage(error));
            }
          }}
        >
          <a style={{ color: 'red' }}>
            删除
          </a>
        </Popconfirm>,
      ],
    },
  ];

  return (
    <PageContainer title="用户管理" subTitle="管理当前租户下的所有用户账号">
      <ProTable<Account>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        scroll={{ x: 900 }}
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
            新建用户
          </Button>,
        ]}
      />

      <Modal
        title={editing ? '编辑用户' : '新建用户'}
        open={modalOpen}
        onOk={async () => {
          try {
            const values = await form.validateFields();
            setSaving(true);
            if (editing) {
              const payload: AccountUpdatePayload = {
                username: values.username.trim(),
                active: values.active,
              };
              await updateAccount(editing.id, payload);
              message.success('更新成功');
            } else {
              const payload: AccountPayload = {
                contact_name: values.contact_name.trim(),
                username: values.username.trim(),
                password: values.password,
              };
              await createAccount(payload);
              message.success('创建成功');
            }
            setModalOpen(false);
            setEditing(null);
            form.resetFields();
            await loadRows();
          } catch (error: any) {
            if (error?.errorFields) return;
            message.error(toErrorMessage(error));
          } finally {
            setSaving(false);
          }
        }}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
          form.resetFields();
        }}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {!editing && (
            <Form.Item
              name="contact_name"
              label="用户姓名"
              rules={[
                { required: true, message: '请输入用户姓名' },
                { max: 64, message: '用户姓名最多64个字符' },
              ]}
            >
              <Input placeholder="请输入用户姓名" />
            </Form.Item>
          )}
          <Form.Item
            name="username"
            label="用户名（电子邮件或移动电话）"
            rules={[
              { required: true, message: '请输入用户名' },
              { max: 255, message: '用户名最多255个字符' },
            ]}
          >
            <Input placeholder="请输入电子邮件或移动电话" />
          </Form.Item>
          {!editing && (
            <Form.Item
              name="password"
              label="密码"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 6, message: '密码至少6个字符' },
                { max: 255, message: '密码最多255个字符' },
              ]}
            >
              <Input.Password placeholder="请输入密码" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title={`重置密码 - ${passwordEditing?.username || ''}`}
        open={passwordModalOpen}
        onOk={async () => {
          if (!passwordEditing) return;
          setSaving(true);
          try {
            await updateAccountPassword(passwordEditing.id, passwordForm.getFieldValue('new_password'));
            message.success('密码重置成功');
            setPasswordModalOpen(false);
            setPasswordEditing(null);
            passwordForm.resetFields();
          } catch (error) {
            message.error(toErrorMessage(error));
          } finally {
            setSaving(false);
          }
        }}
        onCancel={() => {
          setPasswordModalOpen(false);
          setPasswordEditing(null);
          passwordForm.resetFields();
        }}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={passwordForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码至少6个字符' },
              { max: 255, message: '密码最多255个字符' },
            ]}
          >
            <Input.Password placeholder="请输入新密码" />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
};

export default AccountPage;

import { PlusOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import {
  Button,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';

import {
  createTenantAccount,
  deleteTenantAccount,
  listTenantAccounts,
  updateTenantAccount,
  type AccountInfo,
} from '@/services/tenant';
import { getSession } from '@/utils/session';

const USER_FLAG_MAP: Record<number, string> = {
  1: '邮箱',
  2: '手机号',
};

const TenantUsersPage = () => {
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const currentAccountId = useMemo(() => getSession()?.account_id, []);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const data = await listTenantAccounts();
      setAccounts(data);
    } catch (error: any) {
      const detail = error?.data?.detail || '获取用户列表失败';
      message.error(String(detail));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  const handleDelete = async (record: AccountInfo) => {
    try {
      await deleteTenantAccount(record.id);
      message.success('用户已删除');
      fetchAccounts();
    } catch (error: any) {
      const detail = error?.data?.detail || '删除失败';
      message.error(String(detail));
    }
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await createTenantAccount({
        username: values.username,
        password: values.password,
        email: values.email || undefined,
        mobile: values.mobile || undefined,
        flag: values.flag,
        active: true,
      });
      message.success('账号创建成功');
      setModalOpen(false);
      form.resetFields();
      fetchAccounts();
    } catch (error: any) {
      if (error?.errorFields) {
        // 表单验证错误，不处理
        return;
      }
      const detail = error?.data?.detail || '创建账号失败';
      message.error(String(detail));
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleActive = async (record: AccountInfo, checked: boolean) => {
    try {
      await updateTenantAccount(record.id, { active: checked });
      message.success('更新成功');
      fetchAccounts();
    } catch (error: any) {
      const detail = error?.data?.detail || '更新失败';
      message.error(String(detail));
    }
  };

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 180,
      sorter: (a: any, b: any) => (a.username || '').localeCompare(b.username || '', 'zh-CN'),
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 200,
      render: (text: string | null) => text || '-',
      sorter: (a: any, b: any) => (a.email || '').localeCompare(b.email || '', 'zh-CN'),
    },
    {
      title: '手机号',
      dataIndex: 'mobile',
      key: 'mobile',
      width: 160,
      render: (text: string | null) => text || '-',
      sorter: (a: any, b: any) => (a.mobile || '').localeCompare(b.mobile || '', 'zh-CN'),
    },
    {
      title: '登录方式',
      dataIndex: 'flag',
      key: 'flag',
      width: 120,
      render: (flag: number) => (
        <Tag color={flag === 1 ? 'green' : 'orange'}>
          {USER_FLAG_MAP[flag] || '未知'}
        </Tag>
      ),
      sorter: (a: any, b: any) => Number(a.flag) - Number(b.flag),
    },
    {
      title: '状态',
      dataIndex: 'active',
      key: 'active',
      width: 120,
      render: (active: boolean, record: AccountInfo) => {
        const isSelf = record.id === currentAccountId;
        const isLast = accounts.length <= 1;
        const disabled = isSelf || isLast;
        const tooltipTitle = isSelf ? '不能停用自己的账号' : isLast ? '至少保留一个启用账号' : undefined;

        return (
          <Tooltip title={tooltipTitle}>
            <Switch
              checked={active}
              checkedChildren="启用"
              unCheckedChildren="停用"
              disabled={disabled}
              onChange={(checked) => handleToggleActive(record, checked)}
            />
          </Tooltip>
        );
      },
      sorter: (a: any, b: any) => Number(a.active) - Number(b.active),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right',
      render: (_: any, record: AccountInfo) => {
        const isSelf = record.id === currentAccountId;
        if (isSelf) return null;
        return (
          <Space>
            <Popconfirm
              title="确认删除"
              description={`确定要删除用户 "${record.username}" 吗？`}
              onConfirm={() => handleDelete(record)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <PageContainer
      title="系统用户"
      ghost
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新增账号
        </Button>
      }
    >
      <ProCard>
        <Table
          dataSource={accounts}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={false}
          scroll={{ x: 'max-content' }}
        />
      </ProCard>

      <Modal
        title="新增账号"
        open={modalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setModalOpen(false);
          form.resetFields();
        }}
        confirmLoading={submitting}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="请输入用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码长度不能少于6位' },
            ]}
          >
            <Input.Password placeholder="请输入密码" />
          </Form.Item>

          <Form.Item
            name="flag"
            label="登录方式"
            initialValue={2}
            rules={[{ required: true, message: '请选择登录方式' }]}
          >
            <Select
              options={[
                { value: 1, label: '邮箱' },
                { value: 2, label: '手机号' },
              ]}
            />
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prev, curr) => prev.flag !== curr.flag}
          >
            {({ getFieldValue }) => {
              const flag = getFieldValue('flag');
              if (flag === 1) {
                return (
                  <Form.Item
                    name="email"
                    label="邮箱"
                    rules={[
                      { required: true, message: '请输入邮箱' },
                      { type: 'email', message: '邮箱格式不正确' },
                    ]}
                  >
                    <Input placeholder="请输入邮箱" />
                  </Form.Item>
                );
              }
              return (
                <Form.Item
                  name="mobile"
                  label="手机号"
                  rules={[
                    { required: true, message: '请输入手机号' },
                    { pattern: /^[0-9+()\-\s]{6,20}$/, message: '手机号格式不正确' },
                  ]}
                >
                  <Input placeholder="请输入手机号" />
                </Form.Item>
              );
            }}
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
};

export default TenantUsersPage;

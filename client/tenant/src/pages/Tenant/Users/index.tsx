import { PlusOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { QRCodeCanvas } from 'qrcode.react';
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
  getWxBindQrCode,
  checkWxBindStatus,
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
  const [bindModalOpen, setBindModalOpen] = useState(false);
  const [qrUrl, setQrUrl] = useState('');
  const [sceneStr, setSceneStr] = useState('');
  const [bindUser, setBindUser] = useState<AccountInfo | null>(null);
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

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (bindModalOpen && sceneStr) {
      timer = setInterval(async () => {
        try {
          const res = await checkWxBindStatus(sceneStr);
          if (res.code === 200) {
            message.success('微信绑定成功');
            setBindModalOpen(false);
            setSceneStr('');
            fetchAccounts();
          }
        } catch (e) { }
      }, 2000);
    }
    return () => clearInterval(timer);
  }, [bindModalOpen, sceneStr]);

  const handleBindWx = async (record: AccountInfo) => {
    try {
      const res = await getWxBindQrCode(record.id);
      setQrUrl(res.data.qr_url);
      setSceneStr(res.data.scene_str);
      setBindUser(record);
      setBindModalOpen(true);
    } catch (error: any) {
      const detail = error?.data?.detail || '获取绑定二维码失败';
      message.error(String(detail));
    }
  };

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
      title: '用户名1',
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
      title: '微信绑定',
      dataIndex: 'wx_user_id',
      key: 'wx_user_id',
      width: 120,
      render: (wx_user_id: string | null | undefined) => (
        <Tag color={wx_user_id ? 'blue' : 'default'}>
          {wx_user_id ? '已绑定' : '未绑定'}
        </Tag>
      ),
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
            <a onClick={() => handleBindWx(record)}>绑定微信</a>
            <Popconfirm
              title="确认删除"
              description={`确定要删除用户 "${record.username}" 吗？`}
              onConfirm={() => handleDelete(record)}
              okText="确认"
              cancelText="取消"
            >
              <a style={{ color: '#ff4d4f' }}>
                删除
              </a>
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

      <Modal
        title="绑定微信"
        open={bindModalOpen}
        footer={null}
        onCancel={() => {
          setBindModalOpen(false);
          setSceneStr('');
          setBindUser(null);
        }}
        width={320}
        destroyOnClose
      >
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          {qrUrl ? (
            <>
              <QRCodeCanvas 
                value={qrUrl} 
                size={200} 
                imageSettings={{ src: '/logo.png', height: 40, width: 40, excavate: true }} 
              />
              <div style={{ marginTop: 16, color: '#333', fontSize: 16, fontWeight: 'bold' }}>
                {bindUser?.username}
              </div>
              <div style={{ marginTop: 8, color: '#666' }}>请使用微信扫描上方二维码进行绑定</div>
            </>
          ) : (
            <div>加载中...</div>
          )}
        </div>
      </Modal>
    </PageContainer>
  );
};

export default TenantUsersPage;

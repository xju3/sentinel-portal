import { EditOutlined, PlusOutlined } from '@ant-design/icons';
import { PageContainer, ProCard, ProColumns, ProTable } from '@ant-design/pro-components';
import { QRCodeCanvas } from 'qrcode.react';
import {
  Button,
  Descriptions,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useState } from 'react';

import {
  createTenantAccount,
  deleteTenantAccount,
  getCurrentTenant,
  listTenantAccounts,
  updateCurrentTenant,
  updateTenantAccount,
  updateTenantAccountPassword,
  getWxBindQrCode,
  checkWxBindStatus,
  type AccountInfo,
  type TenantInfo,
} from '@/services/tenant';

const USER_FLAG_MAP: Record<number, string> = {
  1: '邮箱',
  2: '手机号',
};

const TenantPage = () => {
  // 公司信息状态
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [tenantLoading, setTenantLoading] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editForm] = Form.useForm();

  // 系统用户状态
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [bindModalOpen, setBindModalOpen] = useState(false);
  const [qrUrl, setQrUrl] = useState('');
  const [sceneStr, setSceneStr] = useState('');
  const [bindUser, setBindUser] = useState<AccountInfo | null>(null);
  const [createForm] = Form.useForm();

  // 获取公司信息
  const fetchTenant = async () => {
    setTenantLoading(true);
    try {
      const data = await getCurrentTenant();
      setTenant(data);
    } catch (error: any) {
      const detail = error?.data?.detail || '获取公司信息失败';
      message.error(String(detail));
    } finally {
      setTenantLoading(false);
    }
  };

  // 获取用户列表
  const fetchAccounts = async () => {
    setAccountsLoading(true);
    try {
      const data = await listTenantAccounts();
      setAccounts(data);
    } catch (error: any) {
      const detail = error?.data?.detail || '获取用户列表失败';
      message.error(String(detail));
    } finally {
      setAccountsLoading(false);
    }
  };

  useEffect(() => {
    fetchTenant();
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
        } catch (e) {}
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

  // 编辑公司信息
  const handleEdit = () => {
    if (!tenant) return;
    editForm.setFieldsValue({
      name: tenant.name,
      mqtt_server: tenant.mqtt_server,
      api_server: tenant.api_server,
    });
    setEditModalOpen(true);
  };

  const handleEditSave = async () => {
    try {
      const values = await editForm.validateFields();
      setEditSubmitting(true);
      await updateCurrentTenant({
        name: values.name,
        mqtt_server: values.mqtt_server,
        api_server: values.api_server,
      });
      message.success('公司信息更新成功');
      setEditModalOpen(false);
      await fetchTenant();
    } catch (error: any) {
      if (error?.errorFields) return;
      const detail = error?.data?.detail || '更新失败，请重试';
      message.error(String(detail));
    } finally {
      setEditSubmitting(false);
    }
  };

  // 停用/启用用户
  const handleToggleActive = async (record: AccountInfo) => {
    try {
      await updateTenantAccount(record.id, { active: !record.active });
      message.success(record.active ? '用户已停用' : '用户已启用');
      fetchAccounts();
    } catch (error: any) {
      const detail = error?.data?.detail || '操作失败';
      message.error(String(detail));
    }
  };

  // 修改密码
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);
  const [passwordTarget, setPasswordTarget] = useState<AccountInfo | null>(null);
  const [passwordForm] = Form.useForm();

  const handlePasswordOpen = (record: AccountInfo) => {
    setPasswordTarget(record);
    passwordForm.resetFields();
    setPasswordModalOpen(true);
  };

  const handlePasswordSave = async () => {
    if (!passwordTarget) return;
    try {
      const values = await passwordForm.validateFields();
      setPasswordSubmitting(true);
      await updateTenantAccountPassword(passwordTarget.id, { password: values.password });
      message.success('密码修改成功');
      setPasswordModalOpen(false);
      setPasswordTarget(null);
      passwordForm.resetFields();
    } catch (error: any) {
      if (error?.errorFields) return;
      const detail = error?.data?.detail || '修改密码失败';
      message.error(String(detail));
    } finally {
      setPasswordSubmitting(false);
    }
  };

  // 删除用户
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

  // 自动检测 username 类型：先用邮箱规则检查，不通过则视为手机号
  const detectFlag = (username: string): number => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (emailRegex.test(username)) {
      return 1; // 邮箱
    }
    return 2; // 手机号
  };

  // 创建用户
  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      const flag = detectFlag(values.username);
      setCreateSubmitting(true);
      await createTenantAccount({
        contact_name: values.contact_name,
        username: values.username,
        password: values.password,
        flag,
        active: true,
      });
      message.success('账号创建成功');
      setCreateModalOpen(false);
      createForm.resetFields();
      fetchAccounts();
    } catch (error: any) {
      if (error?.errorFields) return;
      const detail = error?.data?.detail || '创建账号失败';
      message.error(String(detail));
    } finally {
      setCreateSubmitting(false);
    }
  };

  const columns = [
    {
      title: '姓名',
      dataIndex: 'contact_name',
      key: 'contact_name',
      width: 120,
      render: (text: string | null) => text || '-',
      sorter: (a: any, b: any) => (a.contact_name || '').localeCompare(b.contact_name || '', 'zh-CN'),
    },
    {
      title: '登录账号',
      dataIndex: 'username',
      key: 'username',
      width: 220,
      sorter: (a: any, b: any) => (a.username || '').localeCompare(b.username || '', 'zh-CN'),
    },
    {
      title: '类型',
      dataIndex: 'flag',
      key: 'flag',
      width: 80,
      render: (flag: number) => (
        <Tag color={flag === 1 ? 'green' : 'orange'}>
          {USER_FLAG_MAP[flag] || '未知'}
        </Tag>
      ),
      sorter: (a: any, b: any) => Number(a.flag) - Number(b.flag),
    },
    {
      title: '管理员',
      dataIndex: 'admin',
      key: 'admin',
      width: 80,
      render: (admin: boolean) => (
        <Tag color={admin ? 'blue' : 'default'}>
          {admin ? '是' : '否'}
        </Tag>
      ),
      sorter: (a: any, b: any) => Number(a.admin) - Number(b.admin),
    },
    {
      title: '微信绑定',
      dataIndex: 'wx_user_id',
      key: 'wx_user_id',
      width: 100,
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
      width: 80,
      render: (active: boolean) => (
        <Tag color={active ? 'success' : 'error'}>
          {active ? '启用' : '禁用'}
        </Tag>
      ),
      sorter: (a: any, b: any) => Number(a.active) - Number(b.active),
    },
    {
      title: '操作',
      key: 'action',
      width: 240,
      fixed: 'right' as const,
      align: 'center' as const,
      render: (_: any, record: AccountInfo) => (
        <Space>
          <a onClick={() => handleBindWx(record)}>绑定微信</a>
          <a onClick={() => handleToggleActive(record)}>
            {record.active ? '停用' : '启用'}
          </a>
          <a onClick={() => handlePasswordOpen(record)}>
            修改密码
          </a>
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
      ),
    },
  ];

  return (
    <PageContainer title="公司信息" ghost>
      {/* 公司信息卡片 */}
      <ProCard
        title="公司信息"
        loading={tenantLoading}
        extra={
          <Button type="primary" icon={<EditOutlined />} onClick={handleEdit}>
            编辑
          </Button>
        }
        style={{ marginBottom: 24 }}
      >
        {tenant ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="公司编码">{tenant.code}</Descriptions.Item>
            <Descriptions.Item label="公司名称">{tenant.name}</Descriptions.Item>
            <Descriptions.Item label="MQTT 服务器">{tenant.mqtt_server}</Descriptions.Item>
            <Descriptions.Item label="API 服务器">{tenant.api_server}</Descriptions.Item>
            <Descriptions.Item label="状态">
              {tenant.active ? '启用' : '禁用'}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Typography.Text type="secondary">暂无公司信息</Typography.Text>
        )}
      </ProCard>

      {/* 系统用户卡片 */}
      <ProCard
        title="系统用户"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            新增账号
          </Button>
        }
        style={{}}
      >
        <Table
          dataSource={accounts}
          columns={columns}
          rowKey="id"
          loading={accountsLoading}
          pagination={false}
          size="small"
        />
      </ProCard>

      {/* 编辑公司信息弹窗 */}
      <Modal
        title="编辑公司信息"
        open={editModalOpen}
        onOk={handleEditSave}
        onCancel={() => {
          setEditModalOpen(false);
          editForm.resetFields();
        }}
        confirmLoading={editSubmitting}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="公司名称"
            rules={[{ required: true, message: '请输入公司名称' }]}
          >
            <Input placeholder="请输入公司名称" />
          </Form.Item>
          <Form.Item
            name="mqtt_server"
            label="MQTT 服务器"
            rules={[{ required: true, message: '请输入 MQTT 服务器地址' }]}
          >
            <Input placeholder="请输入 MQTT 服务器地址" />
          </Form.Item>
          <Form.Item
            name="api_server"
            label="API 服务器"
            rules={[{ required: true, message: '请输入 API 服务器地址' }]}
          >
            <Input placeholder="请输入 API 服务器地址" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 修改密码弹窗 */}
      <Modal
        title={`修改密码 - ${passwordTarget?.username || ''}`}
        open={passwordModalOpen}
        onOk={handlePasswordSave}
        onCancel={() => {
          setPasswordModalOpen(false);
          setPasswordTarget(null);
          passwordForm.resetFields();
        }}
        confirmLoading={passwordSubmitting}
        okText="保存"
        cancelText="取消"
      >
        <Form form={passwordForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码长度不能少于6位' },
            ]}
          >
            <Input.Password placeholder="请输入新密码" />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label="确认密码"
            dependencies={['password']}
            rules={[
              { required: true, message: '请确认新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password placeholder="请再次输入新密码" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新增账号弹窗 */}
      <Modal
        title="新增账号"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false);
          createForm.resetFields();
        }}
        confirmLoading={createSubmitting}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="contact_name"
            label="姓名"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input placeholder="请输入姓名" />
          </Form.Item>

          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
            help="支持邮箱或手机号，系统会自动识别类型"
          >
            <Input placeholder="请输入邮箱或手机号" />
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
        </Form>
      </Modal>

      {/* 绑定微信弹窗 */}
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
                level="H"
                imageSettings={{ src: '/logo.png', height: 40, width: 40, excavate: true }} 
              />
              <div style={{ marginTop: 16, color: '#333', fontSize: 16, fontWeight: 'bold' }}>
                {bindUser?.username}
              </div>
              <div style={{ marginTop: 8, color: '#666' }}>请【{bindUser?.username}】使用微信扫描上方二维码进行绑定</div>
            </>
          ) : (
            <div>加载中...</div>
          )}
        </div>
      </Modal>
    </PageContainer>
  );
};

export default TenantPage;

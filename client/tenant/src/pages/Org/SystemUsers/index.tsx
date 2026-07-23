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
  Space,
  Table,
  Tag,
  Select,
} from 'antd';
import { useEffect, useState } from 'react';
import {
  createTenantAccount,
  deleteTenantAccount,
  listTenantAccounts,
  updateTenantAccount,
  updateTenantAccountPassword,
  getWxBindQrCode,
  checkWxBindStatus,
  type AccountInfo,
} from '@/services/tenant';

const USER_FLAG_MAP: Record<number, string> = {
  1: '邮箱',
  2: '手机号',
};

const SystemUsers = () => {
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [employees, setEmployees] = useState<any[]>([]);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [bindModalOpen, setBindModalOpen] = useState(false);
  const [qrUrl, setQrUrl] = useState('');
  const [sceneStr, setSceneStr] = useState('');
  const [bindUser, setBindUser] = useState<AccountInfo | null>(null);
  const [createForm] = Form.useForm();
  
  // 修改密码状态
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);
  const [currentAccount, setCurrentAccount] = useState<AccountInfo | null>(null);
  const [passwordForm] = Form.useForm();

  const fetchAccounts = async () => {
    setAccountsLoading(true);
    try {
      const [accData, empData] = await Promise.all([
        listTenantAccounts(),
        import('@/services/org').then(m => m.listEmployees())
      ]);
      setAccounts(accData);
      setEmployees(empData);
    } catch (error: any) {
      const detail = error?.data?.detail || '获取数据失败';
      message.error(String(detail));
    } finally {
      setAccountsLoading(false);
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

  const handleToggleActive = async (record: AccountInfo) => {
    try {
      await updateTenantAccount(record.id, { active: !record.active });
      message.success(record.active ? '用户已禁用' : '用户已启用');
      fetchAccounts();
    } catch (error: any) {
      const detail = error?.data?.detail || '更新状态失败';
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

  const detectFlag = (username: string): number => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (emailRegex.test(username)) {
      return 1;
    }
    return 2;
  };

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      const flag = detectFlag(values.username);
      setCreateSubmitting(true);
      await createTenantAccount({
        contact_name: values.contact_name,
        username: values.username,
        password: values.password,
        employee_id: values.employee_id,
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

  const handleChangePassword = async () => {
    if (!currentAccount) return;
    try {
      const values = await passwordForm.validateFields();
      setPasswordSubmitting(true);
      await updateTenantAccountPassword(currentAccount.id, {
        password: values.password,
      });
      message.success('密码修改成功');
      setPasswordModalOpen(false);
      passwordForm.resetFields();
    } catch (error: any) {
      if (error?.errorFields) return;
      const detail = error?.data?.detail || '修改密码失败';
      message.error(String(detail));
    } finally {
      setPasswordSubmitting(false);
    }
  };

  const columns = [
    {
      title: '姓名',
      dataIndex: 'contact_name',
      key: 'contact_name',
      width: 150,
    },
    {
      title: '登录账号',
      dataIndex: 'username',
      key: 'username',
      width: 220,
      sorter: (a: any, b: any) => (a.username || '').localeCompare(b.username || '', 'zh-CN'),
    },
    {
      title: '关联员工',
      key: 'employee_id',
      width: 120,
      render: (_: any, record: AccountInfo) => {
        const emp = employees.find(e => e.id === record.employee_id);
        return emp ? <Tag color="blue">{emp.name}</Tag> : <Tag color="default">未关联</Tag>;
      }
    },
    {
      title: '类型',
      dataIndex: 'flag',
      key: 'flag',
      width: 100,
      render: (flag: number) => USER_FLAG_MAP[flag] || '未知',
    },
    {
      title: '是否主账户',
      dataIndex: 'admin',
      key: 'admin',
      width: 100,
      render: (admin: boolean) => (
        <Tag color={admin ? 'gold' : 'default'}>{admin ? '主账户' : '子账户'}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'active',
      key: 'active',
      width: 100,
      render: (active: boolean) => (
        <Tag color={active ? 'success' : 'error'}>{active ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '微信绑定',
      key: 'wx_bind',
      width: 150,
      render: (_: any, record: AccountInfo) => (
        record.wx_user_id ? (
          <Tag color="success">已绑定</Tag>
        ) : (
          <Space>
            <Tag color="default">未绑定</Tag>
            {!record.admin && <a onClick={() => handleBindWx(record)}>去绑定</a>}
          </Space>
        )
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 250,
      render: (_: any, record: AccountInfo) => (
        <Space>
          <a
            onClick={() => {
              setCurrentAccount(record);
              setPasswordModalOpen(true);
            }}
          >
            修改密码
          </a>
          {!record.admin && (
            <>
              <Popconfirm
                title={`确认${record.active ? '禁用' : '启用'}`}
                description={`确定要${record.active ? '禁用' : '启用'}此账号吗？`}
                onConfirm={() => handleToggleActive(record)}
                okText="确认"
                cancelText="取消"
              >
                <a>{record.active ? '禁用' : '启用'}</a>
              </Popconfirm>
              <Popconfirm
                title="确认删除"
                description="确定要删除此账号吗？此操作不可恢复。"
                onConfirm={() => handleDelete(record)}
                okText="确认"
                cancelText="取消"
              >
                <a style={{ color: '#ff4d4f' }}>删除</a>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="系统用户" ghost>
      <ProCard
        title="系统用户"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            新增账号
          </Button>
        }
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

      {/* 修改密码弹窗 */}
      <Modal
        title={`修改密码 - ${currentAccount?.username}`}
        open={passwordModalOpen}
        onOk={handleChangePassword}
        onCancel={() => {
          setPasswordModalOpen(false);
          passwordForm.resetFields();
          setCurrentAccount(null);
        }}
        confirmLoading={passwordSubmitting}
        okText="确认"
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
            name="confirm_password"
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

          <Form.Item
            name="employee_id"
            label="关联员工"
            help="（可选）将此账号与系统中的员工关联"
          >
            <Select
              placeholder="请选择员工"
              allowClear
              showSearch
              optionFilterProp="children"
              options={employees.map(e => ({ label: e.name, value: e.id }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 微信绑定弹窗 */}
      <Modal
        title="绑定微信"
        open={bindModalOpen}
        onCancel={() => {
          setBindModalOpen(false);
          setSceneStr('');
          setBindUser(null);
        }}
        footer={null}
        width={400}
      >
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          {qrUrl ? (
            <>
              <QRCodeCanvas value={qrUrl} size={200} />
              <div style={{ marginTop: 16, color: '#666' }}>
                请使用微信扫一扫绑定此账号
                <br />
                {bindUser?.username}
              </div>
            </>
          ) : (
            <div>加载二维码中...</div>
          )}
        </div>
      </Modal>
    </PageContainer>
  );
};

export default SystemUsers;

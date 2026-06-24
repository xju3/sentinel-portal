import { Link, useNavigate } from '@umijs/max';
import { PageContainer, ProCard, ProForm, ProFormText } from '@ant-design/pro-components';
import { Alert, Button, Space, Typography, message, Modal } from 'antd';
import { WechatOutlined } from '@ant-design/icons';
import { useEffect, useState } from 'react';

import { login, getWxLoginQrCode, checkWxLoginStatus, type LoginResult } from '@/services/auth';
import { clearSession, getSession, saveSession } from '@/utils/session';

type LoginFormValues = {
  username: string;
  password: string;
};

const LoginPage = () => {
  const navigate = useNavigate();
  const [session, setSession] = useState<LoginResult | null>(null);

  useEffect(() => {
    const parsed = getSession();
    if (parsed) setSession(parsed);
  }, []);

  const handleLogout = () => {
    clearSession();
    setSession(null);
    message.success('已退出登录');
  };

  const [wxModalOpen, setWxModalOpen] = useState(false);
  const [wxQrUrl, setWxQrUrl] = useState('');
  const [wxSceneStr, setWxSceneStr] = useState('');

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (wxModalOpen && wxSceneStr) {
      timer = setInterval(async () => {
        try {
          const res = await checkWxLoginStatus(wxSceneStr);
          // If the backend returns success code and data contains access_token
          if (res?.data && (res.data as any).access_token) {
            const loginData = res.data as LoginResult;
            saveSession(loginData);
            setSession(loginData);
            message.success('登录成功');
            setWxModalOpen(false);
            setWxSceneStr('');
            navigate('/');
          }
        } catch (error: any) {
          // umi request throws an error for non-2xx status codes (like 404)
          // The backend returns 404 with detail="此微信号没有绑定相应平台账号"
          if (error?.response?.status === 404 || (error?.data && error.data.detail)) {
            message.error(error?.data?.detail || '此微信号没有绑定相应平台账号');
            setWxModalOpen(false);
            setWxSceneStr('');
          }
        }
      }, 2000);
    }
    return () => clearInterval(timer);
  }, [wxModalOpen, wxSceneStr, navigate]);

  const handleWxLoginClick = async () => {
    try {
      const res = await getWxLoginQrCode();
      setWxQrUrl(res.data.qr_url);
      setWxSceneStr(res.data.scene_str);
      setWxModalOpen(true);
    } catch (e) {
      message.error('获取微信登录二维码失败');
    }
  };

  return (
    <PageContainer title="账号登录" content="使用用户名和密码登录平台。" ghost>
      <ProCard colSpan={12} style={{ maxWidth: 560, margin: '0 auto' }}>
        {session ? (
          <Alert
            type="success"
            showIcon
            message="当前已登录"
            description={
              <Space direction="vertical" size={4}>
                <Typography.Text>用户名: {session.username}</Typography.Text>
                <Space>
                  <Button type="primary" onClick={() => navigate('/dashboard/overview')}>
                    进入主应用
                  </Button>
                  <Button onClick={handleLogout}>退出登录</Button>
                </Space>
              </Space>
            }
          />
        ) : (
          <>
            <ProForm<LoginFormValues>
              submitter={{
                searchConfig: {
                  submitText: '登录',
                },
              }}
              onFinish={async (values) => {
                try {
                  const res = await login({
                    username: values.username,
                    password: values.password,
                  });
                  saveSession(res);
                  setSession(res);
                  message.success('登录成功');
                  navigate('/');
                  return true;
                } catch (error: any) {
                  const detail =
                    error?.data?.detail || error?.info?.errorMessage || '登录失败，请检查用户名和密码';
                  message.error(String(detail));
                  return false;
                }
              }}
            >
              <ProFormText
                name="username"
                label="用户名"
                placeholder="请输入用户名"
                rules={[{ required: true, message: '请输入用户名' }]}
              />

              <ProFormText.Password
                name="password"
                label="密码"
                placeholder="请输入密码"
                rules={[{ required: true, message: '请输入密码' }]}
              />
            </ProForm>

            <Alert
              type="info"
              showIcon
              message="还没有账号？"
              description={
                <Typography.Text>
                  请先前往 <Link to="/register">注册页</Link> 创建账号。
                </Typography.Text>
              }
              style={{ marginBottom: 16 }}
            />

            <Button
              block
              icon={<WechatOutlined />}
              onClick={handleWxLoginClick}
              style={{ backgroundColor: '#07c160', color: '#fff', borderColor: '#07c160' }}
            >
              微信扫码登录
            </Button>
          </>
        )}
      </ProCard>

      <Modal
        title="微信扫码登录"
        open={wxModalOpen}
        footer={null}
        onCancel={() => {
          setWxModalOpen(false);
          setWxSceneStr('');
        }}
        width={320}
        destroyOnClose
      >
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          {wxQrUrl ? (
            <>
              <img src={wxQrUrl} alt="微信登录二维码" style={{ width: 200, height: 200 }} />
              <div style={{ marginTop: 16, color: '#666' }}>请使用微信扫描上方二维码登录</div>
            </>
          ) : (
            <div>加载中...</div>
          )}
        </div>
      </Modal>
    </PageContainer>
  );
};

export default LoginPage;

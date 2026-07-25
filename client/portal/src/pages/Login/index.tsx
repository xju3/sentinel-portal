import { Link, useNavigate } from '@umijs/max';
import { ProForm, ProFormText } from '@ant-design/pro-components';
import { Button, Space, message, Modal } from 'antd';
import { WechatOutlined, UserOutlined, LockOutlined, LogoutOutlined, AppstoreOutlined } from '@ant-design/icons';
import { QRCodeCanvas } from 'qrcode.react';
import { useEffect, useState } from 'react';

import { login, getWxLoginQrCode, checkWxLoginStatus, type LoginResult } from '@/services/auth';
import { clearSession, getSession, saveSession } from '@/utils/session';
import styles from './index.less';

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
          const data = (res as any)?.data || res;
          if (data && data.access_token) {
            const loginData = data as LoginResult;
            saveSession(loginData);
            setSession(loginData);
            message.success('登录成功');
            setWxModalOpen(false);
            setWxSceneStr('');
            navigate('/');
          }
        } catch (error: any) {
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
      const data = (res as any).data || res;
      if (!data || !data.qr_url) {
        throw new Error('未获取到二维码数据');
      }
      setWxQrUrl(data.qr_url);
      setWxSceneStr(data.scene_str);
      setWxModalOpen(true);
    } catch (e: any) {
      console.error(e);
      message.error('获取微信登录二维码失败: ' + (e.message || '未知错误'));
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.bgElements}>
        <div className={styles.glowingOrb1} />
        <div className={styles.glowingOrb2} />
        <div className={styles.grid} />
      </div>
      
      <div className={styles.loginWrapper}>
        <div className={styles.loginBox}>
          {session ? (
            <div className={styles.sessionBox}>
              <div className={styles.header}>
                <h2>欢迎回来</h2>
                <p>当前已登录为: <strong style={{ color: '#fff' }}>{session.username}</strong></p>
              </div>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Button 
                  type="primary" 
                  size="large" 
                  block 
                  icon={<AppstoreOutlined />} 
                  onClick={() => navigate('/dashboard/overview')}
                >
                  进入主应用
                </Button>
                <Button 
                  size="large" 
                  block 
                  ghost
                  icon={<LogoutOutlined />} 
                  onClick={handleLogout}
                  style={{ borderColor: 'rgba(255,255,255,0.2)', color: '#fff' }}
                >
                  退出登录
                </Button>
              </Space>
            </div>
          ) : (
            <>
              <div className={styles.header}>
                <h1>Sentinel Platform</h1>
                <p>欢迎登录 Sentinel 系统，掌控您的资源</p>
              </div>
              <ProForm<LoginFormValues>
                submitter={{
                  searchConfig: {
                    submitText: '登 录',
                  },
                  submitButtonProps: {
                    size: 'large',
                    style: { width: '100%' },
                  },
                  resetButtonProps: {
                    style: { display: 'none' },
                  },
                }}
                onFinish={async (values) => {
                  try {
                    const res = await login({
                      username: values.username,
                      password: values.password,
                    });
                    const data = (res as any).data || res;
                    saveSession(data);
                    setSession(data);
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
                  placeholder="请输入用户名"
                  fieldProps={{
                    size: 'large',
                    prefix: <UserOutlined />,
                  }}
                  rules={[{ required: true, message: '请输入用户名' }]}
                />

                <ProFormText.Password
                  name="password"
                  placeholder="请输入密码"
                  fieldProps={{
                    size: 'large',
                    prefix: <LockOutlined />,
                  }}
                  rules={[{ required: true, message: '请输入密码' }]}
                />
              </ProForm>

              <div className={styles.divider}>
                <span>或</span>
              </div>
                
              <Button
                block
                className={styles.wxLoginBtn}
                icon={<WechatOutlined />}
                onClick={handleWxLoginClick}
              >
                微信扫码快捷登录
              </Button>

              <div className={styles.registerHint}>
                还没有账号? <Link to="/register">立即注册</Link>
              </div>
            </>
          )}
        </div>
      </div>

      <Modal
        title={null}
        open={wxModalOpen}
        footer={null}
        onCancel={() => {
          setWxModalOpen(false);
          setWxSceneStr('');
        }}
        width={360}
        destroyOnClose
        centered
        styles={{
          content: {
            backgroundColor: '#111827',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          },
        }}
        closeIcon={<span style={{ color: '#9ca3af', fontSize: 16 }}>✕</span>}
      >
        <div style={{ textAlign: 'center', padding: '30px 0 10px' }}>
          <h2 style={{ color: '#fff', fontSize: 20, marginBottom: 24, fontWeight: 600 }}>微信扫码登录</h2>
          {wxQrUrl ? (
            <>
              <div style={{ background: '#fff', padding: 12, borderRadius: 12, display: 'inline-block' }}>
                <QRCodeCanvas 
                  value={wxQrUrl} 
                  size={200} 
                  level="H"
                  imageSettings={{ src: '/logo.png', height: 44, width: 44, excavate: true }} 
                />
              </div>
              <div style={{ marginTop: 24, color: '#9ca3af', fontSize: 15 }}>
                请使用 <span style={{ color: '#10d36b', fontWeight: 600 }}>微信</span> 扫描上方二维码
              </div>
            </>
          ) : (
            <div style={{ padding: '60px 0', color: '#9ca3af' }}>加载二维码中...</div>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default LoginPage;

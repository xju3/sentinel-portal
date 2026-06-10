import { Link, useNavigate } from '@umijs/max';
import { PageContainer, ProCard, ProForm, ProFormText } from '@ant-design/pro-components';
import { Alert, Button, Space, Typography, message } from 'antd';
import { useEffect, useState } from 'react';

import { login, type LoginResult } from '@/services/auth';
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
            />
          </>
        )}
      </ProCard>
    </PageContainer>
  );
};

export default LoginPage;

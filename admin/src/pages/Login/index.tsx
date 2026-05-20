import { history } from '@umijs/max';
import { PageContainer, ProCard, ProForm, ProFormText } from '@ant-design/pro-components';
import { message } from 'antd';
import { useState } from 'react';

import { login, type LoginResult } from '@/services/auth';
import { clearSession, getSession, saveSession } from '@/utils/session';

type LoginFormValues = {
  username: string;
  password: string;
};

const LoginPage = () => {
  const [session, setSession] = useState<LoginResult | null>(() => getSession());

  const handleLogout = () => {
    clearSession();
    setSession(null);
    message.success('已退出登录');
  };

  return (
    <PageContainer title="管理员登录" content="使用管理员账号登录后台管理系统。" ghost>
      <ProCard style={{ maxWidth: 480, margin: '0 auto' }}>
        {session ? (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <div style={{ fontSize: 16, marginBottom: 16 }}>
              当前已登录: <strong>{session.username}</strong>
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <a
                style={{ fontSize: 14 }}
                onClick={() => history.push('/tenant')}
              >
                进入管理后台
              </a>
              <a style={{ fontSize: 14, color: '#ff4d4f' }} onClick={handleLogout}>
                退出登录
              </a>
            </div>
          </div>
        ) : (
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
                history.push('/tenant');
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
        )}
      </ProCard>
    </PageContainer>
  );
};

export default LoginPage;

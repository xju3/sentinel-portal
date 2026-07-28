import { Link, useNavigate } from '@umijs/max';
import { ProForm, ProFormText } from '@ant-design/pro-components';
import { CheckCircleOutlined, LockOutlined } from '@ant-design/icons';
import { Button, message } from 'antd';
import { useMemo, useState } from 'react';

import { setupInitialPassword } from '@/services/auth';
import styles from '../Register/index.less';

type PasswordSetupForm = {
  new_password: string;
  confirm_password: string;
};

const SetPasswordPage = () => {
  const navigate = useNavigate();
  const [completed, setCompleted] = useState(false);
  const token = useMemo(
    () => new URLSearchParams(window.location.search).get('token') || '',
    [],
  );

  return (
    <div className={styles.container}>
      <div className={styles.bgElements}>
        <div className={styles.glowingOrb1} />
        <div className={styles.glowingOrb2} />
        <div className={styles.grid} />
      </div>

      <div className={styles.registerWrapper}>
        <div className={styles.registerBox}>
          {completed ? (
            <div className={styles.successBox}>
              <CheckCircleOutlined style={{ fontSize: 64, color: '#10b981', marginBottom: 24 }} />
              <h2>密码设置成功</h2>
              <p style={{ color: '#9ca3af', marginBottom: 32 }}>
                该设置链接已失效，现在可以使用邮箱和新密码登录。
              </p>
              <Button type="primary" size="large" block onClick={() => navigate('/login')}>
                前往登录
              </Button>
            </div>
          ) : (
            <>
              <div className={styles.header}>
                <h1>设置登录密码</h1>
                <p>请为您的朗湖智能平台账号设置密码</p>
              </div>

              {!token ? (
                <div className={styles.successBox}>
                  <p style={{ color: '#ef4444' }}>设置密码链接不完整，请重新打开邮件中的链接。</p>
                  <Link to="/login">返回登录</Link>
                </div>
              ) : (
                <ProForm<PasswordSetupForm>
                  submitter={{
                    searchConfig: { submitText: '设置密码' },
                    submitButtonProps: { size: 'large', style: { width: '100%' } },
                    resetButtonProps: { style: { display: 'none' } },
                  }}
                  onFinish={async (values) => {
                    if (values.new_password !== values.confirm_password) {
                      message.error('两次输入的密码不一致');
                      return false;
                    }
                    try {
                      await setupInitialPassword({
                        token,
                        new_password: values.new_password,
                      });
                      setCompleted(true);
                      message.success('密码设置成功');
                      return true;
                    } catch (error: any) {
                      if (!error?.businessErrorShown) {
                        const detail =
                          error?.data?.detail || error?.message || '密码设置失败，请重新打开邮件链接';
                        message.error(String(detail));
                      }
                      return false;
                    }
                  }}
                >
                  <ProFormText.Password
                    name="new_password"
                    placeholder="请输入至少 8 位密码"
                    fieldProps={{ size: 'large', prefix: <LockOutlined /> }}
                    rules={[
                      { required: true, message: '请输入新密码' },
                      { min: 8, message: '密码至少 8 位' },
                    ]}
                  />
                  <ProFormText.Password
                    name="confirm_password"
                    placeholder="请再次输入密码"
                    fieldProps={{ size: 'large', prefix: <LockOutlined /> }}
                    rules={[{ required: true, message: '请再次输入密码' }]}
                  />
                </ProForm>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SetPasswordPage;

import { Link, useNavigate } from '@umijs/max';
import { ProForm, ProFormText } from '@ant-design/pro-components';
import { Button, message } from 'antd';
import { BankOutlined, UserOutlined, PhoneOutlined, MailOutlined, ArrowLeftOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useState } from 'react';

import { registerTenant, type RegisterResult } from '@/services/register';
import styles from './index.less';

const RegisterPage = () => {
  const navigate = useNavigate();
  const [result, setResult] = useState<RegisterResult | null>(null);
  const [loginAccount, setLoginAccount] = useState<string>('');

  const updateLoginPreview = (values: Record<string, string | undefined>) => {
    const email = (values.email || '').trim();
    setLoginAccount(email.toLowerCase());
  };

  return (
    <div className={styles.container}>
      <div className={styles.bgElements}>
        <div className={styles.glowingOrb1} />
        <div className={styles.glowingOrb2} />
        <div className={styles.grid} />
      </div>
      
      <div className={styles.registerWrapper}>
        <div className={styles.registerBox}>
          
          <div className={styles.backToLogin}>
             <Link to="/login"><ArrowLeftOutlined /> 返回登录</Link>
          </div>

          {result ? (
            <div className={styles.successBox}>
              <CheckCircleOutlined style={{ fontSize: 64, color: '#10b981', marginBottom: 24 }} />
              <h2>企业注册成功</h2>
              <p style={{ color: '#9ca3af', marginBottom: 32 }}>
                设置密码链接已发送至注册邮箱。
              </p>
              
              <div className={styles.accountInfoCard}>
                <div className={styles.infoRow}>
                  <span>登录账号</span>
                  <strong>{result.account_username}</strong>
                </div>
                <div className={styles.infoRow}>
                  <span>账号类型</span>
                  <strong>邮箱</strong>
                </div>
              </div>
              
              <div className={styles.warningText}>
                请检查收件箱和垃圾邮件目录，并在 24 小时内设置登录密码。
              </div>

              <Button 
                type="primary" 
                size="large" 
                block 
                onClick={() => navigate('/login')}
              >
                立即前往登录
              </Button>
            </div>
          ) : (
            <>
              <div className={styles.header}>
                <h1>注册企业账号</h1>
                <p>提交后系统将自动为您创建专属租户平台</p>
              </div>

              <ProForm
                submitter={{
                  searchConfig: {
                    submitText: '提交注册信息',
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
                    const res = await registerTenant({
                      company_name: values.company_name,
                      contact_name: values.contact_name,
                      phone: values.phone,
                      email: values.email.trim(),
                    });
                    const data = (res as any)?.data || res;
                    setResult(data);
                    message.success('注册成功，设置密码链接已发送至邮箱');
                    return true;
                  } catch (error: any) {
                    if (!error?.businessErrorShown) {
                      const detail = error?.data?.detail || error?.message || '注册失败，请检查输入后重试';
                      message.error(String(detail));
                    }
                    return false;
                  }
                }}
                onValuesChange={(_, values) => {
                  updateLoginPreview(values as Record<string, string | undefined>);
                }}
              >
                <div style={{ marginBottom: 24 }}>
                  <ProFormText
                    name="company_name"
                    placeholder="请输入公司名称"
                    fieldProps={{
                      size: 'large',
                      prefix: <BankOutlined />,
                    }}
                    rules={[{ required: true, message: '请输入公司名称' }]}
                  />
                </div>

                <div style={{ marginBottom: 24 }}>
                  <ProFormText
                    name="contact_name"
                    placeholder="请输入管理员/联系人姓名"
                    fieldProps={{
                      size: 'large',
                      prefix: <UserOutlined />,
                    }}
                    rules={[{ required: true, message: '请输入联系人' }]}
                  />
                </div>

                <div style={{ marginBottom: 24 }}>
                  <ProFormText
                    name="phone"
                    placeholder="请输入联系电话"
                    fieldProps={{
                      size: 'large',
                      prefix: <PhoneOutlined />,
                    }}
                    rules={[
                      { required: true, message: '请输入联系电话' },
                      { pattern: /^[0-9+()\-\s]{6,20}$/, message: '电话格式不正确' },
                    ]}
                  />
                </div>

                <div style={{ marginBottom: 24 }}>
                  <ProFormText
                    name="email"
                    placeholder="请输入用于登录的电子邮件"
                    fieldProps={{
                      size: 'large',
                      prefix: <MailOutlined />,
                    }}
                    rules={[
                      { required: true, message: '请输入电子邮件' },
                      { type: 'email', message: '电子邮件格式不正确' },
                    ]}
                  />
                </div>
                
                <div className={styles.previewBox}>
                  <div className={styles.previewTitle}>账户预览</div>
                  <div className={styles.previewContent}>
                    系统将使用
                    <span className={styles.highlightEmail}>
                      {loginAccount || '尚未填写'}
                    </span>
                    作为管理员登录账号，并将设置密码链接发送至该邮箱
                  </div>
                </div>

              </ProForm>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;

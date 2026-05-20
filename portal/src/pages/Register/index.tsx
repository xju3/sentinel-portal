import { useNavigate } from '@umijs/max';
import { PageContainer, ProCard, ProForm, ProFormText } from '@ant-design/pro-components';
import { Alert, Space, Typography, message } from 'antd';
import { useState } from 'react';

import { registerTenant, type RegisterResult } from '@/services/register';
import './index.less';

const RegisterPage = () => {
  const navigate = useNavigate();
  const [result, setResult] = useState<RegisterResult | null>(null);
  const [loginAccount, setLoginAccount] = useState<string>('');
  const [loginChannel, setLoginChannel] = useState<'email' | 'mobile'>('mobile');

  const updateLoginPreview = (values: Record<string, string | undefined>) => {
    const email = (values.email || '').trim();
    const phone = (values.phone || '').trim();
    if (email) {
      setLoginChannel('email');
      setLoginAccount(email.toLowerCase());
      return;
    }
    const normalizedPhone = phone.replace(/\D/g, '');
    setLoginChannel('mobile');
    setLoginAccount(normalizedPhone);
  };

  return (
    <PageContainer
      title="企业注册"
      content="提交后系统会自动创建租户、联系人，并创建平台账号。邮箱优先作为登录账号，若未填写邮箱则使用手机号。"
      ghost
    >
      <ProCard colSpan={12} style={{ maxWidth: 680, margin: '0 auto' }}>
        <ProForm
          submitter={{
            searchConfig: {
              submitText: '提交注册',
            },
          }}
          onFinish={async (values) => {
            try {
              const res = await registerTenant({
                company_name: values.company_name,
                contact_name: values.contact_name,
                phone: values.phone,
                email: values.email?.trim() || undefined,
              });
              setResult(res);
              message.success('注册成功，请使用生成的临时密码登录');
              return true;
            } catch (error: any) {
              const detail = error?.data?.detail || '注册失败，请检查输入后重试';
              message.error(String(detail));
              return false;
            }
          }}
          onValuesChange={(_, values) => {
            updateLoginPreview(values as Record<string, string | undefined>);
          }}
        >
          <ProFormText
            name="company_name"
            label="公司名称"
            placeholder="请输入公司名称"
            rules={[{ required: true, message: '请输入公司名称' }]}
          />

          <ProFormText
            name="contact_name"
            label="联系人"
            placeholder="请输入联系人"
            rules={[{ required: true, message: '请输入联系人' }]}
          />

          <ProFormText
            name="phone"
            label="电话"
            placeholder="请输入联系电话"
            rules={[
              { required: true, message: '请输入联系电话' },
              { pattern: /^[0-9+()\-\s]{6,20}$/, message: '电话格式不正确' },
            ]}
          />

          <ProFormText
            name="email"
            label="电子邮件"
            placeholder="请输入电子邮件（可选）"
            rules={[
              { type: 'email', message: '电子邮件格式不正确' },
            ]}
          />

          <Alert
            showIcon
            type="info"
            message="登录账号预览"
            description={
              <Space direction="vertical" size={2}>
                <Typography.Text>
                  当前将使用:
                  <Typography.Text
                    style={{
                      color: loginChannel === 'email' ? '#389e0d' : '#d46b08',
                      marginLeft: 6,
                      fontWeight: 600,
                    }}
                  >
                    {loginAccount || '请先填写手机号，或填写邮箱'}
                  </Typography.Text>
                </Typography.Text>
                <Typography.Text type="secondary">
                  标记:
                  {loginChannel === 'email' ? ' 邮箱作为登录账号' : ' 手机号作为登录账号'}
                </Typography.Text>
                <Typography.Text type="secondary">
                  注册成功后会直接显示系统生成的临时密码。
                </Typography.Text>
              </Space>
            }
          />
        </ProForm>

        {result ? (
          <Alert
            type="success"
            showIcon
            message="账号已创建"
            description={
              <Space direction="vertical" size={0}>
                <Typography.Text>登录账号: {result.account_username}</Typography.Text>
                <Typography.Text>临时密码: {result.generated_password}</Typography.Text>
                <Typography.Text type="secondary">
                  登录账号类型: {result.login_channel === 'email' ? '邮箱' : '手机号'}
                </Typography.Text>
                <Typography.Text type="secondary">
                  请使用上面的临时密码登录，并在首次登录后立即修改密码。
                </Typography.Text>
                <Typography.Text>
                  <Typography.Link onClick={() => navigate('/login')}>前往登录</Typography.Link>
                </Typography.Text>
              </Space>
            }
          />
        ) : null}
      </ProCard>
    </PageContainer>
  );
};

export default RegisterPage;

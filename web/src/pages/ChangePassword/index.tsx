import { history } from '@umijs/max';
import { PageContainer, ProCard, ProForm, ProFormText } from '@ant-design/pro-components';
import { message } from 'antd';

import { changePassword } from '@/services/auth';
import { getSession } from '@/utils/session';

type PasswordFormValues = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};

const ChangePasswordPage = () => {
  return (
    <PageContainer title="更改密码">
      <ProCard colSpan={12} style={{ maxWidth: 560, margin: '0 auto' }}>
        <ProForm<PasswordFormValues>
          submitter={{
            searchConfig: {
              submitText: '保存新密码',
            },
          }}
          onFinish={async (values) => {
            const session = getSession();
            if (!session) {
              message.error('登录已失效，请重新登录');
              history.push('/login');
              return false;
            }
            if (values.new_password !== values.confirm_password) {
              message.error('两次输入的新密码不一致');
              return false;
            }
            await changePassword({
              account_id: session.account_id,
              current_password: values.current_password,
              new_password: values.new_password,
            });
            message.success('密码修改成功，请使用新密码登录');
            history.push('/profile');
            return true;
          }}
        >
          <ProFormText.Password
            name="current_password"
            label="当前密码"
            rules={[{ required: true, message: '请输入当前密码' }]}
          />
          <ProFormText.Password
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '新密码至少 6 位' },
            ]}
          />
          <ProFormText.Password
            name="confirm_password"
            label="确认新密码"
            rules={[{ required: true, message: '请再次输入新密码' }]}
          />
        </ProForm>
      </ProCard>
    </PageContainer>
  );
};

export default ChangePasswordPage;

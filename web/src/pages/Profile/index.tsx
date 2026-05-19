import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Descriptions, Empty, Typography } from 'antd';

import { getSession } from '@/utils/session';

const ProfilePage = () => {
  const session = getSession();

  return (
    <PageContainer title="个人信息" subTitle="当前登录用户信息">
      <ProCard>
        {session ? (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="联系人姓名">
              {session.contact_name || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="登录用户名">{session.username}</Descriptions.Item>
            <Descriptions.Item label="租户公司">{session.tenant_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="租户ID">{session.tenant_id}</Descriptions.Item>
            <Descriptions.Item label="账号ID">{session.account_id}</Descriptions.Item>
            <Descriptions.Item label="用户名类型">
              {session.flag === 1 ? '邮箱' : '手机号'}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="未登录" />
        )}
        <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
          如需修改密码，请使用右上角菜单中的“更改密码”。
        </Typography.Paragraph>
      </ProCard>
    </PageContainer>
  );
};

export default ProfilePage;

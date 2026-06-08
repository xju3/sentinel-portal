import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Typography } from 'antd';

const WelcomePage = () => {
  return (
    <PageContainer title="Welcome" subTitle="主应用结构页（占位）">
      <ProCard bordered>
        <Typography.Title level={4} style={{ marginTop: 0 }}>
          Welcome
        </Typography.Title>
        <Typography.Paragraph type="secondary">
          你已进入主应用。后续业务页面将从这里开始扩展。
        </Typography.Paragraph>
      </ProCard>
    </PageContainer>
  );
};

export default WelcomePage;

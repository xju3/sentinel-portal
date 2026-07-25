import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Typography } from 'antd';

type BusinessPlaceholderProps = {
  title: string;
  description: string;
  model?: string;
  apiPath?: string;
};

const BusinessPlaceholder = ({ title, description, model, apiPath }: BusinessPlaceholderProps) => {
  return (
    <PageContainer title={title}>
      <ProCard bordered>
        <Typography.Paragraph>{description}</Typography.Paragraph>
        {model ? (
          <Typography.Paragraph type="secondary">数据模型: {model}</Typography.Paragraph>
        ) : null}
        {apiPath ? (
          <Typography.Paragraph type="secondary">接口路径: {apiPath}</Typography.Paragraph>
        ) : null}
      </ProCard>
    </PageContainer>
  );
};

export default BusinessPlaceholder;

import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Tag, Timeline, Typography } from 'antd';

const DashboardMonitoring = () => {
  return (
    <PageContainer title="Dashboard Monitoring" subTitle="仪表盘实时监控">
      <ProCard gutter={16} wrap>
        <ProCard colSpan={12} title="实时告警" bordered headerBordered>
          <Timeline
            items={[
              {
                color: 'red',
                children: (
                  <>
                    <Typography.Text strong>设备 A-001</Typography.Text>
                    <Tag color="error" style={{ marginLeft: 8 }}>
                      温度过高
                    </Tag>
                    <br />
                    <Typography.Text type="secondary">2026-05-20 15:30:00</Typography.Text>
                  </>
                ),
              },
              {
                color: 'orange',
                children: (
                  <>
                    <Typography.Text strong>设备 B-023</Typography.Text>
                    <Tag color="warning" style={{ marginLeft: 8 }}>
                      振动异常
                    </Tag>
                    <br />
                    <Typography.Text type="secondary">2026-05-20 14:15:00</Typography.Text>
                  </>
                ),
              },
              {
                color: 'blue',
                children: (
                  <>
                    <Typography.Text strong>设备 C-112</Typography.Text>
                    <Tag color="processing" style={{ marginLeft: 8 }}>
                      离线
                    </Tag>
                    <br />
                    <Typography.Text type="secondary">2026-05-20 12:00:00</Typography.Text>
                  </>
                ),
              },
            ]}
          />
        </ProCard>
        <ProCard colSpan={12} title="设备状态概览" bordered headerBordered>
          <ProCard>
            <Typography.Text strong>在线率</Typography.Text>
            <Typography.Title level={2} style={{ color: '#52c41a', margin: '8px 0' }}>
              75%
            </Typography.Title>
            <Typography.Text type="secondary">在线 96 / 总计 128</Typography.Text>
          </ProCard>
          <ProCard style={{ marginTop: 16 }}>
            <Typography.Text strong>健康状态</Typography.Text>
            <div style={{ marginTop: 8 }}>
              <Tag color="success">健康 (82)</Tag>
              <Tag color="warning">警告 (14)</Tag>
              <Tag color="error">故障 (2)</Tag>
            </div>
          </ProCard>
        </ProCard>
      </ProCard>
    </PageContainer>
  );
};

export default DashboardMonitoring;

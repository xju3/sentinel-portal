import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';

const { Statistic } = StatisticCard;

const DashboardOverview = () => {
  return (
    <PageContainer title="Dashboard Overview" subTitle="仪表盘概览">
      <StatisticCard.Group direction="row" gutter={16}>
        <StatisticCard
          statistic={{
            title: '设备总数',
            value: 128,
            suffix: '台',
          }}
        />
        <StatisticCard
          statistic={{
            title: '在线设备',
            value: 96,
            suffix: '台',
            status: 'success',
          }}
        />
        <StatisticCard
          statistic={{
            title: '告警数量',
            value: 12,
            suffix: '条',
            status: 'error',
          }}
        />
        <StatisticCard
          statistic={{
            title: '今日新增',
            value: 5,
            suffix: '台',
          }}
        />
      </StatisticCard.Group>
      <ProCard style={{ marginTop: 16 }}>
        <ProCard title="系统状态" bordered headerBordered>
          <StatisticCard
            chart={
              <div
                style={{
                  height: 200,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#999',
                }}
              >
                图表区域（待接入真实数据）
              </div>
            }
          />
        </ProCard>
      </ProCard>
    </PageContainer>
  );
};

export default DashboardOverview;

import { useEffect, useState } from 'react';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { message } from 'antd';
import { request } from '@umijs/max';
import CalendarHeatmap from './CalendarHeatmap';
import FaultPieChart from './FaultPieChart';
import SunburstChart from './SunburstChart';
import FaultAlertList from './FaultAlertList';

const { Statistic } = StatisticCard;

// 定义 Dashboard 聚合数据类型
type DashboardData = {
  totalDevices: number;
  runningDevices: number;
  faultyDevices: number;
  newDevicesToday: number;
  vibrationAnomalyCount: number;
  temperatureAnomalyCount: number;
  bothAnomalyCount: number;
  recentAnomalies: {
    id: string;
    device_code: string;
    device_sn: string;
    anomaly: number;
    ts: number;
  }[];
  devicesByCategoryTree?: any[];
  devicesByAreaTree?: any[];
};

const DashboardOverview = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<DashboardData>({
    totalDevices: 0,
    runningDevices: 0,
    faultyDevices: 0,
    newDevicesToday: 0,
    vibrationAnomalyCount: 0,
    temperatureAnomalyCount: 0,
    bothAnomalyCount: 0,
    recentAnomalies: [],
  });

  // 年历数据
  const [calendarData, setCalendarData] = useState<any>(null);
  const [calendarLoading, setCalendarLoading] = useState(false);

  const [treeViewMode, setTreeViewMode] = useState<'category' | 'area'>('category');

  // 从后端获取 Dashboard 聚合数据
  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const res = await request<DashboardData>('/api/v1/dashboard/overview');
      if (res) setData(res);
    } catch (error) {
      message.error('获取仪表盘数据失败');
    } finally {
      setLoading(false);
    }
  };

  // 仅刷新统计卡片数据
  const refreshStats = async () => {
    try {
      const res = await request<DashboardData>('/api/v1/dashboard/overview');
      if (res) {
        setData(prev => ({
          ...prev,
          totalDevices: res.totalDevices,
          runningDevices: res.runningDevices,
          faultyDevices: res.faultyDevices,
          newDevicesToday: res.newDevicesToday,
        }));
      }
    } catch (error) {
      message.error('刷新统计数据失败');
    }
  };

  // 仅刷新故障视图（三个图表）
  const refreshCharts = async () => {
    try {
      const res = await request<DashboardData>('/api/v1/dashboard/overview');
      if (res) {
        setData(prev => ({
          ...prev,
          faultyDevices: res.faultyDevices,
          vibrationAnomalyCount: res.vibrationAnomalyCount,
          temperatureAnomalyCount: res.temperatureAnomalyCount,
          bothAnomalyCount: res.bothAnomalyCount,
          devicesByCategoryTree: res.devicesByCategoryTree,
          devicesByAreaTree: res.devicesByAreaTree,
        }));
      }
    } catch (error) {
      message.error('刷新图表数据失败');
    }
  };

  // 仅刷新最新故障预警列表
  const refreshAlerts = async () => {
    try {
      const res = await request<DashboardData>('/api/v1/dashboard/overview');
      if (res) {
        setData(prev => ({
          ...prev,
          recentAnomalies: res.recentAnomalies,
        }));
      }
    } catch (error) {
      message.error('刷新预警数据失败');
    }
  };

  // 获取年历数据
  const fetchCalendarData = async () => {
    setCalendarLoading(true);
    try {
      const res = await request<any>('/api/v1/dashboard/calendar');
      if (res) setCalendarData(res);
    } catch (error) {
      console.error('获取年历数据失败', error);
    } finally {
      setCalendarLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    fetchCalendarData();
  }, []);

  // 定时刷新：每10分钟一次
  useEffect(() => {
    const timer = setInterval(() => {
      fetchDashboardData();
      fetchCalendarData();
    }, 600000);
    return () => clearInterval(timer);
  }, []);

  return (
    <PageContainer title="仪表盘" subTitle="概览">
      <ProCard style={{ marginTop: 16 }} ghost>
        <ProCard
          title="警情概览"
          bordered
          headerBordered
          loading={loading}
          extra={
            <a onClick={refreshStats} style={{ cursor: 'pointer' }}>
              刷新
            </a>
          }
        >
          <StatisticCard.Group direction="row" gutter={16}>
            <StatisticCard
              statistic={{
                title: '设备总数',
                value: data.totalDevices,
                suffix: '台',
              }}
            />
            <StatisticCard
              statistic={{
                title: '在线设备',
                value: data.runningDevices,
                suffix: '台',
                status: 'success',
              }}
            />
            <StatisticCard
              statistic={{
                title: '报警设备',
                value: data.faultyDevices,
                suffix: '台',
                status: 'error',
              }}
            />
            <StatisticCard
              statistic={{
                title: '今日新增',
                value: data.newDevicesToday,
                suffix: '台',
              }}
            />
          </StatisticCard.Group>
        </ProCard>
      </ProCard>
   <ProCard style={{ marginTop: 16 }} ghost>
        <ProCard
          title="年历视图"
          bordered
          headerBordered
          loading={calendarLoading}
          extra={
            <a onClick={fetchCalendarData} style={{ cursor: 'pointer' }}>
              刷新
            </a>
          }
        >
          <CalendarHeatmap data={calendarData} loading={calendarLoading} />
        </ProCard>
      </ProCard>
      <ProCard style={{ marginTop: 16 }} ghost>
        <ProCard
          title="分布视图"
          bordered
          headerBordered
          loading={loading}
          extra={
            <a onClick={refreshCharts} style={{ cursor: 'pointer' }}>
              刷新
            </a>
          }
        >
          <div style={{ display: 'flex', gap: 16 }}>
            {/* <div style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
              <FaultPieChart
                totalDevices={data.totalDevices}
                runningDevices={data.runningDevices}
                faultyDevices={data.faultyDevices}
                vibrationAnomalyCount={data.vibrationAnomalyCount}
                temperatureAnomalyCount={data.temperatureAnomalyCount}
                bothAnomalyCount={data.bothAnomalyCount}
              />
              <div style={{ marginTop: 8, fontSize: 14, fontWeight: 500, color: '#333' }}>
                故障总览（{data.faultyDevices}台）
              </div>
            </div> */}
            <div style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
              <SunburstChart
                treeData={treeViewMode === 'category' ? (data.devicesByCategoryTree || []) : (data.devicesByAreaTree || [])}
                onViewModeToggle={() => setTreeViewMode(prev => prev === 'category' ? 'area' : 'category')}
              />
              <div style={{ marginTop: 8, fontSize: 14, fontWeight: 500, color: '#333' }}>
                {treeViewMode === 'category' ? '类别视图' : '区域视图'}（{data.faultyDevices}台）
                <span
                  style={{
                    marginLeft: 12,
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#999',
                    cursor: 'pointer',
                    borderBottom: '1px dashed #999',
                  }}
                  onClick={() => setTreeViewMode(prev => prev === 'category' ? 'area' : 'category')}
                >
                  点击中心切换至{treeViewMode === 'category' ? '区域视图' : '类别视图'}
                </span>
              </div>
            </div>
          </div>
        </ProCard>
      </ProCard>

   

      <ProCard style={{ marginTop: 16 }} ghost>
        <ProCard title="最新预警" bordered headerBordered loading={loading}>
          <FaultAlertList dataSource={data.recentAnomalies} />
        </ProCard>
      </ProCard>
    </PageContainer>
  );
};

export default DashboardOverview;

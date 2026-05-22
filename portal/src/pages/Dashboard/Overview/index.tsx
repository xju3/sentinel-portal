import { useEffect, useRef, useState } from 'react';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { Badge, List, Tag, Typography, message } from 'antd';
import { request } from '@umijs/max';
import * as echarts from 'echarts';

const { Statistic } = StatisticCard;

// 定义 Dashboard 聚合数据类型
type DashboardData = {
  totalDevices: number;
  runningDevices: number;
  faultyDevices: number;
  newDevicesToday: number;
  recentAnomalies: {
    id: string;
    device_code: string;
    device_sn: string;
    anomaly: number; // 1=振动异常, 2=温度异常, 3=双异常
    ts: number;
  }[];
  devicesByCategory?: {
    name: string;
    value: number;
  }[];
};

// 异常状态映射 (根据后端 handler 逻辑)
const ANOMALY_MAP: Record<number, { text: string; color: string }> = {
  1: { text: '振动异常', color: 'warning' },
  2: { text: '温度异常', color: 'error' },
  3: { text: '振动+温度异常', color: 'magenta' },
};

const DashboardOverview = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<DashboardData>({
    totalDevices: 0,
    runningDevices: 0,
    faultyDevices: 0,
    newDevicesToday: 0,
    recentAnomalies: [],
    devicesByCategory: [],
  });
  const chartRef = useRef<HTMLDivElement>(null);
  const categoryChartRef = useRef<HTMLDivElement>(null);

  // 从后端获取 Dashboard 聚合数据
  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const res = await request<DashboardData>('/api/v1/dashboard/overview');
      if (res) {
        setData(res);
      }
    } catch (error) {
      message.error('获取仪表盘数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  // 初始化和更新 Echarts 饼图及柱状图
  useEffect(() => {
    let pieChart: echarts.ECharts | undefined;
    let barChart: echarts.ECharts | undefined;
    
    // 计算剩余的“离线/未知”设备数（防止由于统计误差出现负数）
    const offlineDevices = Math.max(0, data.totalDevices - data.runningDevices - data.faultyDevices);

    // 1. 渲染设备健康分布饼图
    if (chartRef.current) {
      pieChart = echarts.init(chartRef.current);
      const pieOption = {
      tooltip: {
        trigger: 'item'
      },
      legend: {
        top: '5%',
        left: 'center'
      },
      series: [
        {
          name: '设备健康分布',
          type: 'pie',
          radius: ['40%', '70%'], // 环形图内外半径
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 8,
            borderColor: '#fff',
            borderWidth: 2
          },
          label: { show: false, position: 'center' },
          emphasis: {
            label: { show: true, fontSize: 18, fontWeight: 'bold' }
          },
          labelLine: { show: false },
          data: [
            { value: data.runningDevices, name: '正常运行', itemStyle: { color: '#52c41a' } },
            { value: data.faultyDevices, name: '故障设备', itemStyle: { color: '#ff4d4f' } },
            { value: offlineDevices, name: '离线/未知', itemStyle: { color: '#d9d9d9' } },
          ].filter(item => item.value > 0) // 过滤掉数值为0的项，使图表更整洁
        }
      ]
    };
      pieChart.setOption(pieOption);
    }

    // 2. 渲染设备分类统计柱状图
    if (categoryChartRef.current) {
      barChart = echarts.init(categoryChartRef.current);
      const categoryData = data.devicesByCategory || [];
      
      const barOption = {
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: {
          type: 'category',
          data: categoryData.map((item) => item.name),
          axisTick: { alignWithLabel: true },
          axisLabel: { interval: 0, width: 80, overflow: 'truncate' } // 防止文字过长重叠
        },
        yAxis: { type: 'value' },
        series: [
          {
            name: '设备数量',
            type: 'bar',
            barWidth: '40%',
            data: categoryData.map((item) => item.value),
            itemStyle: {
              borderRadius: [4, 4, 0, 0], // 柱子顶部圆角
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#83bff6' },
                { offset: 0.5, color: '#188df0' },
                { offset: 1, color: '#188df0' }
              ])
            }
          }
        ]
      };
      barChart.setOption(barOption);
    }

    // 监听窗口大小改变，使图表自适应响应式缩放
    const handleResize = () => {
      pieChart?.resize();
      barChart?.resize();
    };
    window.addEventListener('resize', handleResize);

    // 清理副作用
    return () => {
      window.removeEventListener('resize', handleResize);
      pieChart?.dispose();
      barChart?.dispose();
    };
  }, [data]); // 当 data 数据发生变化时重新渲染图表

  return (
    <PageContainer title="Dashboard Overview" subTitle="仪表盘概览">
      <StatisticCard.Group direction="row" gutter={16} loading={loading}>
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
            title: '故障设备',
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

      <ProCard style={{ marginTop: 16 }} gutter={16} ghost>
        <ProCard title="设备健康分布" colSpan={14} bordered headerBordered loading={loading}>
          <StatisticCard
            chart={
              <div
                ref={chartRef}
                style={{
                  height: 250,
                  width: '100%',
                }}
              />
            }
          />
        </ProCard>

        <ProCard title="最新故障预警" colSpan={10} bordered headerBordered loading={loading}>
          <List
            itemLayout="horizontal"
            dataSource={data.recentAnomalies}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <span>
                      <Badge status="error" style={{ marginRight: 8 }} />
                      {item.device_code}
                    </span>
                  }
                  description={`SN: ${item.device_sn} | 时间: ${new Date(item.ts).toLocaleString()}`}
                />
                <Tag color={ANOMALY_MAP[item.anomaly]?.color || 'default'}>
                  {ANOMALY_MAP[item.anomaly]?.text || '未知异常'}
                </Tag>
              </List.Item>
            )}
          />
        </ProCard>
      </ProCard>

      <ProCard style={{ marginTop: 16 }} gutter={16} ghost>
        <ProCard title="设备分类统计" bordered headerBordered loading={loading}>
          <StatisticCard
            chart={
              <div
                ref={categoryChartRef}
                style={{
                  height: 300,
                  width: '100%',
                }}
              />
            }
          />
        </ProCard>
      </ProCard>
    </PageContainer>
  );
};

export default DashboardOverview;

import { useEffect, useRef, useState } from 'react';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { Badge, List, Tag, message } from 'antd';
import { request } from '@umijs/max';
import * as echarts from 'echarts';

const { Statistic } = StatisticCard;

// 定义 Dashboard 聚合数据类型
type DashboardData = {
  totalDevices: number;
  runningDevices: number;
  faultyDevices: number;
  newDevicesToday: number;
  vibrationAnomalyCount: number;  // anomaly=1 震动异常
  temperatureAnomalyCount: number; // anomaly=2 温度异常
  bothAnomalyCount: number;        // anomaly=3 双异常
  recentAnomalies: {
    id: string;
    device_code: string;
    device_sn: string;
    anomaly: number; // 1=振动异常, 2=温度异常, 3=双异常
    ts: number;
  }[];
  devicesByCategoryTree?: any[];
  devicesByAreaTree?: any[];
};

// 异常状态映射 (根据后端 handler 逻辑)
const ANOMALY_MAP: Record<number, { text: string; color: string }> = {
  1: { text: '振动异常', color: 'warning' },
  2: { text: '温度异常', color: 'error' },
  3: { text: '振动+温度异常', color: 'magenta' },
};

// 异常层级渐进色阶：从浅红到深红，按层级深度递增
const ANOMALY_COLORS = [
  '#ffebee', // 第1层（最内层父分类）- 极浅红
  '#ffcdd2', // 第2层 - 浅红
  '#ef9a9a', // 第3层 - 中浅红
  '#e57373', // 第4层 - 中红
  '#ef5350', // 第5层 - 中深红
  '#e53935', // 第6层（最外层异常子节点）- 深红
];

// 递归生成旭日图数据格式
const convertToSunburst = (nodes: any[], anomalyDepth: number = 0): any[] => {
  return nodes.map(n => {
    const hasAnomaly = n.anomaly > 0;
    let children = n.children ? convertToSunburst(n.children, hasAnomaly ? anomalyDepth + 1 : anomalyDepth) : [];

    // 如果该底层分类有异常，则在外部再增加一圈（子节点）专门显示健康状态
    if (children.length === 0 && hasAnomaly) {
      const normalCount = Math.max(0, n.total - n.anomaly);
      if (normalCount > 0) {
        children.push({
          name: '正常',
          realTotal: normalCount,
          anomaly: 0,
          value: normalCount,
          itemStyle: { color: '#e8f5e9' },
          label: { show: true, formatter: '{c}', color: '#81c784', fontSize: 10, textBorderWidth: 0 },
          tooltip: { show: true },
        });
      }
      const outerColorIndex = Math.min(anomalyDepth + 1, ANOMALY_COLORS.length - 1);
      children.push({
        name: '异常',
        realTotal: n.anomaly,
        anomaly: n.anomaly,
        value: n.anomaly,
        itemStyle: { color: ANOMALY_COLORS[outerColorIndex] },
        label: { show: true, formatter: '{c}', color: '#fff', textBorderWidth: 0 },
      });
    }

    let color = undefined;
    if (n.total === 0) {
      color = '#e8e8e8';
    } else if (n.anomaly === 0) {
      color = '#e0e0e0';
    } else {
      const colorIndex = Math.min(anomalyDepth, ANOMALY_COLORS.length - 1);
      color = ANOMALY_COLORS[colorIndex];
    }

    return {
      name: n.name,
      realTotal: n.total,
      anomaly: n.anomaly,
      value: children.length > 0 ? undefined : Math.max(n.total, 1),
      itemStyle: { color },
      label: {
        color: n.total === 0 ? '#999' : (n.anomaly > 0 ? '#c62828' : '#666'),
        textBorderColor: n.total === 0 ? 'transparent' : 'rgba(255,255,255,0.8)',
        textBorderWidth: n.total === 0 ? 0 : 1,
      },
      children: children.length > 0 ? children : undefined,
    };
  });
};

// 计算最大层级
const getMaxDepth = (nodes: any[]): number => {
  if (!nodes || nodes.length === 0) return 0;
  let max = 0;
  for (const node of nodes) {
    max = Math.max(max, node.children ? getMaxDepth(node.children) : 0);
  }
  return max + 1;
};

// 渲染旭日图（类别视图和区域视图共用）
const renderSunburstChart = (
  chartDom: HTMLDivElement,
  treeData: any[],
  anomalyColor: string = '#9b2e2e',
) => {
  const chart = echarts.init(chartDom);
  const sunburstData = convertToSunburst(treeData || []);

  const depth = getMaxDepth(sunburstData);
  const sunburstLevels: any[] = [{}];
  if (depth > 0) {
    const innerRadius = 0;
    const outerRadius = 95;
    const thicknessUnit = (outerRadius - innerRadius) / (depth - 0.5);
    let currentRadius = innerRadius;
    for (let i = 1; i <= depth; i++) {
      const thickness = i === depth ? thicknessUnit / 2 : thicknessUnit;
      sunburstLevels.push({
        r0: `${currentRadius}%`,
        r: `${currentRadius + thickness}%`,
      });
      currentRadius += thickness;
    }
  }

  if (sunburstData.length === 0) {
    chart.setOption({
      title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#999', fontSize: 14 } },
      series: [],
    });
  } else {
    chart.setOption({
      tooltip: {
        formatter: (params: any) => {
          const { name, data } = params;
          if (!data) return '';
          const realTotal = data.realTotal ?? data.value ?? 0;
          const anomaly = data.anomaly ?? 0;
          const normal = Math.max(0, realTotal - anomaly);
          return `${name}<br/>总计: ${realTotal} 台<br/>正常: ${normal} 台 | 异常: <span style="color:${anomalyColor}">${anomaly}</span> 台`;
        },
      },
      series: {
        type: 'sunburst',
        data: sunburstData,
        radius: ['0%', '95%'],
        levels: depth > 0 ? sunburstLevels : undefined,
        sort: undefined,
        emphasis: { focus: 'ancestor' },
        itemStyle: { borderRadius: 4, borderWidth: 2, borderColor: '#fff' },
        label: {
          show: true,
          formatter: (params: any) => {
            const { name, data } = params;
            if (!data) return '';
            const realTotal = data.realTotal ?? data.value ?? 0;
            if (name === '全部') {
              return `全部(${realTotal}台)`;
            }
            return ` ${name}\n${realTotal} 台`;
          },
          rich: {
            name: { color: 'inherit', fontSize: 10, align: 'center', lineHeight: 18 },
            total: { color: 'inherit', fontSize: 12, align: 'center', lineHeight: 16 },
          },
        },
      },
    });
  }

  return chart;
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

  const chartRef = useRef<HTMLDivElement>(null);
  const categoryChartRef = useRef<HTMLDivElement>(null);
  const areaChartRef = useRef<HTMLDivElement>(null);

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

  // 仅刷新统计卡片数据（设备总数、在线设备、故障设备、今日新增）
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

  // 仅刷新故障视图（三个图表），不刷新统计卡片
  const refreshCharts = async () => {
    try {
      const res = await request<DashboardData>('/api/v1/dashboard/overview');
      if (res) {
        // 只更新图表相关数据，不更新统计卡片
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


  useEffect(() => {
    fetchDashboardData();
  }, []);

  // 定时刷新：设备概览每10分钟刷新一次
  useEffect(() => {
    const timer = setInterval(refreshStats, 600000);
    return () => clearInterval(timer);
  }, []);

  // 定时刷新：故障视图每10分钟刷新一次
  useEffect(() => {
    const timer = setInterval(refreshCharts, 600000);
    return () => clearInterval(timer);
  }, []);

  // 定时刷新：最新故障预警每10分钟刷新一次
  useEffect(() => {
    const timer = setInterval(refreshAlerts, 600000);
    return () => clearInterval(timer);
  }, []);



  // 初始化和更新 Echarts 图表
  useEffect(() => {
    let pieChart: echarts.ECharts | undefined;
    let categoryChart: echarts.ECharts | undefined;
    let areaChart: echarts.ECharts | undefined;

    // 计算各分类设备数
    const normalRunning = Math.max(0, data.runningDevices - data.faultyDevices);
    const offlineDevices = Math.max(0, data.totalDevices - normalRunning - data.faultyDevices);

    // 1. 渲染温震故障分布饼图
    if (chartRef.current) {
      pieChart = echarts.init(chartRef.current);
      pieChart.setOption({
        tooltip: {
          trigger: 'item',
          formatter: (params: any) => {
            return `${params.name}: ${params.value} 台 (${params.percent}%)`;
          },
        },
        series: [
          {
            name: '故障概览',
            type: 'pie',
            radius: ['40%', '70%'],
            avoidLabelOverlap: false,
            itemStyle: {
              borderRadius: 8,
              borderColor: '#fff',
              borderWidth: 2,
            },
            label: {
              show: true,
              formatter: (params: any) => `${params.name}\n${params.value}台`,
              fontSize: 11,
              color: '#333',
              lineHeight: 16,
            },
            emphasis: {
              label: { show: true, fontSize: 14, fontWeight: 'bold' },
            },
            labelLine: {
              show: true,
              length: 8,
              length2: 12,
              smooth: true,
            },
            data: (() => {
              const items = [
                { value: normalRunning, name: '正常运行', itemStyle: { color: '#52c41a' } },
                { value: offlineDevices, name: '离线/未知', itemStyle: { color: '#d9d9d9' } },
              ];
              const hasDetail = data.vibrationAnomalyCount > 0 || data.temperatureAnomalyCount > 0 || data.bothAnomalyCount > 0;
              if (hasDetail) {
                items.splice(1, 0,
                  { value: data.vibrationAnomalyCount, name: '震动异常', itemStyle: { color: '#faad14' } },
                  { value: data.temperatureAnomalyCount, name: '温度异常', itemStyle: { color: '#ff4d4f' } },
                  { value: data.bothAnomalyCount, name: '震动+温度异常', itemStyle: { color: '#eb2f96' } },
                );
              } else if (data.faultyDevices > 0) {
                items.splice(1, 0,
                  { value: data.faultyDevices, name: '故障设备', itemStyle: { color: '#ff4d4f' } },
                );
              }
              return items.filter(item => item.value > 0);
            })(),
          },
        ],
      });
    }

    // 2. 渲染类别视图旭日图
    if (categoryChartRef.current) {
      categoryChart = renderSunburstChart(categoryChartRef.current, data.devicesByCategoryTree || [], '#9b2e2e');
    }

    // 3. 渲染区域视图旭日图（与类别视图共用 renderSunburstChart）
    if (areaChartRef.current) {
      areaChart = renderSunburstChart(areaChartRef.current, data.devicesByAreaTree || [], '#9b2e2e');
    }


    // 监听窗口大小改变
    const handleResize = () => {
      pieChart?.resize();
      categoryChart?.resize();
      areaChart?.resize();
    };
    window.addEventListener('resize', handleResize);

    // 清理副作用
    return () => {
      window.removeEventListener('resize', handleResize);
      pieChart?.dispose();
      categoryChart?.dispose();
      areaChart?.dispose();
    };
  }, [data]);

  return (
    <PageContainer title="仪表盘" subTitle="概览">
      <ProCard style={{ marginTop: 16 }} ghost>
        <ProCard
          title="设备概览"
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
        </ProCard>
      </ProCard>


      <ProCard style={{ marginTop: 16 }} ghost>
        <ProCard
          title="故障视图"
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
            <div style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
              <div
                ref={chartRef}
                style={{
                  height: 350,
                  width: '100%',
                }}
              />
              <div style={{ marginTop: 8, fontSize: 14, fontWeight: 500, color: '#333' }}>
                故障总览（{data.faultyDevices}台）
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
              <div
                ref={categoryChartRef}
                style={{
                  height: 350,
                  width: '100%',
                }}
              />
              <div style={{ marginTop: 8, fontSize: 14, fontWeight: 500, color: '#333' }}>
                类别视图（{data.faultyDevices}台）
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
              <div
                ref={areaChartRef}
                style={{
                  height: 350,
                  width: '100%',
                }}
              />
              <div style={{ marginTop: 8, fontSize: 14, fontWeight: 500, color: '#333' }}>
                区域视图（{data.faultyDevices}台）
              </div>
            </div>
          </div>
        </ProCard>
      </ProCard>

      <ProCard style={{ marginTop: 16 }} ghost>
        <ProCard title="最新故障预警" bordered headerBordered loading={loading}>
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
    </PageContainer>
  );
};

export default DashboardOverview;

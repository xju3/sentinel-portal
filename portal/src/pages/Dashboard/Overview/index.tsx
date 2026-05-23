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
    vibrationAnomalyCount: 0,
    temperatureAnomalyCount: 0,
    bothAnomalyCount: 0,
    recentAnomalies: [],
  });

  const chartRef = useRef<HTMLDivElement>(null);
  const categoryChartRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    fetchDashboardData();
  }, []);

  // 初始化和更新 Echarts 饼图及多层环形图
  useEffect(() => {
    let pieChart: echarts.ECharts | undefined;
    let nestedPieChart: echarts.ECharts | undefined;

    // 计算剩余的"离线/未知"设备数（防止由于统计误差出现负数）
    const anomalyTotal = data.vibrationAnomalyCount + data.temperatureAnomalyCount + data.bothAnomalyCount;
    const offlineDevices = Math.max(0, data.totalDevices - data.runningDevices - anomalyTotal);

    // 1. 渲染设备健康分布饼图 (区分异常类型: 0=正常, 1=震动异常, 2=温度异常, 3=双异常)
    if (chartRef.current) {
      pieChart = echarts.init(chartRef.current);
      const pieOption = {
        tooltip: {
          trigger: 'item',
          formatter: (params: any) => {
            return `${params.name}: ${params.value} 台 (${params.percent}%)`;
          },
        },
        legend: {
          top: '5%',
          left: 'center',
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
              borderWidth: 2,
            },
            label: { show: false, position: 'center' },
            emphasis: {
              label: { show: true, fontSize: 18, fontWeight: 'bold' },
            },
            labelLine: { show: false },
            data: [
              { value: data.runningDevices, name: '正常运行', itemStyle: { color: '#52c41a' } },
              { value: data.vibrationAnomalyCount, name: '震动异常', itemStyle: { color: '#faad14' } },
              { value: data.temperatureAnomalyCount, name: '温度异常', itemStyle: { color: '#ff4d4f' } },
              { value: data.bothAnomalyCount, name: '震动+温度异常', itemStyle: { color: '#eb2f96' } },
              { value: offlineDevices, name: '离线/未知', itemStyle: { color: '#d9d9d9' } },
            ].filter((item) => item.value > 0), // 过滤掉数值为0的项，使图表更整洁
          },
        ],
      };
      pieChart.setOption(pieOption);
    }

    // 2. 构建并渲染设备分类多层环形图 (旭日图 Sunburst)
    if (categoryChartRef.current) {
      nestedPieChart = echarts.init(categoryChartRef.current);
      
      const treeData = data.devicesByCategoryTree || [];

      // 递归生成旭日图数据格式
      const convertToSunburst = (nodes: any[]): any[] => {
        return nodes.map(n => {
          const hasAnomaly = n.anomaly > 0;
          const children = n.children ? convertToSunburst(n.children) : [];
          
          let color = undefined;
          if (hasAnomaly) {
            if (children.length === 0) {
              color = '#ff4d4f'; // 仅底层（最细分类）有故障时显著标红
            } else {
              color = undefined; // 顶层和中间层保留 ECharts 自带的默认颜色区分度
            }
          } else if (n.total === 0) {
            color = '#e8e8e8'; // 空分类置灰处理
          }

          return {
            name: n.name,
            realTotal: n.total,
            anomaly: n.anomaly,
            value: n.total,
            itemStyle: { color: color },
            label: {
              color: n.total === 0 ? '#999' : '#fff',
              textBorderColor: n.total === 0 ? 'transparent' : 'rgba(0,0,0,0.4)',
              textBorderWidth: n.total === 0 ? 0 : 1,
            },
            children: children.length > 0 ? children : undefined
          };
        });
      };

      const sunburstData = convertToSunburst(treeData);

      // 如果没有数据，显示空状态
      if (sunburstData.length === 0) {
        nestedPieChart.setOption({
          title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#999', fontSize: 14 } },
          series: []
        });
      } else {
        nestedPieChart.setOption({
          tooltip: {
            formatter: (params: any) => {
              const { name, data } = params;
              if (!data) return '';
              const realTotal = data.realTotal || 0;
              const normal = Math.max(0, realTotal - (data.anomaly || 0));
              return `${name}<br/>总计: ${realTotal} 台<br/>正常: ${normal} 台 | 异常: <span style="color:#ff4d4f">${data.anomaly || 0}</span> 台`;
            }
          },
          series: {
            type: 'sunburst',
            data: sunburstData,
            radius: [0, '95%'],
            sort: undefined, // 保持原始分类自然顺序
            emphasis: { focus: 'ancestor' },
            itemStyle: { borderRadius: 4, borderWidth: 2, borderColor: '#fff' },
            label: { 
              show: true, 
              formatter: (params: any) => {
                const { name, data } = params;
                if (!data) return '';
                const isLeaf = !data.children || data.children.length === 0;
                if (isLeaf && data.anomaly > 0) {
                  return `{name|${name}}\n{total|${data.realTotal} 台}\n{anomaly|异常 ${data.anomaly} 台}`;
                }
                return `{name|${name}}\n{total|${data.realTotal} 台}`;
              },
              rich: {
                name: { color: 'inherit', fontSize: 13, align: 'center', lineHeight: 18 },
                total: { color: 'inherit', fontSize: 12, align: 'center', lineHeight: 16 },
                anomaly: { color: '#fff', backgroundColor: '#ff4d4f', padding: [2, 4], borderRadius: 2, fontSize: 11, align: 'center', lineHeight: 16 }
              }
            }
          }
        });
      }
    }

    // 监听窗口大小改变，使图表自适应响应式缩放
    const handleResize = () => {
      pieChart?.resize();
      nestedPieChart?.resize();
    };
    window.addEventListener('resize', handleResize);

    // 清理副作用
    return () => {
      window.removeEventListener('resize', handleResize);
      pieChart?.dispose();
      nestedPieChart?.dispose();
    };
  }, [data]); 

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
        <ProCard title="设备分类统计与异常分布" bordered headerBordered loading={loading}>
          <StatisticCard
            chart={
              <div
                ref={categoryChartRef}
                style={{
                  height: 350,
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

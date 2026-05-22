import { useEffect, useRef, useState } from 'react';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { Badge, List, Tag, message } from 'antd';
import { request } from '@umijs/max';
import * as echarts from 'echarts';

const { Statistic } = StatisticCard;

// 设备分类树节点类型（递归结构）
type CategoryTreeNode = {
  name: string;
  total: number;   // 该分类下的设备总数
  anomaly: number;  // 该分类下的异常设备数
  children?: CategoryTreeNode[];
};

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
  devicesByCategory?: {
    name: string;
    value: number;
  }[];
  devicesByCategoryTree?: CategoryTreeNode[];
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

  // 将分类树展平为层级数据，用于多层环形图
  // 内圈：一级分类的设备总数
  // 外圈：二级分类的设备总数
  // 每个扇区通过颜色深浅或内嵌小扇区表示异常占比
  const flattenCategoryTree = (tree: CategoryTreeNode[] | undefined) => {
    const innerData: { name: string; value: number; itemStyle?: any }[] = [];
    const outerData: { name: string; value: number; itemStyle?: any }[] = [];
    const anomalyData: { name: string; value: number; itemStyle?: any }[] = [];
    const parentChildMap: Record<string, string[]> = {};

    if (!tree || tree.length === 0) return { innerData, outerData, anomalyData, parentChildMap };

    // 预定义颜色调色板（用于正常设备）
    const colorPalette = [
      '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
      '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#f47920',
    ];

    tree.forEach((root, idx) => {
      const baseColor = colorPalette[idx % colorPalette.length];
      // 内圈：一级分类的设备总数
      innerData.push({
        name: root.name,
        value: root.total,
        itemStyle: { color: baseColor },
      });
      // 内圈异常部分（叠加在正常扇区上，用更深的颜色）
      if (root.anomaly > 0) {
        anomalyData.push({
          name: `${root.name} (异常)`,
          value: root.anomaly,
          itemStyle: { color: baseColor, opacity: 0.3 },
        });
      }

      if (root.children && root.children.length > 0) {
        parentChildMap[root.name] = root.children.map((c) => c.name);
        root.children.forEach((child) => {
          outerData.push({
            name: child.name,
            value: child.total,
            itemStyle: { color: baseColor },
          });
          // 外圈异常部分
          if (child.anomaly > 0) {
            anomalyData.push({
              name: `${child.name} (异常)`,
              value: child.anomaly,
              itemStyle: { color: baseColor, opacity: 0.3 },
            });
          }
        });
      }
    });

    return { innerData, outerData, anomalyData, parentChildMap };
  };

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
            { value: data.vibrationAnomalyCount, name: '震动异常', itemStyle: { color: '#faad14' } },
            { value: data.temperatureAnomalyCount, name: '温度异常', itemStyle: { color: '#ff4d4f' } },
            { value: data.bothAnomalyCount, name: '震动+温度异常', itemStyle: { color: '#eb2f96' } },
            { value: offlineDevices, name: '离线/未知', itemStyle: { color: '#d9d9d9' } },
          ].filter(item => item.value > 0) // 过滤掉数值为0的项，使图表更整洁
        }
      ]
    };
      pieChart.setOption(pieOption);
    }

    // 2. 渲染设备分类多层环形图（展示设备总数 + 异常占比）
    if (categoryChartRef.current) {
      nestedPieChart = echarts.init(categoryChartRef.current);
      const { innerData, outerData, anomalyData, parentChildMap } = flattenCategoryTree(data.devicesByCategoryTree);

      // 如果没有数据，显示空状态
      if (innerData.length === 0) {
        nestedPieChart.setOption({
          title: {
            text: '暂无数据',
            left: 'center',
            top: 'center',
            textStyle: { color: '#999', fontSize: 14 },
          },
        });
      } else {
        const nestedOption = {
          tooltip: {
            trigger: 'item',
            formatter: (params: any) => {
              const { name, value, seriesName } = params;
              // 查找该分类的异常数
              const anomalyItem = anomalyData.find(
                (a) => a.name === `${name} (异常)`
              );
              const anomalyCount = anomalyItem ? anomalyItem.value : 0;
              const normalCount = value - anomalyCount;
              return `${seriesName}<br/>${name}: 共 ${value} 台<br/>正常: ${normalCount} 台 | 异常: ${anomalyCount} 台`;
            },
          },
          legend: {
            top: '5%',
            left: 'center',
            data: innerData.map((item) => item.name),
          },
          series: [
            {
              // 内圈：一级分类的设备总数（主色）
              name: '设备分类分布',
              type: 'pie',
              selectedMode: 'single',
              radius: ['0%', '45%'],
              avoidLabelOverlap: false,
              label: {
                show: true,
                formatter: (params: any) => {
                  const name = params.name;
                  const anomalyItem = anomalyData.find(
                    (a) => a.name === `${name} (异常)`
                  );
                  const anomalyCount = anomalyItem ? anomalyItem.value : 0;
                  return `${name}\n${params.value}台\n异常${anomalyCount}台`;
                },
                fontSize: 11,
                fontWeight: 'bold',
              },
              emphasis: {
                label: { show: true, fontSize: 14, fontWeight: 'bold' },
                itemStyle: {
                  shadowBlur: 10,
                  shadowOffsetX: 0,
                  shadowColor: 'rgba(0, 0, 0, 0.5)',
                },
              },
              labelLine: { show: true },
              data: innerData,
            },
            {
              // 内圈异常叠加层：用半透明深色覆盖异常部分
              name: '异常设备',
              type: 'pie',
              radius: ['0%', '45%'],
              silent: true,
              label: { show: false },
              labelLine: { show: false },
              emphasis: { scale: false },
              itemStyle: {
                borderColor: 'transparent',
                borderWidth: 0,
              },
              data: anomalyData.filter((a) =>
                innerData.some((i) => a.name === `${i.name} (异常)`)
              ),
            },
            {
              // 外圈：二级分类的设备总数
              name: '子分类分布',
              type: 'pie',
              radius: ['55%', '80%'],
              avoidLabelOverlap: false,
              label: {
                show: true,
                formatter: (params: any) => `${params.name}`,
                fontSize: 10,
              },
              emphasis: {
                label: { show: true, fontSize: 12, fontWeight: 'bold' },
              },
              labelLine: {
                length: 10,
                length2: 10,
                smooth: true,
              },
              data: outerData,
            },
            {
              // 外圈异常叠加层
              name: '子分类异常设备',
              type: 'pie',
              radius: ['55%', '80%'],
              silent: true,
              label: { show: false },
              labelLine: { show: false },
              emphasis: { scale: false },
              itemStyle: {
                borderColor: 'transparent',
                borderWidth: 0,
              },
              data: anomalyData.filter((a) =>
                outerData.some((o) => a.name === `${o.name} (异常)`)
              ),
            },
          ],
        };
        nestedPieChart.setOption(nestedOption);
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
        <ProCard title="设备分类异常分布" bordered headerBordered loading={loading}>
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

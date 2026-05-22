import { useEffect, useRef, useState } from 'react';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { Badge, List, Tag, message } from 'antd';
import { request } from '@umijs/max';
import * as echarts from 'echarts';

import { listAllDeviceCategories } from '@/services/deviceCategory';
import { listAllDeviceSpecs } from '@/services/deviceSpec';
import { listAllDeviceInsts } from '@/services/deviceInst';
import { listAllSensors } from '@/services/tenantSensor';
import { listAllSensorMonitorings } from '@/services/sensorMonitoring';

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

  const [categories, setCategories] = useState<any[]>([]);
  const [specs, setSpecs] = useState<any[]>([]);
  const [insts, setInsts] = useState<any[]>([]);
  const [monitorings, setMonitorings] = useState<any[]>([]);
  const [sensors, setSensors] = useState<any[]>([]);

  const chartRef = useRef<HTMLDivElement>(null);
  const categoryChartRef = useRef<HTMLDivElement>(null);

  // 从后端获取 Dashboard 聚合数据
  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const [res, cats, spcs, ins, mons, sens] = await Promise.all([
        request<DashboardData>('/api/v1/dashboard/overview').catch(() => null),
        listAllDeviceCategories().catch(() => []),
        listAllDeviceSpecs().catch(() => []),
        listAllDeviceInsts().catch(() => []),
        listAllSensorMonitorings().catch(() => []),
        listAllSensors().catch(() => [])
      ]);
      if (res) setData(res);
      setCategories(cats || []);
      setSpecs(spcs || []);
      setInsts(ins || []);
      setMonitorings(mons || []);
      setSensors(sens || []);
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
      
      // --- 在前端动态关联计算多层数据结构 ---
      const catMap = new Map<string, any>();
      categories.forEach(c => catMap.set(c.id, { ...c, total: 0, anomaly: 0, childrenMap: new Map() }));

      const specMap = new Map<string, any>();
      specs.forEach(s => specMap.set(s.id, s));

      const sensorMap = new Map<string, any>();
      sensors.forEach(s => sensorMap.set(s.id, s));

      // 找出所有有异常的设备实例 (Sensor -> SensorMonitoring -> DeviceInst)
      const anomalousDevices = new Set<string>();
      monitorings.forEach(mon => {
        if (!mon.sensor_id || !mon.device_inst_id) return;
        const sensor = sensorMap.get(mon.sensor_id);
        if (sensor && sensor.anomaly > 0) {
          anomalousDevices.add(mon.device_inst_id);
        }
      });

      // 将设备实例统计累加到分类树 (自底向上，汇聚到顶层)
      insts.forEach(inst => {
        const spec = specMap.get(inst.device_spec_id);
        if (!spec) return;
        const leafCatId = spec.device_category_id;
        const isAnomaly = anomalousDevices.has(inst.id) ? 1 : 0;

        let currId = leafCatId;
        while (currId) {
          const cat = catMap.get(currId);
          if (!cat) break;
          cat.total += 1;
          cat.anomaly += isAnomaly;
          currId = cat.parent_id;
        }
      });

      // 组装父子层级结构
      const roots: any[] = [];
      catMap.forEach(cat => {
        if (cat.parent_id && catMap.has(cat.parent_id)) {
          const parent = catMap.get(cat.parent_id);
          if (parent) {
            parent.childrenMap.set(cat.id, cat);
          }
        } else {
          roots.push(cat);
        }
      });

      // 递归生成旭日图数据格式 (包含即使总数为0的分类，保证结构完整显示)
      const convertToSunburst = (nodes: any[]): any[] => {
        return nodes.map(n => {
          const hasAnomaly = n.anomaly > 0;
          const children = convertToSunburst(Array.from(n.childrenMap.values()));
          
          let childrenValueSum = 0;
          children.forEach(c => { childrenValueSum += c.value; });

          // 叶子节点赋予基础占位权重1以保证空类目也能渲染；父节点取 n.total 与子节点权重和的最大值
          const nodeValue = children.length > 0 
            ? Math.max(n.total, childrenValueSum)
            : Math.max(n.total, 1);

          let color = undefined;
          if (hasAnomaly) {
            color = '#ff4d4f'; // 异常状态使用红色
          } else if (n.total === 0) {
            color = '#e8e8e8'; // 空分类置灰处理
          }

          return {
            name: n.name,
            realTotal: n.total,
            anomaly: n.anomaly,
            value: nodeValue,
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

      const sunburstData = convertToSunburst(roots);

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
            label: { show: true, formatter: (params: any) => `${params.name}\n${params.data.realTotal}台` }
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
  }, [data, categories, specs, insts, monitorings, sensors]); 

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

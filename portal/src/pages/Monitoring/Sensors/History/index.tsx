import React, { useEffect, useRef, useState } from 'react';
import { PageContainer } from '@ant-design/pro-components';
import { Card, Select, Space, message, Spin, Typography, Checkbox } from 'antd';
import { useParams, useSearchParams, useNavigate } from '@umijs/max';
import * as echarts from 'echarts';
import dayjs from 'dayjs';

import { getSensorHistory } from '@/services/sensorTrends';

const { Text } = Typography;

const HistoryPage = () => {
  const { sn } = useParams<{ sn: string }>();
  const [searchParams] = useSearchParams();
  const locationName = searchParams.get('location') || '未知测点';
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState('1w');
  const [windowSize, setWindowSize] = useState('auto');
  const [meta, setMeta] = useState<any>({});
  const [chartData, setChartData] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'temp' | 'vibration'>('temp');
  const [selectedVibs, setSelectedVibs] = useState<string[]>(['rms_m']); // 默认只展示综合振动

  const chartRef = useRef<HTMLDivElement>(null);

  // 根据传感器安装方向推算 XYZ 对应的真实物理意义 (假设安装时遵守了 X/Y 对齐规范)
  const getAxisLabels = (direction?: string) => {
    switch (direction) {
      case 'vertical': // 垂直安装：Z轴为垂直，X水平，Y轴向
        return { x: 'X轴(水平)', y: 'Y轴(轴向)', z: 'Z轴(垂直)' };
      case 'horizontal': // 水平安装：Z轴为水平，X垂直，Y轴向
        return { x: 'X轴(垂直)', y: 'Y轴(轴向)', z: 'Z轴(水平)' };
      case 'axial': // 轴向安装：Z轴为轴向，X垂直，Y水平
        return { x: 'X轴(垂直)', y: 'Y轴(水平)', z: 'Z轴(轴向)' };
      default:
        return { x: 'X轴', y: 'Y轴', z: 'Z轴' };
    }
  };

  // 获取灰色缺省遮罩配置：自动找到 null 的范围
  const getGapMarkArea = (dataArr: (number | null)[], times: string[]) => {
    const markAreas = [];
    let gapStartIndex = -1;

    for (let i = 0; i < dataArr.length; i++) {
      if (dataArr[i] === null) {
        if (gapStartIndex === -1) gapStartIndex = i;
      } else {
        if (gapStartIndex !== -1) {
          const start = Math.max(0, gapStartIndex - 1);
          markAreas.push([{ xAxis: times[start] }, { xAxis: times[i] }]);
          gapStartIndex = -1;
        }
      }
    }
    // 结尾如果也是缺失的
    if (gapStartIndex !== -1) {
      const start = Math.max(0, gapStartIndex - 1);
      markAreas.push([{ xAxis: times[start] }, { xAxis: times[dataArr.length - 1] }]);
    }

    if (!markAreas.length) return undefined;

    return {
      itemStyle: { color: 'rgba(200, 200, 200, 0.2)' },
      label: { show: true, position: 'insideTop', color: '#888', formatter: '设备离线/数据缺失', padding: [10, 0, 0, 0] },
      data: markAreas,
    };
  };

  const fetchData = async () => {
    if (!sn) return;
    setLoading(true);
    try {
      const res = await getSensorHistory(sn, range, windowSize);
      
      // 兼容判断：针对外层带有 { code, message, data } 的原生接口返回解包
      const payload = res?.data?.timestamps ? res.data : res;

      if (!payload || !payload.timestamps) {
        return;
      }

      setMeta(payload.meta || {});
      setChartData(payload); // 缓存数据给渲染副作用使用
    } catch (err: any) {
      message.error(err.message || '数据拉取失败');
    } finally {
      setLoading(false);
    }
  };

  // ECharts 渲染与 Tab 切换逻辑
  useEffect(() => {
    if (!chartRef.current || !chartData) return;
    
    const chart = echarts.getInstanceByDom(chartRef.current) || echarts.init(chartRef.current);
    const times = (chartData.timestamps || []).map((t: string) => dayjs(t).format('YYYY-MM-DD HH:mm'));
    const gapMarkArea = chartData.series?.temperature ? getGapMarkArea(chartData.series.temperature, times) : undefined;

    const labels = getAxisLabels(meta.direction);

    if (activeTab === 'temp') {
      const candlestickData = times.map((_, i) => {
        const max = chartData.series?.temperature?.[i];
        if (max === null || max === undefined) return '-'; 
        const min = chartData.series?.temp_min?.[i] ?? max;
        const first = chartData.series?.temp_first?.[i] ?? max;
        const last = chartData.series?.temp_last?.[i] ?? max;
        return [first, last, min, max];
      });

      chart?.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
        grid: { top: 40, left: 40, right: 40, bottom: 40, containLabel: true },
        xAxis: { type: 'category', data: times, boundaryGap: true },
        yAxis: { type: 'value', name: '温度区间 (°C)', scale: true },
        series: [
          {
            name: '温度区间 (Candlestick)',
            type: 'candlestick',
            data: candlestickData,
            barMaxWidth: 16,
            itemStyle: { 
              color: '#ff4d4f',       // 阳线: 红色代表升温
              color0: '#52c41a',      // 阴线: 绿色代表降温
              borderColor: '#ff4d4f',
              borderColor0: '#52c41a',
              borderWidth: 2,
            },
            markArea: gapMarkArea,
          },
        ],
      }, true); // true 参数代表“完全覆盖上一轮配置(notMerge)”，非常关键
    } else {
      // 动态构建用户勾选了的展示维度系列
      const series: any[] = [];

      if (selectedVibs.includes('rms_m')) {
        const candlestickData = times.map((_, i) => {
          const max = chartData.series?.rms_m?.[i];
          if (max === null || max === undefined) return '-'; // Echarts 中 K线图的缺失断连必须用 '-' 而不能用 null
          const min = chartData.series?.rms_m_min?.[i] ?? max;
          const first = chartData.series?.rms_m_first?.[i] ?? max;
          const last = chartData.series?.rms_m_last?.[i] ?? max;
          // ECharts candlestick 所需格式: [期初(open), 期末(close), 最低(lowest), 最高(highest)]
          return [first, last, min, max];
        });

        series.push({
          name: '综合区间 (Candlestick)',
          type: 'candlestick',
          data: candlestickData,
          barMaxWidth: 16,
          itemStyle: { 
            color: '#ff4d4f',       // 阳线: 红色代表振动呈"上升/恶化"趋势 (收盘 > 开盘)
            color0: '#52c41a',      // 阴线: 绿色代表振动呈"下降/好转"趋势 (收盘 < 开盘)
            borderColor: '#ff4d4f',
            borderColor0: '#52c41a',
            borderWidth: 2,
          },
          markArea: gapMarkArea,
        });
      }
      if (selectedVibs.includes('rms_x')) {
        series.push({ name: `RMS ${labels.x}`, type: 'line', data: chartData.series?.rms_x || [], connectNulls: false, smooth: true, showSymbol: true, symbol: 'circle', symbolSize: 4, lineStyle: { width: 2, color: '#1890ff' }, itemStyle: { color: '#1890ff' } });
      }
      if (selectedVibs.includes('rms_y')) {
        series.push({ name: `RMS ${labels.y}`, type: 'line', data: chartData.series?.rms_y || [], connectNulls: false, smooth: true, showSymbol: true, symbol: 'circle', symbolSize: 4, lineStyle: { width: 2, color: '#52c41a' }, itemStyle: { color: '#52c41a' } });
      }
      if (selectedVibs.includes('rms_z')) {
        series.push({ name: `RMS ${labels.z}`, type: 'line', data: chartData.series?.rms_z || [], connectNulls: false, smooth: true, showSymbol: true, symbol: 'circle', symbolSize: 4, lineStyle: { width: 2, color: '#faad14' }, itemStyle: { color: '#faad14' } });
      }

      chart?.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
        grid: { top: 40, left: 40, right: 40, bottom: 40, containLabel: true },
        xAxis: { type: 'category', data: times, boundaryGap: true },
        yAxis: { type: 'value', name: '振动 RMS (mm/s)', scale: true },
        series: series,
      }, true);
    }
  }, [chartData, activeTab, selectedVibs, meta.direction]);

  useEffect(() => {
    fetchData();
  }, [sn, range, windowSize]);

  // Echarts 响应式与卸载处理
  useEffect(() => {
    const handleResize = () => {
      chartRef.current && echarts.getInstanceByDom(chartRef.current)?.resize();
    };
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      chartRef.current && echarts.getInstanceByDom(chartRef.current)?.dispose();
    };
  }, []);

  const labels = getAxisLabels(meta.direction);

  return (
    <PageContainer
      title={`测点分析: ${locationName}`}
      subTitle={`传感器 SN: ${sn}`}
      onBack={() => navigate(-1)}
      extra={[
        <Select key="range" value={range} onChange={setRange} style={{ width: 140 }}>
          <Select.Option value="1w">最近 1 周</Select.Option>
          <Select.Option value="2w">最近 2 周</Select.Option>
          <Select.Option value="1m">最近 1 个月</Select.Option>
          <Select.Option value="2m">最近 2 个月</Select.Option>
          <Select.Option value="3m">最近 3 个月</Select.Option>
        </Select>,
        <Select key="windowSize" value={windowSize} onChange={setWindowSize} style={{ width: 140 }}>
          <Select.Option value="auto">智能适配粒度</Select.Option>
          <Select.Option value="1h">1 小时 (1h)</Select.Option>
          <Select.Option value="4h">4 小时 (4h)</Select.Option>
          <Select.Option value="8h">8 小时 (8h)</Select.Option>
          <Select.Option value="12h">12 小时 (12h)</Select.Option>
          <Select.Option value="1d">1 天 (1d)</Select.Option>
        </Select>,
      ]}
    >
      <Spin spinning={loading}>
        <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
          {meta.patrol && (
            <Text type="secondary">
              数据说明: 此设备巡检频率为 {meta.patrol} 分钟/次，为保证图表清晰，当前时间跨度下您的数据点基于 <Text strong>{meta.window}</Text> 为窗口进行了最高值聚拢降采样。
            </Text>
          )}
          <Card 
            tabList={[
              { key: 'temp', tab: '温度趋势' },
              { key: 'vibration', tab: '振动趋势' }
            ]}
            activeTabKey={activeTab}
            onTabChange={(key) => setActiveTab(key as 'temp' | 'vibration')}
            title="分析图表 (断连期间自动标记为灰色离线区)"
            tabBarExtraContent={
              activeTab === 'vibration' && (
                <Checkbox.Group
                  options={[
                    { label: '综合区间 (K线)', value: 'rms_m' },
                    { label: labels.x, value: 'rms_x' },
                    { label: labels.y, value: 'rms_y' },
                    { label: labels.z, value: 'rms_z' },
                  ]}
                  value={selectedVibs}
                  onChange={(vals) => setSelectedVibs(vals as string[])}
                />
              )
            }
          >
            <div ref={chartRef} style={{ width: '100%', height: 450 }} />
          </Card>
        </Space>
      </Spin>
    </PageContainer>
  );
};

export default HistoryPage;

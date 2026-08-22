import { useEffect, useMemo, useRef, useState } from 'react';
import { Card, Empty, Select, Space, Spin, Tabs, Typography, message } from 'antd';
import * as echarts from 'echarts';
import dayjs from 'dayjs';

import {
  DevicePointTrend,
  PointTrendValue,
  getDevicePointTrend,
} from '@/services/deviceHealthArchive';
import { calculateTrendLine } from '@/utils/trendline';

import styles from './index.less';

type TrendTab = 'temperature' | 'vibration' | 'displacement';

const RANGE_OPTIONS = [
  { label: '近 3 天', value: 3 },
  { label: '近 1 周', value: 7 },
  { label: '近 2 周', value: 14 },
  { label: '近 1 月', value: 30 },
  { label: '近 3 月', value: 90 },
  { label: '近半年', value: 180 },
  { label: '近 1 年', value: 365 },
];

const DEFAULT_WINDOWS: Record<number, number> = {
  3: 0,
  7: 60,
  14: 120,
  30: 240,
  90: 720,
  180: 1440,
  365: 1440,
};

const WINDOW_OPTIONS: Record<number, Array<{ label: string; value: number }>> = {
  3: [
    { label: '原始数据', value: 0 },
    { label: '1 小时', value: 60 },
    { label: '2 小时', value: 120 },
    { label: '4 小时', value: 240 },
  ],
  7: [
    { label: '1 小时', value: 60 },
    { label: '2 小时', value: 120 },
    { label: '4 小时', value: 240 },
    { label: '8 小时', value: 480 },
  ],
  14: [
    { label: '2 小时', value: 120 },
    { label: '4 小时', value: 240 },
    { label: '8 小时', value: 480 },
    { label: '12 小时', value: 720 },
  ],
  30: [
    { label: '4 小时', value: 240 },
    { label: '8 小时', value: 480 },
    { label: '12 小时', value: 720 },
    { label: '24 小时', value: 1440 },
  ],
  90: [
    { label: '12 小时', value: 720 },
    { label: '24 小时', value: 1440 },
  ],
  180: [{ label: '24 小时', value: 1440 }],
  365: [{ label: '24 小时', value: 1440 }],
};

const windowLabel = (minutes: number) => {
  if (minutes === 0) return '原始数据';
  if (minutes < 60) return `${minutes} 分钟`;
  return `${minutes / 60} 小时`;
};

function withRawGaps(data: DevicePointTrend) {
  if (!data.meta.raw || data.timestamps.length < 2) return data;
  const timestamps: string[] = [];
  const temperature: Array<PointTrendValue | null> = [];
  const vibration: Array<PointTrendValue | null> = [];
  const gapMs = Math.max(1, data.meta.patrolMinutes) * 60_000 * 1.5;

  data.timestamps.forEach((timestamp, index) => {
    if (index > 0) {
      const previous = dayjs(data.timestamps[index - 1]).valueOf();
      const current = dayjs(timestamp).valueOf();
      if (current - previous > gapMs) {
        timestamps.push(dayjs(previous + Math.min(current - previous, gapMs)).toISOString());
        temperature.push(null);
        vibration.push(null);
      }
    }
    timestamps.push(timestamp);
    temperature.push(data.temperature[index] || null);
    vibration.push(data.vibration[index] || null);
  });
  return { ...data, timestamps, temperature, vibration };
}

const PointTrendCard = ({
  deviceId,
  locationId,
  locationName,
}: {
  deviceId: string;
  locationId: string;
  locationName: string;
}) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const [rangeDays, setRangeDays] = useState(3);
  const [windowMinutes, setWindowMinutes] = useState(DEFAULT_WINDOWS[3]);
  const [activeTab, setActiveTab] = useState<TrendTab>('temperature');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<DevicePointTrend | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getDevicePointTrend(deviceId, { locationId, rangeDays, windowMinutes })
      .then((result) => {
        if (active) setData(withRawGaps(result));
      })
      .catch((error: any) => {
        if (active) {
          setData(null);
          message.error(error?.data?.detail || error?.message || '测点历史曲线加载失败');
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [deviceId, locationId, rangeDays, windowMinutes]);

  const chartOption = useMemo(() => {
    if (!data) return null;
    
    const times = data.timestamps.map((timestamp) =>
      dayjs(timestamp).format(rangeDays <= 7 ? 'MM-DD HH:mm' : 'YYYY-MM-DD'),
    );

    const series = [];
    let yAxis: any;
    let tooltipFormatter: any;

    if (activeTab === 'temperature') {
      const source = data.temperature;
      const values = source.map((item) => (item ? item.value : null));
      series.push({
        name: '温度',
        type: 'line',
        data: values,
        connectNulls: false,
        showSymbol: data.timestamps.length <= 100,
        symbolSize: 5,
        sampling: 'lttb',
        lineStyle: { width: 2, color: '#fa8c16' },
        itemStyle: { color: '#fa8c16' },
        areaStyle: { opacity: 0.06 },
      });
      yAxis = { type: 'value', name: '°C', scale: true };
      
      tooltipFormatter = (params: any[]) => {
        const index = params?.[0]?.dataIndex;
        const item = source[index];
        if (!item) return `${times[index]}<br/>无数据`;
        const lines = [
          dayjs(data.timestamps[index]).format('YYYY-MM-DD HH:mm'),
          `温度：${values[index]?.toFixed(3)} °C`,
        ];
        if (!data.meta.raw) {
          lines.push(
            `最小：${item.min?.toFixed(3) ?? '-'} °C`,
            `平均：${item.value?.toFixed(3) ?? '-'} °C`,
            `最大：${item.max?.toFixed(3) ?? '-'} °C`,
            `末次：${item.last?.toFixed(3) ?? '-'} °C`,
            `采样：${item.count} 次`,
          );
        }
        return lines.join('<br/>');
      };
    } else if (activeTab === 'vibration') {
      const source = data.vibration;
      const values = source.map((item) => (item ? (!data.meta.raw ? item.max : item.value) : null));
      const trendData = calculateTrendLine(data.timestamps, values);
      series.push({
        name: '速度 RMS',
        type: 'line',
        data: values,
        connectNulls: false,
        showSymbol: data.timestamps.length <= 100,
        symbolSize: 5,
        sampling: 'lttb',
        lineStyle: { width: 2, color: '#1677ff' },
        itemStyle: { color: '#1677ff' },
        areaStyle: { opacity: 0.06 },
        markLine: trendData ? {
          data: trendData.markLineData,
          symbol: 'none',
          label: { formatter: `${trendData.slopePerHour.toFixed(3)} / ${trendData.amplitude.toFixed(3)}`, position: 'end' },
          lineStyle: { type: 'dashed', color: '#1677ff' },
          tooltip: { formatter: `Slope: ${trendData.slopePerHour.toFixed(3)}, Amp: ${trendData.amplitude.toFixed(3)}` }
        } : undefined
      });
      yAxis = { type: 'value', name: 'mm/s', scale: true };
      
      tooltipFormatter = (params: any[]) => {
        const index = params?.[0]?.dataIndex;
        const item = source[index];
        if (!item) return `${times[index]}<br/>无数据`;
        const lines = [
          dayjs(data.timestamps[index]).format('YYYY-MM-DD HH:mm'),
          `速度 (RMS)：${values[index]?.toFixed(3)} mm/s`,
        ];
        if (!data.meta.raw) {
          lines.push(
            `最小：${item.min?.toFixed(3) ?? '-'} mm/s`,
            `最大：${item.max?.toFixed(3) ?? '-'} mm/s`,
            `采样：${item.count} 次`,
          );
        }
        return lines.join('<br/>');
      };
    } else {
      const source = data.displacement;
      const values = source.map((item) => (item ? (!data.meta.raw ? item.max : item.value) : null));
      const trendData = calculateTrendLine(data.timestamps, values);
      series.push({
        name: '位移 P-P',
        type: 'line',
        data: values,
        connectNulls: false,
        showSymbol: data.timestamps.length <= 100,
        symbolSize: 5,
        sampling: 'lttb',
        lineStyle: { width: 2, color: '#13c2c2' },
        itemStyle: { color: '#13c2c2' },
        areaStyle: { opacity: 0.06 },
        markLine: trendData ? {
          data: trendData.markLineData,
          symbol: 'none',
          label: { formatter: `${trendData.slopePerHour.toFixed(3)} / ${trendData.amplitude.toFixed(3)}`, position: 'end' },
          lineStyle: { type: 'dashed', color: '#13c2c2' },
          tooltip: { formatter: `Slope: ${trendData.slopePerHour.toFixed(3)}, Amp: ${trendData.amplitude.toFixed(3)}` }
        } : undefined
      });
      yAxis = { type: 'value', name: 'um', scale: true };
      
      tooltipFormatter = (params: any[]) => {
        const index = params?.[0]?.dataIndex;
        const item = source[index];
        if (!item) return `${times[index]}<br/>无数据`;
        const lines = [
          dayjs(data.timestamps[index]).format('YYYY-MM-DD HH:mm'),
          `位移 (P-P)：${values[index]?.toFixed(3)} um`,
        ];
        if (!data.meta.raw) {
          lines.push(
            `最小：${item.min?.toFixed(3) ?? '-'} um`,
            `最大：${item.max?.toFixed(3) ?? '-'} um`,
          );
        }
        return lines.join('<br/>');
      };
    }

    return {
      animation: false,
      tooltip: {
        trigger: 'axis',
        formatter: tooltipFormatter,
      },
      grid: { top: 36, left: 56, right: activeTab === 'temperature' ? 26 : 100, bottom: 76 },
      xAxis: {
        type: 'category',
        data: times,
        boundaryGap: false,
        axisLabel: { hideOverlap: true },
      },
      yAxis,
      dataZoom: [
        { type: 'inside', filterMode: 'none' },
        { type: 'slider', height: 22, bottom: 18, filterMode: 'none' },
      ],
      series,
    };
  }, [activeTab, data, rangeDays]);

  useEffect(() => {
    if (!chartRef.current || !chartOption) return;
    const chart = echarts.getInstanceByDom(chartRef.current) || echarts.init(chartRef.current);
    chart.setOption(chartOption, true);
  }, [chartOption]);

  useEffect(() => {
    const resize = () => {
      if (chartRef.current) echarts.getInstanceByDom(chartRef.current)?.resize();
    };
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      if (chartRef.current) echarts.getInstanceByDom(chartRef.current)?.dispose();
    };
  }, []);

  return (
    <Card
      className={styles.trendCard}
      title={`${locationName} · 历史曲线`}
      extra={
        <Space wrap>
          <Typography.Text type="secondary">时间范围</Typography.Text>
          <Select
            value={rangeDays}
            options={RANGE_OPTIONS}
            style={{ width: 112 }}
            onChange={(value) => {
              setRangeDays(value);
              setWindowMinutes(DEFAULT_WINDOWS[value]);
            }}
          />
          <Typography.Text type="secondary">显示窗口</Typography.Text>
          <Select
            value={windowMinutes}
            options={WINDOW_OPTIONS[rangeDays]}
            style={{ width: 112 }}
            onChange={setWindowMinutes}
          />
        </Space>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as TrendTab)}
        items={[
          { key: 'temperature', label: '温度' },
          { key: 'vibration', label: '振动 (速度)' },
          { key: 'displacement', label: '振动 (位移)' },
        ]}
      />
      <Spin spinning={loading}>
        {data && data.meta.pointCount > 0 ? (
          <>
            <Typography.Text type="secondary" className={styles.trendHint}>
              {data.meta.raw
                ? `按实际采样时间展示，共 ${data.meta.pointCount} 个数据点`
                : `每 ${windowLabel(data.meta.windowMinutes)} 汇总；温度显示平均值，振动显示窗口最大值`}
            </Typography.Text>
            <div ref={chartRef} className={styles.trendChart} />
          </>
        ) : (
          <Empty description="该测点在所选时间范围内没有趋势数据" />
        )}
      </Spin>
    </Card>
  );
};

export default PointTrendCard;

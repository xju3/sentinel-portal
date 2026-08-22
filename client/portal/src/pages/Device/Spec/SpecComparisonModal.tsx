import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Empty, Select, Space, Spin, Tabs, Typography, message, Radio, Row, Col } from 'antd';
import * as echarts from 'echarts';
import dayjs from 'dayjs';
import { useNavigate } from '@umijs/max';

import {
  DeviceSpec,
  DeviceSpecComparison,
  getDeviceSpecComparison,
} from '@/services/deviceSpec';
import { ProcessDevice, listAllProcessDevices } from '@/services/process';
import { calculateTrendLine } from '@/utils/trendline';

import styles from './index.less';

type TrendTab = 'temperature' | 'vibration' | 'displacement';

const SERIES_COLORS = [
  '#1677FF',
  '#52C41A',
  '#FA8C16',
  '#F5222D',
  '#722ED1',
  '#13C2C2',
  '#EB2F96',
  '#FADB14',
  '#A0D911',
  '#FA541C',
];

const RANGE_OPTIONS = [
  { label: '近 1 天', value: 1 },
  { label: '近 3 天', value: 3 },
  { label: '近 1 周', value: 7 },
  { label: '近 2 周', value: 14 },
  { label: '近 1 月', value: 30 },
  { label: '近 3 月', value: 90 },
  { label: '近半年', value: 180 },
  { label: '近 1 年', value: 365 },
];

const DEFAULT_WINDOWS: Record<number, number> = {
  1: 0,
  3: 0,
  7: 60,
  14: 120,
  30: 240,
  90: 720,
  180: 1440,
  365: 1440,
};

const WINDOW_OPTIONS: Record<number, Array<{ label: string; value: number }>> = {
  1: [
    { label: '原始数据', value: 0 },
    { label: '30 分钟', value: 30 },
    { label: '1 小时', value: 60 },
  ],
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

const toErrorMessage = (error: any) =>
  error?.data?.detail || error?.message || '设备趋势对比加载失败';

const SpecComparisonContent = ({
  spec,
  defaultGroupId,
  refreshKey,
  specSelector,
}: {
  spec: DeviceSpec | null;
  defaultGroupId?: string;
  refreshKey?: number;
  specSelector?: ReactNode;
}) => {
  const navigate = useNavigate();
  const chartRef = useRef<HTMLDivElement>(null);
  const requestSeq = useRef(0);
  const [groupId, setGroupId] = useState<string>();
  const [locationId, setLocationId] = useState<string>();
  const [rangeDays, setRangeDays] = useState(1);
  const [windowMinutes, setWindowMinutes] = useState(0);
  const [activeTab, setActiveTab] = useState<TrendTab>('temperature');
  const [loading, setLoading] = useState(false);
  const [groupLoading, setGroupLoading] = useState(false);
  const [compatibleGroups, setCompatibleGroups] = useState<ProcessDevice[]>([]);
  const [data, setData] = useState<DeviceSpecComparison | null>(null);

  const loadComparison = async (
    selectedGroupId: string,
    selectedLocationId: string | undefined,
    selectedRangeDays: number,
    selectedWindowMinutes: number,
  ) => {
    if (!spec) return;
    const seq = ++requestSeq.current;
    setLoading(true);
    try {
      const result = await getDeviceSpecComparison(spec.id, {
        processDeviceId: selectedGroupId,
        locationId: selectedLocationId,
        rangeDays: selectedRangeDays,
        windowMinutes: selectedWindowMinutes,
      });
      if (seq !== requestSeq.current) return;
      setData(result);
      setLocationId(
        result.selectedLocationId ||
          (result.locations.length > 0 ? result.locations[0].id : undefined),
      );
    } catch (error) {
      if (seq !== requestSeq.current) return;
      setData(null);
      message.error(toErrorMessage(error));
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (!spec) return;
    let active = true;
    setGroupLoading(true);
    setCompatibleGroups([]);
    setGroupId(undefined);
    setLocationId(undefined);
    setRangeDays(1);
    setWindowMinutes(0);
    setActiveTab('temperature');
    setData(null);
    listAllProcessDevices(spec.id)
      .then((items) => {
        if (!active) return;
        setCompatibleGroups(items);
        const initialGroupId =
          defaultGroupId && items.some((item) => item.id === defaultGroupId)
            ? defaultGroupId
            : items.length > 0
              ? items[0].id
              : undefined;
        setGroupId(initialGroupId);
        if (initialGroupId) {
          void loadComparison(initialGroupId, undefined, 1, 0);
        }
      })
      .catch((error) => {
        if (active) message.error(toErrorMessage(error));
      })
      .finally(() => {
        if (active) setGroupLoading(false);
      });
    return () => {
      active = false;
    };
  }, [spec?.id, defaultGroupId]);

  useEffect(() => {
    if (refreshKey === undefined || refreshKey === 0) return;
    if (groupId) {
      void loadComparison(groupId, locationId, rangeDays, windowMinutes);
    }
  }, [refreshKey]);

  const chartOption = useMemo(() => {
    if (!data || data.meta.pointCount === 0) return null;
    const locationName = data.selectedLocation?.name || '未命名测点';
    const chartSeries: any[] = [];
    
    let unit = '°C';
    if (activeTab === 'vibration') unit = 'mm/s';
    if (activeTab === 'displacement') unit = 'um';

    data.series.forEach((item, deviceIndex) => {
      let source;
      if (activeTab === 'temperature') source = item.temperature;
      else if (activeTab === 'vibration') source = item.vibration;
      else source = item.displacement;

      const points: Array<[string, number | null]> = [];
      item.timestamps.forEach((timestamp, index) => {
        const value = source?.[index];
        points.push([timestamp, value ? (data.meta.raw ? value.value : value.max) : null]);
      });
      const trendData = (activeTab === 'vibration' || activeTab === 'displacement') 
        ? calculateTrendLine(item.timestamps, points.map(p => p[1]))
        : undefined;

      chartSeries.push({
        name: `${item.device.code} · ${locationName}`,
        type: 'line',
        data: points,
        smooth: true,
        showSymbol: false,
        itemStyle: { color: item.device.color || SERIES_COLORS[deviceIndex % SERIES_COLORS.length] },
        emphasis: { focus: 'series' },
        markLine: trendData ? {
          data: trendData.markLineData,
          symbol: 'none',
          label: { formatter: `${trendData.slopePerHour.toFixed(3)} / ${trendData.amplitude.toFixed(3)}`, position: 'end' },
          lineStyle: { type: 'dashed', color: item.device.color || SERIES_COLORS[deviceIndex % SERIES_COLORS.length] },
          tooltip: { formatter: `${item.device.code} - Slope: ${trendData.slopePerHour.toFixed(3)}, Amp: ${trendData.amplitude.toFixed(3)}` }
        } : undefined,
      });
    });

    return {
      animation: false,
      color: data.series.map(item => item.device.color || SERIES_COLORS[0]),
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: number | null) => {
          if (value === null || value === undefined) return '无数据';
          return `${Number(value).toFixed(3)} ${unit}`;
        },
      },
      grid: { top: 24, left: 62, right: activeTab === 'temperature' ? 28 : 100, bottom: 72 },
      xAxis: {
        type: 'time',
        axisLabel: {
          hideOverlap: true,
          formatter: (value: number) => dayjs(value).format(rangeDays <= 7 ? 'MM-DD HH:mm' : 'YYYY-MM-DD'),
        },
      },
      yAxis: { type: 'value', name: unit, scale: true },
      dataZoom: [
        { type: 'inside', filterMode: 'none' },
        { type: 'slider', height: 22, bottom: 18, filterMode: 'none' },
      ],
      series: chartSeries,
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

  const groupOptions = compatibleGroups.map((item) => ({
    value: item.id,
    label: item.process?.name || item.code,
  }));

  return (
    <div className={styles.comparisonPageContent}>
      <div className={styles.comparisonFilters} style={{ width: '100%', paddingBottom: 16 }}>
        <Row gutter={[24, 16]}>
          {/* 第一列（上）：设备规格 + 设备分组 */}
          <Col span={14}>
            <Space size="large" wrap>
              {specSelector && (
                <Space>
                  {specSelector}
                </Space>
              )}
              
              <Space>
                <Typography.Text type="secondary">设备分组</Typography.Text>
                <Radio.Group
                  value={groupId}
                  onChange={(e) => {
                    const value = e.target.value;
                    setGroupId(value);
                    setLocationId(undefined);
                    setData(null);
                    void loadComparison(value, undefined, rangeDays, windowMinutes);
                  }}
                  optionType="button"
                  buttonStyle="solid"
                >
                  {groupLoading ? (
                    <Radio.Button disabled value="loading">正在加载...</Radio.Button>
                  ) : groupOptions.length > 0 ? (
                    groupOptions.map((item) => (
                      <Radio.Button key={item.value} value={item.value}>
                        {item.label}
                      </Radio.Button>
                    ))
                  ) : (
                    <Radio.Button disabled value="empty">暂无分组</Radio.Button>
                  )}
                </Radio.Group>
              </Space>
            </Space>
          </Col>

          {/* 第二列（上）：对比测点 */}
          <Col span={10}>
            <Space wrap>
              <Typography.Text type="secondary">对比测点</Typography.Text>
              <Radio.Group
                value={locationId}
                disabled={!groupId || !data?.locations.length}
                onChange={(e) => {
                  const value = e.target.value;
                  setLocationId(value);
                  if (groupId) void loadComparison(groupId, value, rangeDays, windowMinutes);
                }}
                optionType="button"
                buttonStyle="solid"
              >
                {!groupId ? (
                  <Radio.Button disabled value="empty">请先选择分组</Radio.Button>
                ) : loading && !data?.locations?.length ? (
                  <Radio.Button disabled value="loading">正在加载...</Radio.Button>
                ) : data?.locations?.length ? (
                  data.locations.map((item) => (
                    <Radio.Button key={item.id} value={item.id}>
                      {item.name}（{item.deviceCount} 台）
                    </Radio.Button>
                  ))
                ) : (
                  <Radio.Button disabled value="empty">暂无测点</Radio.Button>
                )}
              </Radio.Group>
            </Space>
          </Col>

          {/* 第一列（下）：时间范围 */}
          <Col span={14}>
            <Space wrap>
              <Typography.Text type="secondary">时间范围</Typography.Text>
              <Radio.Group
                value={rangeDays}
                onChange={(e) => {
                  const value = e.target.value;
                  const nextWindow = DEFAULT_WINDOWS[value];
                  setRangeDays(value);
                  setWindowMinutes(nextWindow);
                  if (groupId) void loadComparison(groupId, locationId, value, nextWindow);
                }}
                optionType="button"
                buttonStyle="solid"
              >
                {RANGE_OPTIONS.map((item) => (
                  <Radio.Button key={item.value} value={item.value}>
                    {item.label}
                  </Radio.Button>
                ))}
              </Radio.Group>
            </Space>
          </Col>

          {/* 第二列（下）：显示窗口 */}
          <Col span={10}>
            <Space wrap>
              <Typography.Text type="secondary">显示窗口</Typography.Text>
              <Radio.Group
                value={windowMinutes}
                onChange={(e) => {
                  const value = e.target.value;
                  setWindowMinutes(value);
                  if (groupId) void loadComparison(groupId, locationId, rangeDays, value);
                }}
                optionType="button"
                buttonStyle="solid"
              >
                {WINDOW_OPTIONS[rangeDays].map((item) => (
                  <Radio.Button key={item.value} value={item.value}>
                    {item.label}
                  </Radio.Button>
                ))}
              </Radio.Group>
            </Space>
          </Col>
        </Row>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as TrendTab)}
        items={[
          { key: 'temperature', label: '温度对比' },
          { key: 'vibration', label: '振动 (速度) 对比' },
          { key: 'displacement', label: '振动 (位移) 对比' },
        ]}
      />
      <Spin spinning={loading}>
        {!groupId ? (
          <Empty
            description={
              groupLoading
                ? '正在加载设备分组'
                : compatibleGroups.length === 0
                  ? '没有包含当前设备规格的设备分组'
                  : '请选择设备分组'
            }
          />
        ) : data && data.meta.deviceCount > 0 ? (
          <>
            <Typography.Text type="secondary" className={styles.comparisonHint}>
              测点：{data.selectedLocation?.name || '-'}；当前比较 {data.meta.deviceCount} 台设备，
              共 {data.meta.pointCount} 个数据点；
              {data.meta.raw ? '按实际采样时间展示' : `每 ${data.meta.windowMinutes} 分钟汇总`}
            </Typography.Text>
            {data.meta.pointCount > 0 ? (
              <div ref={chartRef} className={styles.comparisonChart} />
            ) : (
              <Empty description="这些设备的所选测点在当前时间范围内没有趋势数据" />
            )}
            <div className={styles.comparisonDevices}>
              {data.series.map((item, index) => (
                <div
                  key={item.device.id}
                  className={styles.comparisonDevice}
                  role="link"
                  tabIndex={0}
                  title={`查看 ${item.device.name} 的健康档案`}
                  onClick={() => {
                    navigate(`/device/${item.device.id}/health-archive`);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      navigate(`/device/${item.device.id}/health-archive`);
                    }
                  }}
                >
                  <span
                    className={styles.comparisonDeviceColor}
                    style={{ backgroundColor: item.device.color || SERIES_COLORS[index % SERIES_COLORS.length] }}
                  />
                  <span className={styles.comparisonDeviceIdentity}>
                    <Typography.Text ellipsis title={item.device.name}>
                      {item.device.name}
                    </Typography.Text>
                    <Typography.Text type="secondary" ellipsis title={item.device.code}>
                      {item.device.code}
                    </Typography.Text>
                    <Typography.Text
                      type="secondary"
                      ellipsis
                      title={data.selectedLocation?.name}
                      className={styles.comparisonDevicePoint}
                    >
                      测点：{data.selectedLocation?.name || '-'}
                    </Typography.Text>
                  </span>
                  <Typography.Text
                    type={item.timestamps.length > 0 ? 'secondary' : 'danger'}
                    className={styles.comparisonDeviceCount}
                  >
                    {item.timestamps.length > 0 ? `${item.timestamps.length} 个点` : '无数据'}
                  </Typography.Text>
                </div>
              ))}
            </div>
          </>
        ) : (
          <Empty description="该分组中没有配置当前规格和测点的设备" />
        )}
      </Spin>
    </div>
  );
};

export default SpecComparisonContent;

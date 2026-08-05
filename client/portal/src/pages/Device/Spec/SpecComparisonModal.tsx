import { useEffect, useMemo, useRef, useState } from 'react';
import { Empty, Select, Space, Spin, Tabs, Typography, message } from 'antd';
import * as echarts from 'echarts';
import dayjs from 'dayjs';
import { useNavigate } from '@umijs/max';

import {
  DeviceSpec,
  DeviceSpecComparison,
  getDeviceSpecComparison,
} from '@/services/deviceSpec';
import { ProcessDevice, listAllProcessDevices } from '@/services/process';

import styles from './index.less';

type TrendTab = 'temperature' | 'vibration';

const SERIES_COLORS = [
  '#1677ff',
  '#fa8c16',
  '#52c41a',
  '#722ed1',
  '#13c2c2',
  '#eb2f96',
  '#a0d911',
];

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

const toErrorMessage = (error: any) =>
  error?.data?.detail || error?.message || '设备趋势对比加载失败';

const SpecComparisonContent = ({
  spec,
  defaultGroupId,
}: {
  spec: DeviceSpec | null;
  defaultGroupId?: string;
}) => {
  const navigate = useNavigate();
  const chartRef = useRef<HTMLDivElement>(null);
  const requestSeq = useRef(0);
  const [groupId, setGroupId] = useState<string>();
  const [locationId, setLocationId] = useState<string>();
  const [rangeDays, setRangeDays] = useState(3);
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
          (result.locations.length === 1 ? result.locations[0].id : undefined),
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
    setRangeDays(3);
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
            : items.length === 1
              ? items[0].id
              : undefined;
        setGroupId(initialGroupId);
        if (initialGroupId) {
          void loadComparison(initialGroupId, undefined, 3, 0);
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

  const chartOption = useMemo(() => {
    if (!data || data.meta.pointCount === 0) return null;
    const isVibration = activeTab === 'vibration';
    const unit = isVibration ? 'mm/s' : '°C';
    const locationName = data.selectedLocation?.name || '未命名测点';
    const chartSeries = data.series.map((item) => {
      const source = isVibration ? item.vibration : item.temperature;
      const points: Array<[string, number | null]> = [];
      item.timestamps.forEach((timestamp, index) => {
        const value = source[index];
        points.push([
          timestamp,
          value
            ? isVibration && !data.meta.raw
              ? value.max
              : value.value
            : null,
        ]);
      });
      return {
        name: `${item.device.code} · ${locationName}`,
        type: 'line',
        data: points,
        smooth: true,
        showSymbol: false,
        emphasis: { focus: 'series' },
      };
    });
    return {
      animation: false,
      color: SERIES_COLORS,
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: number | null) =>
          value === null || value === undefined ? '无数据' : `${Number(value).toFixed(3)} ${unit}`,
      },
      grid: { top: 24, left: 62, right: 28, bottom: 72 },
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
    label: [item.code, item.sn, item.process?.name, item.status === 1 ? undefined : '已停用']
      .filter(Boolean)
      .join(' / '),
  }));

  return (
    <div className={styles.comparisonPageContent}>
      <Space wrap className={styles.comparisonFilters}>
        <Typography.Text type="secondary">设备分组</Typography.Text>
        <Select
          value={groupId}
          options={groupOptions}
          loading={groupLoading}
          showSearch
          optionFilterProp="label"
          getPopupContainer={(trigger) => trigger.parentElement || document.body}
          placeholder={groupLoading ? '正在加载设备分组' : '请选择设备分组'}
          style={{ width: 300 }}
          onChange={(value) => {
            setGroupId(value);
            setLocationId(undefined);
            setData(null);
            void loadComparison(value, undefined, rangeDays, windowMinutes);
          }}
        />
        <Typography.Text type="secondary">对比测点</Typography.Text>
        <Select
          value={locationId}
          disabled={!groupId || !data?.locations.length}
          options={(data?.locations || []).map((item) => ({
            value: item.id,
            label: `${item.name}（${item.deviceCount} 台）`,
          }))}
          getPopupContainer={(trigger) => trigger.parentElement || document.body}
          style={{ width: 190 }}
          onChange={(value) => {
            setLocationId(value);
            if (groupId) void loadComparison(groupId, value, rangeDays, windowMinutes);
          }}
        />
        <Typography.Text type="secondary">时间范围</Typography.Text>
        <Select
          value={rangeDays}
          options={RANGE_OPTIONS}
          getPopupContainer={(trigger) => trigger.parentElement || document.body}
          style={{ width: 112 }}
          onChange={(value) => {
            const nextWindow = DEFAULT_WINDOWS[value];
            setRangeDays(value);
            setWindowMinutes(nextWindow);
            if (groupId) void loadComparison(groupId, locationId, value, nextWindow);
          }}
        />
        <Typography.Text type="secondary">显示窗口</Typography.Text>
        <Select
          value={windowMinutes}
          options={WINDOW_OPTIONS[rangeDays]}
          getPopupContainer={(trigger) => trigger.parentElement || document.body}
          style={{ width: 112 }}
          onChange={(value) => {
            setWindowMinutes(value);
            if (groupId) void loadComparison(groupId, locationId, rangeDays, value);
          }}
        />
      </Space>

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as TrendTab)}
        items={[
          { key: 'temperature', label: '温度对比' },
          { key: 'vibration', label: '振动对比' },
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
                    style={{ backgroundColor: SERIES_COLORS[index % SERIES_COLORS.length] }}
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

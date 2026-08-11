import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeftOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-components';
import { useNavigate, useParams } from '@umijs/max';
import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Tooltip,
  Typography,
  message,
} from 'antd';
import dayjs from 'dayjs';

import {
  DeviceHealthArchive,
  HealthArchiveBucket,
  HealthArchiveBucketStatus,
  getDeviceHealthArchive,
} from '@/services/deviceHealthArchive';

import styles from './index.less';
import PointTrendCard from './PointTrendCard';
import DeviceFftCard from './DeviceFftCard';

const STATUS_META: Record<
  HealthArchiveBucketStatus,
  { label: string; color: string }
> = {
  normal: { label: '正常', color: '#52c41a' },
  attention: { label: '关注', color: '#faad14' },
  abnormal: { label: '异常', color: '#fa8c16' },
  warning: { label: '告警', color: '#f5222d' },
  critical: { label: '严重', color: '#820014' },
  missed: { label: '诊断缺口', color: '#8c8c8c' },
  waiting: { label: '等待补传', color: '#1677ff' },
  processing: { label: '处理中', color: '#13c2c2' },
  no_data: { label: '无数据', color: '#f0f0f0' },
};

const RANGE_OPTIONS = [
  { label: '近 1 天', value: 1 },
  { label: '近 3 天', value: 3 },
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
  { label: '近 1 年', value: 365 },
];

const INTERVAL_OPTIONS = [
  { label: '1 小时', value: 1 },
  { label: '4 小时', value: 4 },
  { label: '8 小时', value: 8 },
  { label: '24 小时', value: 24 },
];

const WEEKDAY_LABELS = ['日', '一', '二', '三', '四', '五', '六'];

const bucketTooltip = (bucket: HealthArchiveBucket) => {
  const meta = STATUS_META[bucket.status];
  return (
    <div>
      <div>{`${dayjs(bucket.startAt).format('YYYY-MM-DD HH:mm')} - ${dayjs(bucket.endAt).format('MM-DD HH:mm')}`}</div>
      <div>{`状态：${meta.label}`}</div>
      <div>{`完成诊断：${bucket.diagnosedCount} 次`}</div>
      {bucket.abnormalCount > 0 && <div>{`异常诊断：${bucket.abnormalCount} 次`}</div>}
      {bucket.missedCount > 0 && <div>{`未完成诊断：${bucket.missedCount} 次`}</div>}
      {bucket.waitingCount > 0 && <div>{`等待补传：${bucket.waitingCount} 次`}</div>}
    </div>
  );
};

const DeviceHealthArchivePage = () => {
  const { deviceId = '' } = useParams<{ deviceId: string }>();
  const navigate = useNavigate();
  const fullscreenRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [rangeDays, setRangeDays] = useState(1);
  const [intervalHours, setIntervalHours] = useState(1);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<DeviceHealthArchive | null>(null);
  const [selectedLocationId, setSelectedLocationId] = useState<string>();
  const [selectedDay, setSelectedDay] = useState<HealthArchiveBucket | null>(null);
  const [dayDetail, setDayDetail] = useState<DeviceHealthArchive | null>(null);
  const [dayDetailLoading, setDayDetailLoading] = useState(false);
  const calendarMode = rangeDays >= 30;

  useEffect(() => {
    const handleFullscreenChange = () => {
      setFullscreen(document.fullscreenElement === fullscreenRef.current);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (fullscreenRef.current) {
        await fullscreenRef.current.requestFullscreen();
      }
    } catch (error: any) {
      message.error(error?.message || '无法切换全屏显示');
    }
  };

  const loadData = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try {
      const endAt = dayjs();
      const startAt = calendarMode
        ? endAt.startOf('day').subtract(rangeDays - 1, 'day')
        : endAt.subtract(rangeDays, 'day');
      const result = await getDeviceHealthArchive(deviceId, {
        startAt: startAt.toISOString(),
        endAt: endAt.toISOString(),
        intervalHours: calendarMode ? 24 : intervalHours,
        locationId: selectedLocationId,
      });
      setData(result);
    } catch (error: any) {
      message.error(error?.data?.detail || error?.message || '健康档案加载失败');
    } finally {
      setLoading(false);
    }
  }, [calendarMode, deviceId, intervalHours, rangeDays, selectedLocationId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const activeLocationId = selectedLocationId || data?.selectedLocationId || undefined;
  const selectedPoint = data?.points.find((point) => point.id === activeLocationId);

  const orderedBuckets = useMemo(
    () =>
      data
        ? [...data.buckets].sort(
            (left, right) => dayjs(left.startAt).valueOf() - dayjs(right.startAt).valueOf(),
          )
        : [],
    [data],
  );

  const bucketGroups = useMemo(() => {
    const bucketsPerDay = Math.max(1, Math.floor(24 / intervalHours));
    const groups: HealthArchiveBucket[][] = [];
    for (let index = 0; index < orderedBuckets.length; index += bucketsPerDay) {
      groups.push(orderedBuckets.slice(index, index + bucketsPerDay));
    }
    return groups;
  }, [intervalHours, orderedBuckets]);

  const calendarMonths = useMemo(() => {
    const months = new Map<string, HealthArchiveBucket[]>();
    for (const bucket of orderedBuckets) {
      const key = dayjs(bucket.startAt).format('YYYY-MM');
      const current = months.get(key) || [];
      current.push(bucket);
      months.set(key, current);
    }
    return Array.from(months.entries()).map(([key, buckets]) => ({
      key,
      label: dayjs(`${key}-01`).format('YYYY年M月'),
      buckets,
      leadingDays: dayjs(buckets[0].startAt).day(),
      abnormalDays: buckets.filter((bucket) =>
        ['attention', 'abnormal', 'warning', 'critical'].includes(bucket.status),
      ).length,
    }));
  }, [orderedBuckets]);

  const openDayDetail = useCallback(
    async (bucket: HealthArchiveBucket) => {
      if (!deviceId) return;
      setSelectedDay(bucket);
      setDayDetail(null);
      setDayDetailLoading(true);
      try {
        const dayStart = dayjs(bucket.startAt).startOf('day');
        setDayDetail(
          await getDeviceHealthArchive(deviceId, {
            startAt: dayStart.toISOString(),
            endAt: dayStart.add(1, 'day').toISOString(),
            intervalHours: 1,
            locationId: activeLocationId,
          }),
        );
      } catch (error: any) {
        message.error(error?.data?.detail || error?.message || '当日健康明细加载失败');
      } finally {
        setDayDetailLoading(false);
      }
    },
    [activeLocationId, deviceId],
  );

  return (
    <div ref={fullscreenRef} className={styles.fullscreenHost}>
      <PageContainer
      className={styles.archivePage}
      title={data ? `${data.device.name} · 健康档案` : '设备健康档案'}
      subTitle={data?.device.code}
      extra={[
        <Button
          key="fullscreen"
          icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
          onClick={() => void toggleFullscreen()}
        >
          {fullscreen ? '退出全屏' : '全屏'}
        </Button>,
        <Button key="back" icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
          返回
        </Button>,
        <Button key="reload" icon={<ReloadOutlined />} loading={loading} onClick={loadData}>
          刷新
        </Button>,
      ]}
    >
      <Card style={{ marginBottom: 16 }}>
        <Space size="large" wrap>
          <Space>
            <Typography.Text type="secondary">时间范围</Typography.Text>
            <Segmented
              options={RANGE_OPTIONS}
              value={rangeDays}
              onChange={(value) => setRangeDays(Number(value))}
            />
          </Space>
          {data && data.points.length > 1 && (
            <Space>
              <Typography.Text type="secondary">监测点</Typography.Text>
              <Select
                style={{ minWidth: 200 }}
                value={activeLocationId}
                getPopupContainer={(trigger) => trigger.parentElement || document.body}
                options={data.points.map((point) => ({
                  label: point.active ? point.name : `${point.name}（历史测点）`,
                  value: point.id,
                }))}
                onChange={(value) => setSelectedLocationId(value)}
              />
            </Space>
          )}
          {data && activeLocationId && (
            <Space>
              <Typography.Text type="secondary">当前传感器</Typography.Text>
              <Typography.Text>
                {selectedPoint?.sensor
                  ? [selectedPoint.sensor.sn, selectedPoint.sensor.description]
                      .filter(Boolean)
                      .join(' / ')
                  : ''}
              </Typography.Text>
            </Space>
          )}
          {calendarMode ? (
            <Typography.Text type="secondary">按自然日汇总，每格代表一天</Typography.Text>
          ) : (
            <Space>
              <Typography.Text type="secondary">时间粒度</Typography.Text>
              <Segmented
                options={INTERVAL_OPTIONS}
                value={intervalHours}
                onChange={(value) => setIntervalHours(Number(value))}
              />
            </Space>
          )}
        </Space>
      </Card>
      {deviceId && <DeviceFftCard deviceId={deviceId} rpm={data?.device?.rpm} />}

      <Spin spinning={loading}>
        {data ? (
          <>
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={12} md={6}>
                <Card className={styles.summaryCard}>
                  <Statistic title="完成诊断" value={data.summary.diagnosedCount} suffix="次" />
                </Card>
              </Col>
              <Col xs={12} md={6}>
                <Card className={styles.summaryCard}>
                  <Statistic
                    title="正常诊断"
                    value={data.summary.normalCount}
                    valueStyle={{ color: '#389e0d' }}
                    suffix="次"
                  />
                </Card>
              </Col>
              <Col xs={12} md={6}>
                <Card className={styles.summaryCard}>
                  <Statistic
                    title="异常诊断"
                    value={data.summary.abnormalCount}
                    valueStyle={{ color: '#cf1322' }}
                    suffix="次"
                  />
                </Card>
              </Col>
              <Col xs={12} md={6}>
                <Card className={styles.summaryCard}>
                  <Statistic
                    title="诊断缺口"
                    value={data.summary.missedCount}
                    valueStyle={{ color: data.summary.missedCount ? '#595959' : undefined }}
                    suffix="次"
                  />
                </Card>
              </Col>
            </Row>

            {(data.summary.waitingCount > 0 || data.summary.receivedCount > 0) && (
              <Alert
                showIcon
                type="info"
                style={{ marginBottom: 16 }}
                message={`当前有 ${data.summary.waitingCount} 条等待补传、${data.summary.receivedCount} 条正在处理`}
              />
            )}

            <Card
              title={
                calendarMode
                  ? `设备健康日历 · ${rangeDays === 365 ? '近1年' : `近${rangeDays}天`}`
                  : `健康时间轴 · ${data.range.intervalHours} 小时/格`
              }
            >
              {orderedBuckets.length ? (
                <>
                  {calendarMode ? (
                    <div className={styles.calendarMonths}>
                      {calendarMonths.map((month) => (
                        <section className={styles.calendarMonth} key={month.key}>
                          <div className={styles.monthHeader}>
                            <Typography.Text strong>{month.label}</Typography.Text>
                            <Typography.Text type={month.abnormalDays ? 'danger' : 'secondary'}>
                              {month.abnormalDays}个异常日
                            </Typography.Text>
                          </div>
                          <div className={styles.weekdayHeader}>
                            {WEEKDAY_LABELS.map((label) => (
                              <span key={label}>{label}</span>
                            ))}
                          </div>
                          <div className={styles.monthGrid}>
                            {Array.from({ length: month.leadingDays }, (_, index) => (
                              <span className={styles.calendarPlaceholder} key={`empty-${index}`} />
                            ))}
                            {month.buckets.map((bucket) => (
                              <Tooltip
                                key={bucket.startAt}
                                title={bucketTooltip(bucket)}
                                placement="top"
                              >
                                <button
                                  type="button"
                                  aria-label={`${dayjs(bucket.startAt).format('YYYY-MM-DD')}，${STATUS_META[bucket.status].label}`}
                                  className={`${styles.calendarDay} ${bucket.hasGap ? styles.gap : ''}`}
                                  style={{ background: STATUS_META[bucket.status].color }}
                                  onClick={() => void openDayDetail(bucket)}
                                />
                              </Tooltip>
                            ))}
                          </div>
                        </section>
                      ))}
                    </div>
                  ) : (
                    <div className={styles.timelineViewport}>
                      <div className={styles.timelineGroups}>
                        {bucketGroups.map((group, groupIndex) => (
                          <div className={styles.timelineRow} key={group[0].startAt}>
                            <div className={styles.rowLabel}>
                              <span>{dayjs(group[0].startAt).format('MM-DD HH:mm')}</span>
                              <span className={styles.rowLabelSeparator}>至</span>
                              <span>{dayjs(group[group.length - 1].endAt).format('MM-DD HH:mm')}</span>
                            </div>
                            <div
                              className={styles.timeline}
                              style={{
                                gridTemplateColumns: `repeat(${group.length}, minmax(10px, 40px))`,
                              }}
                            >
                              {group.map((bucket) => (
                                <Tooltip
                                  key={bucket.startAt}
                                  title={bucketTooltip(bucket)}
                                  placement="top"
                                >
                                  <span
                                    aria-label={`第 ${groupIndex + 1} 组，${STATUS_META[bucket.status].label}`}
                                    className={`${styles.bucket} ${bucket.hasGap ? styles.gap : ''}`}
                                    style={{ background: STATUS_META[bucket.status].color }}
                                  />
                                </Tooltip>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className={styles.legend}>
                    {Object.entries(STATUS_META).map(([status, meta]) => (
                      <span className={styles.legendItem} key={status}>
                        <span
                          className={styles.legendColor}
                          style={{ background: meta.color }}
                        />
                        {meta.label}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <Empty description="该时间范围内没有健康记录" />
              )}
            </Card>

            {activeLocationId && (
              <PointTrendCard
                deviceId={deviceId}
                locationId={activeLocationId}
                locationName={
                  data.points.find((point) => point.id === activeLocationId)?.name || '当前测点'
                }
              />
            )}
          </>
        ) : (
          !loading && <Empty description="暂无设备健康档案" />
        )}
      </Spin>

      <Drawer
        rootClassName={styles.archiveDrawer}
        title={
          selectedDay
            ? `${dayjs(selectedDay.startAt).format('YYYY年M月D日')} · 小时明细`
            : '当日小时明细'
        }
        width={720}
        open={selectedDay !== null}
        onClose={() => {
          setSelectedDay(null);
          setDayDetail(null);
        }}
      >
        <Spin spinning={dayDetailLoading}>
          {dayDetail ? (
            <>
              <Row gutter={[12, 12]}>
                <Col span={8}>
                  <Statistic title="完成诊断" value={dayDetail.summary.diagnosedCount} suffix="次" />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="异常诊断"
                    value={dayDetail.summary.abnormalCount}
                    valueStyle={{ color: '#cf1322' }}
                    suffix="次"
                  />
                </Col>
                <Col span={8}>
                  <Statistic title="诊断缺口" value={dayDetail.summary.missedCount} suffix="次" />
                </Col>
              </Row>
              <Typography.Title level={5} className={styles.dayDetailTitle}>
                24小时状态
                <Typography.Text type="secondary">（每格1小时，数字为完成诊断次数）</Typography.Text>
              </Typography.Title>
              <div className={styles.dayDetailTimeline}>
                {dayDetail.buckets.map((bucket) => (
                  <div className={styles.dayHour} key={bucket.startAt}>
                    <span className={styles.dayHourLabel}>
                      {dayjs(bucket.startAt).format('HH:00')}
                    </span>
                    <Tooltip title={bucketTooltip(bucket)}>
                      <span
                        className={`${styles.bucket} ${styles.dayHourBucket} ${bucket.hasGap ? styles.gap : ''}`}
                        style={{ background: STATUS_META[bucket.status].color }}
                      >
                        {bucket.diagnosedCount > 0 ? bucket.diagnosedCount : ''}
                      </span>
                    </Tooltip>
                  </div>
                ))}
              </div>
            </>
          ) : (
            !dayDetailLoading && <Empty description="该日期没有健康记录" />
          )}
        </Spin>
      </Drawer>
      </PageContainer>
    </div>
  );
};

export default DeviceHealthArchivePage;

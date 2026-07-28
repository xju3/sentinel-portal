import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-components';
import { useNavigate, useParams } from '@umijs/max';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Segmented,
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
  const [rangeDays, setRangeDays] = useState(7);
  const [intervalHours, setIntervalHours] = useState(1);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<DeviceHealthArchive | null>(null);

  const loadData = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try {
      const endAt = dayjs();
      const result = await getDeviceHealthArchive(deviceId, {
        startAt: endAt.subtract(rangeDays, 'day').toISOString(),
        endAt: endAt.toISOString(),
        intervalHours,
      });
      setData(result);
    } catch (error: any) {
      message.error(error?.data?.detail || error?.message || '健康档案加载失败');
    } finally {
      setLoading(false);
    }
  }, [deviceId, intervalHours, rangeDays]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const axisLabels = useMemo(() => {
    if (!data) return [];
    return [
      dayjs(data.range.startAt).format('YYYY-MM-DD HH:mm'),
      dayjs(data.range.startAt)
        .add((dayjs(data.range.endAt).diff(dayjs(data.range.startAt), 'minute') / 2), 'minute')
        .format('YYYY-MM-DD HH:mm'),
      dayjs(data.range.endAt).format('YYYY-MM-DD HH:mm'),
    ];
  }, [data]);

  return (
    <PageContainer
      className={styles.archivePage}
      title={data ? `${data.device.name} · 健康档案` : '设备健康档案'}
      subTitle={data?.device.code}
      extra={[
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
          <Space>
            <Typography.Text type="secondary">时间粒度</Typography.Text>
            <Segmented
              options={INTERVAL_OPTIONS}
              value={intervalHours}
              onChange={(value) => setIntervalHours(Number(value))}
            />
          </Space>
        </Space>
      </Card>

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

            <Card title={`健康时间轴 · ${data.range.intervalHours} 小时/格`}>
              {data.buckets.length ? (
                <>
                  <div className={styles.timelineViewport}>
                    <div className={styles.timeline}>
                      {data.buckets.map((bucket) => (
                        <Tooltip
                          key={bucket.startAt}
                          title={bucketTooltip(bucket)}
                          placement="top"
                        >
                          <span
                            className={`${styles.bucket} ${bucket.hasGap ? styles.gap : ''}`}
                            style={{ background: STATUS_META[bucket.status].color }}
                          />
                        </Tooltip>
                      ))}
                    </div>
                    <div className={styles.axis}>
                      {axisLabels.map((label) => (
                        <span key={label}>{label}</span>
                      ))}
                    </div>
                  </div>
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
          </>
        ) : (
          !loading && <Empty description="暂无设备健康档案" />
        )}
      </Spin>
    </PageContainer>
  );
};

export default DeviceHealthArchivePage;

import { useEffect, useMemo, useState } from 'react';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import {
  Badge,
  Button,
  Col,
  Empty,
  List,
  Progress,
  Row,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { request } from '@umijs/max';
import type { ColumnsType } from 'antd/es/table';
import CalendarHeatmap from './CalendarHeatmap';

const { Statistic } = StatisticCard;
const { Text } = Typography;

type LevelName = '正常' | '关注' | '警告' | '严重' | '离线' | '未检测' | '未配置';

type DashboardSummary = {
  totalDevices: number;
  onlineDevices: number;
  normalDevices: number;
  faultyDevices: number;
  attentionDevices: number;
  warningDevices: number;
  severeDevices: number;
  offlineSensors: number;
  notCheckedDevices: number;
  unconfiguredDevices: number;
  latestReportTs?: number | null;
};

type HealthDistributionItem = {
  level: LevelName;
  count: number;
};

type DiagnosisDistributionItem = {
  metric: string;
  label: string;
  count: number;
  attention: number;
  warning: number;
  severe: number;
};

type PriorityFault = {
  id: string;
  device_id: string;
  device_name: string;
  device_code: string;
  sn: string;
  area: string;
  process: string;
  level: LevelName;
  metric: string;
  metric_label: string;
  conclusion: string;
  report_ts?: number | null;
  diagnosed_at?: string | null;
  duration_ms?: number | null;
  sequence?: number | null;
  last_activity_at?: string | null;
};

type CommunicationSummary = {
  onlineSensors: number;
  offlineSensors: number;
  slowSensors: number;
  avgDurationMs?: number | null;
  maxDurationMs?: number | null;
  latestActivityAt?: string | null;
};

type TrendItem = {
  date: string;
  attention: number;
  warning: number;
  severe: number;
  total: number;
};

type DashboardWorkbenchData = {
  summary: DashboardSummary;
  healthDistribution: HealthDistributionItem[];
  diagnosisDistribution: DiagnosisDistributionItem[];
  priorityFaults: PriorityFault[];
  communication: CommunicationSummary;
  trend: TrendItem[];
};

const emptyData: DashboardWorkbenchData = {
  summary: {
    totalDevices: 0,
    onlineDevices: 0,
    normalDevices: 0,
    faultyDevices: 0,
    attentionDevices: 0,
    warningDevices: 0,
    severeDevices: 0,
    offlineSensors: 0,
    notCheckedDevices: 0,
    unconfiguredDevices: 0,
  },
  healthDistribution: [],
  diagnosisDistribution: [],
  priorityFaults: [],
  communication: {
    onlineSensors: 0,
    offlineSensors: 0,
    slowSensors: 0,
  },
  trend: [],
};

const levelColor: Record<LevelName, string> = {
  正常: '#52c41a',
  关注: '#faad14',
  警告: '#fa8c16',
  严重: '#f5222d',
  离线: '#8c8c8c',
  未检测: '#1677ff',
  未配置: '#bfbfbf',
};

const levelStatus: Record<LevelName, 'success' | 'warning' | 'error' | 'default' | 'processing'> = {
  正常: 'success',
  关注: 'warning',
  警告: 'warning',
  严重: 'error',
  离线: 'default',
  未检测: 'processing',
  未配置: 'default',
};

const formatTime = (value?: string | number | null) => {
  if (!value) return '-';
  const date = typeof value === 'number' ? new Date(value) : new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString();
};

const formatDuration = (value?: number | null) => {
  if (value === undefined || value === null) return '-';
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
};

const percentOf = (value: number, total: number) => {
  if (!total) return 0;
  return Math.round((value / total) * 100);
};

const DashboardOverview = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<DashboardWorkbenchData>(emptyData);
  const [calendarData, setCalendarData] = useState<any>(null);
  const [calendarLoading, setCalendarLoading] = useState(false);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const res = await request<DashboardWorkbenchData>('/api/v1/dashboard/workbench');
      setData(res || emptyData);
    } catch (error) {
      message.error('获取仪表盘数据失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchCalendarData = async () => {
    setCalendarLoading(true);
    try {
      const res = await request<any>('/api/v1/dashboard/calendar');
      setCalendarData(res);
    } catch (error) {
      message.error('获取年历数据失败');
    } finally {
      setCalendarLoading(false);
    }
  };

  const refreshAll = () => {
    fetchDashboardData();
    fetchCalendarData();
  };

  useEffect(() => {
    refreshAll();
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    const scheduleNextFetch = () => {
      const jitter = Math.floor(Math.random() * 60000);
      timer = setTimeout(() => {
        if (!document.hidden) {
          refreshAll();
        }
        scheduleNextFetch();
      }, 600000 + jitter);
    };

    scheduleNextFetch();
    return () => clearTimeout(timer);
  }, []);

  const totalDevices = data.summary.totalDevices;
  const activeFaultCount = data.summary.warningDevices + data.summary.severeDevices;
  const healthRows = useMemo(
    () => data.healthDistribution.filter(item => item.count > 0 || ['正常', '关注', '警告', '严重'].includes(item.level)),
    [data.healthDistribution],
  );

  const faultColumns: ColumnsType<PriorityFault> = [
    {
      title: '级别',
      dataIndex: 'level',
      width: 86,
      render: level => <Tag color={levelColor[level as LevelName]}>{level}</Tag>,
    },
    {
      title: '设备',
      dataIndex: 'device_name',
      width: 180,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.device_name}</Text>
          <Text type="secondary">{record.device_code}</Text>
        </Space>
      ),
    },
    {
      title: '测点',
      dataIndex: 'sn',
      width: 150,
    },
    {
      title: '诊断项',
      dataIndex: 'metric_label',
      width: 120,
    },
    {
      title: '结论',
      dataIndex: 'conclusion',
      render: value => <Text>{value}</Text>,
    },
    {
      title: '位置',
      dataIndex: 'area',
      width: 120,
    },
    {
      title: '采集耗时',
      dataIndex: 'duration_ms',
      width: 110,
      render: formatDuration,
    },
    {
      title: '最近活动',
      dataIndex: 'last_activity_at',
      width: 180,
      render: formatTime,
    },
  ];

  return (
    <PageContainer
      title="设备运行总览"
      subTitle={`最近上报：${formatTime(data.summary.latestReportTs)}`}
      extra={
        <Button icon={<ReloadOutlined />} onClick={refreshAll} loading={loading || calendarLoading}>
          刷新
        </Button>
      }
    >
      <StatisticCard.Group direction="row" gutter={16}>
        <StatisticCard loading={loading} statistic={{ title: '设备总数', value: totalDevices, suffix: '台' }} />
        <StatisticCard
          loading={loading}
          statistic={{ title: '正常运行', value: data.summary.normalDevices, suffix: '台', status: 'success' }}
        />
        <StatisticCard
          loading={loading}
          statistic={{ title: '故障设备', value: data.summary.faultyDevices, suffix: '台', status: 'error' }}
        />
        <StatisticCard
          loading={loading}
          statistic={{ title: '严重/警告', value: activeFaultCount, suffix: '台', status: 'warning' }}
        />
        <StatisticCard
          loading={loading}
          statistic={{ title: '未覆盖', value: data.summary.unconfiguredDevices, suffix: '台' }}
        />
      </StatisticCard.Group>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={15}>
          <ProCard title="设备状态" bordered headerBordered loading={loading}>
            {healthRows.length ? (
              <Space direction="vertical" size={14} style={{ width: '100%' }}>
                {healthRows.map(item => (
                  <div key={item.level}>
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Space>
                        <Badge status={levelStatus[item.level]} />
                        <Text>{item.level}</Text>
                      </Space>
                      <Text strong>{item.count} 台</Text>
                    </Space>
                    <Progress
                      percent={percentOf(item.count, totalDevices)}
                      showInfo={false}
                      strokeColor={levelColor[item.level]}
                    />
                  </div>
                ))}
              </Space>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </ProCard>
        </Col>

        <Col xs={24} xl={9}>
          <ProCard title="通讯活跃" bordered headerBordered loading={loading}>
            <StatisticCard.Group direction="row">
              <Statistic title="在线测点" value={data.communication.onlineSensors} suffix="个" />
              <Statistic title="离线测点" value={data.communication.offlineSensors} suffix="个" status="warning" />
            </StatisticCard.Group>
            <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 16 }}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text type="secondary">平均采集耗时</Text>
                <Text strong>{formatDuration(data.communication.avgDurationMs)}</Text>
              </Space>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text type="secondary">最长采集耗时</Text>
                <Text strong>{formatDuration(data.communication.maxDurationMs)}</Text>
              </Space>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text type="secondary">最近活动</Text>
                <Text strong>{formatTime(data.communication.latestActivityAt)}</Text>
              </Space>
            </Space>
          </ProCard>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={14}>
          <ProCard title="故障设备优先级" bordered headerBordered loading={loading}>
            <Table<PriorityFault>
              rowKey={record => `${record.id}-${record.device_id}-${record.sn}`}
              columns={faultColumns}
              dataSource={data.priorityFaults}
              pagination={{ pageSize: 8 }}
              size="middle"
            />
          </ProCard>
        </Col>

        <Col xs={24} xl={10}>
          <ProCard title="诊断项分布" bordered headerBordered loading={loading}>
            <List
              dataSource={data.diagnosisDistribution}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
              renderItem={item => (
                <List.Item>
                  <div style={{ width: '100%' }}>
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Text>{item.label}</Text>
                      <Text strong>{item.count} 项</Text>
                    </Space>
                    <Progress
                      percent={percentOf(item.count, Math.max(data.summary.faultyDevices, 1))}
                      showInfo={false}
                      strokeColor={item.severe ? '#f5222d' : item.warning ? '#fa8c16' : '#faad14'}
                    />
                    <Space size={12}>
                      <Text type="secondary">关注 {item.attention}</Text>
                      <Text type="secondary">警告 {item.warning}</Text>
                      <Text type="secondary">严重 {item.severe}</Text>
                    </Space>
                  </div>
                </List.Item>
              )}
            />
          </ProCard>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={10}>
          <ProCard title="最近 7 天趋势" bordered headerBordered loading={loading}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              {data.trend.map(item => (
                <Space key={item.date} style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Text type="secondary">{item.date.slice(5)}</Text>
                  <Progress
                    percent={percentOf(item.total, Math.max(...data.trend.map(row => row.total), 1))}
                    showInfo={false}
                    strokeColor={item.severe ? '#f5222d' : item.warning ? '#fa8c16' : '#faad14'}
                    style={{ flex: 1 }}
                  />
                  <Text strong style={{ width: 40, textAlign: 'right' }}>
                    {item.total}
                  </Text>
                </Space>
              ))}
            </Space>
          </ProCard>
        </Col>

        <Col xs={24} xl={14}>
          <ProCard title="故障年历" bordered headerBordered loading={calendarLoading}>
            <CalendarHeatmap data={calendarData} loading={calendarLoading} />
          </ProCard>
        </Col>
      </Row>
    </PageContainer>
  );
};

export default DashboardOverview;

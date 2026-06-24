import { useEffect, useState } from 'react';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { Button, Col, Empty, Row, Space, Table, Tag, Tooltip, Typography, message } from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  MinusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { request } from '@umijs/max';
import type { ColumnsType } from 'antd/es/table';

const { Statistic } = StatisticCard;
const { Text } = Typography;

// ── Types ──────────────────────────────────────────────

type HealthSummary = {
  total: number;
  normal: number;
  attention: number;
  warning: number;
  severe: number;
  offline: number;
  unconfigured: number;
};

type DistributionItem = {
  name: string;
  attention: number;
  warning: number;
  severe: number;
};

type FaultDevice = {
  deviceId: string;
  deviceName: string;
  deviceCode: string;
  category: string;
  area: string;
  level: string;
  levelScore: number;
  metrics: string[];
  durationHours: number | null;
  trending: 'worsening' | 'stable' | 'improving';
};

type HealthDashboardData = {
  healthSummary: HealthSummary;
  problemDistribution: {
    byCategory: DistributionItem[];
    byArea: DistributionItem[];
    byMetric?: DistributionItem[];
  };
  faultDevices: FaultDevice[];
};

// ── Constants ──────────────────────────────────────────

const levelColor: Record<string, string> = {
  正常: '#52c41a',
  关注: '#faad14',
  警告: '#fa8c16',
  严重: '#f5222d',
};

const trendIcon: Record<string, React.ReactNode> = {
  worsening: <ArrowUpOutlined style={{ color: '#f5222d', fontSize: 13 }} />,
  stable: <MinusOutlined style={{ color: '#8c8c8c', fontSize: 13 }} />,
  improving: <ArrowDownOutlined style={{ color: '#52c41a', fontSize: 13 }} />,
};

const trendLabel: Record<string, string> = {
  worsening: '恶化中',
  stable: '持平',
  improving: '好转中',
};

// ── Helpers ────────────────────────────────────────────

const formatDuration = (hours: number | null) => {
  if (hours === null || hours === undefined) return '-';
  if (hours < 1) return `${Math.round(hours * 60)}分钟`;
  if (hours < 24) return `${Math.round(hours)}小时`;
  const days = Math.floor(hours / 24);
  const remainHours = Math.round(hours % 24);
  if (remainHours === 0) return `${days}天`;
  return `${days}天${remainHours}小时`;
};

// ── HealthBar component ────────────────────────────────

const HealthBar = ({ summary }: { summary: HealthSummary }) => {
  const monitored = summary.total - summary.unconfigured;
  const online = monitored - summary.offline;

  const segments = [
    { key: 'normal', label: '正常', count: summary.normal, color: '#52c41a' },
    { key: 'attention', label: '关注', count: summary.attention, color: '#faad14' },
    { key: 'warning', label: '警告', count: summary.warning, color: '#fa8c16' },
    { key: 'severe', label: '严重', count: summary.severe, color: '#f5222d' },
    { key: 'offline', label: '数据中断', count: summary.offline, color: '#8c8c8c' },
    { key: 'unconfigured', label: '未覆盖', count: summary.unconfigured, color: '#d9d9d9' },
  ];

  return (
    <div>
      {/* Proportion bar */}
      <div
        style={{
          display: 'flex',
          height: 22,
          borderRadius: 4,
          overflow: 'hidden',
          marginBottom: 12,
          background: '#f0f0f0',
        }}
      >
        {segments
          .filter(s => s.count > 0)
          .map(s => (
            <Tooltip key={s.key} title={`${s.label}: ${s.count}台`}>
              <div
                style={{
                  width: `${(s.count / summary.total) * 100}%`,
                  background: s.color,
                  minWidth: s.count > 0 ? 3 : 0,
                  transition: 'width 0.3s ease',
                }}
              />
            </Tooltip>
          ))}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
        {segments.map(s => (
          <Space key={s.key} size={4}>
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                background: s.color,
              }}
            />
            <Text type="secondary" style={{ fontSize: 13 }}>
              {s.label}
            </Text>
            <Text strong style={{ fontSize: 13 }}>
              {s.count}
            </Text>
          </Space>
        ))}
      </div>
    </div>
  );
};

// ── DistributionTags component ────────────────────────

const DistributionTags = ({
  title,
  data,
}: {
  title: string;
  data: DistributionItem[];
}) => {
  if (!data.length) {
    return (
      <ProCard title={title} bordered headerBordered>
        <div style={{ textAlign: 'center', padding: '24px 0', color: '#52c41a', fontWeight: 500 }}>
          ✓ 全部正常
        </div>
      </ProCard>
    );
  }

  return (
    <ProCard title={title} bordered headerBordered>
      <Space size={[12, 12]} wrap style={{ width: '100%' }}>
        {data.map(item => {
          // Determine the highest severity level for this group to set the background color
          let bgColor = '#fafafa';
          let borderColor = '#d9d9d9';
          let textColor = '#rgba(0, 0, 0, 0.88)';

          if (item.severe > 0) {
            bgColor = '#fff1f0';
            borderColor = '#ffa39e';
            textColor = '#cf1322';
          } else if (item.warning > 0) {
            bgColor = '#fff7e6';
            borderColor = '#ffd591';
            textColor = '#d46b08';
          } else if (item.attention > 0) {
            bgColor = '#feffe6';
            borderColor = '#fffb8f';
            textColor = '#d4b106';
          }

          return (
            <div
              key={item.name}
              style={{
                display: 'flex',
                alignItems: 'stretch',
                border: `1px solid ${borderColor}`,
                borderRadius: 6,
                overflow: 'hidden',
                background: bgColor,
              }}
            >
              <div style={{ padding: '4px 12px', fontWeight: 500, color: textColor, background: 'rgba(255,255,255,0.3)' }}>
                {item.name}
              </div>
              <div style={{ display: 'flex', gap: 1, background: borderColor }}>
                {item.severe > 0 && (
                  <div style={{ padding: '4px 8px', background: '#fff', color: '#f5222d', fontWeight: 600 }}>
                    <Tooltip title="严重">{item.severe}</Tooltip>
                  </div>
                )}
                {item.warning > 0 && (
                  <div style={{ padding: '4px 8px', background: '#fff', color: '#fa8c16', fontWeight: 600 }}>
                    <Tooltip title="警告">{item.warning}</Tooltip>
                  </div>
                )}
                {item.attention > 0 && (
                  <div style={{ padding: '4px 8px', background: '#fff', color: '#faad14', fontWeight: 600 }}>
                    <Tooltip title="关注">{item.attention}</Tooltip>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </Space>
    </ProCard>
  );
};

import CalendarHeatmap from '../Overview/CalendarHeatmap';

const emptyData: HealthDashboardData = {
  healthSummary: {
    total: 0,
    normal: 0,
    attention: 0,
    warning: 0,
    severe: 0,
    offline: 0,
    unconfigured: 0,
  },
  problemDistribution: { byCategory: [], byArea: [], byMetric: [] },
  faultDevices: [],
};

const HealthDashboard = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<HealthDashboardData>(emptyData);
  const [calendarData, setCalendarData] = useState<any>();
  const [calendarLoading, setCalendarLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await request<HealthDashboardData>('/api/v1/dashboard/health');
      setData(res || emptyData);
    } catch {
      message.error('获取健康总览数据失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchCalendarData = async () => {
    setCalendarLoading(true);
    try {
      const res = await request<any>('/api/v1/dashboard/calendar');
      if (res) {
        setCalendarData(res);
      }
    } catch (e) {
      // ignore
    } finally {
      setCalendarLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    fetchCalendarData();
  }, []);

  // Auto-refresh every 10 minutes
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      const jitter = Math.floor(Math.random() * 60000);
      timer = setTimeout(() => {
        if (!document.hidden) fetchData();
        schedule();
      }, 600000 + jitter);
    };
    schedule();
    return () => clearTimeout(timer);
  }, []);

  const { healthSummary: summary } = data;
  const faultCount = summary.attention + summary.warning + summary.severe;

  const faultColumns: ColumnsType<FaultDevice> = [
    {
      title: '等级',
      dataIndex: 'level',
      width: 76,
      render: level => <Tag color={levelColor[level]}>{level}</Tag>,
    },
    {
      title: '趋势',
      dataIndex: 'trending',
      width: 80,
      render: (trending: string) => (
        <Tooltip title={trendLabel[trending]}>
          <Space size={4}>
            {trendIcon[trending]}
            <span style={{ fontSize: 12 }}>{trendLabel[trending]}</span>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: '设备',
      dataIndex: 'deviceName',
      width: 180,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.deviceName}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.deviceCode}</Text>
        </Space>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 120,
    },
    {
      title: '车间',
      dataIndex: 'area',
      width: 120,
    },
    {
      title: '异常指标',
      dataIndex: 'metrics',
      render: (metrics: string[]) =>
        metrics.length > 0
          ? metrics.map(m => (
            <Tag key={m} style={{ marginBottom: 2 }}>
              {m}
            </Tag>
          ))
          : <Text type="secondary">-</Text>,
    },
    {
      title: '持续时间',
      dataIndex: 'durationHours',
      width: 120,
      render: (hours: number | null) => {
        const text = formatDuration(hours);
        if (hours !== null && hours >= 168) {
          return <Text type="danger" strong>{text}</Text>;
        }
        if (hours !== null && hours >= 24) {
          return <Text style={{ color: '#fa8c16' }}>{text}</Text>;
        }
        return <Text>{text}</Text>;
      },
    },
  ];

  return (
    <PageContainer
      title="健康总览"
      extra={
        <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
          刷新
        </Button>
      }
    >
      {/* ── Section 1: Health summary ── */}
      <ProCard loading={loading} bordered headerBordered>
        <StatisticCard.Group direction="row" gutter={16}>
          <StatisticCard
            statistic={{ title: '设备总数', value: summary.total, suffix: '台' }}
          />
          <StatisticCard
            statistic={{
              title: '异常设备',
              value: faultCount,
              suffix: '台',
              status: faultCount > 0 ? 'error' : 'success',
            }}
          />
          <StatisticCard
            statistic={{
              title: '正常运行',
              value: summary.normal,
              suffix: '台',
              status: 'success',
            }}
          />
          <StatisticCard
            statistic={{
              title: '数据中断',
              value: summary.offline,
              suffix: '台',
              status: summary.offline > 0 ? 'warning' : 'default',
            }}
          />
        </StatisticCard.Group>
        <div style={{ marginTop: 16 }}>
          <HealthBar summary={summary} />
        </div>
      </ProCard>



      {/* ── Section 2: Problem distribution ── */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="按设备分类"
            data={data.problemDistribution.byCategory}
          />
        </Col>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="按车间/区域"
            data={data.problemDistribution.byArea}
          />
        </Col>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="按诊断项分布"
            data={data.problemDistribution.byMetric || []}
          />
        </Col>
      </Row>



      {/* ── Section 3: Fault devices ── */}
      <ProCard
        title={`异常设备 (${data.faultDevices.length})`}
        bordered
        headerBordered
        loading={loading}
        style={{ marginTop: 16 }}
      >
        {data.faultDevices.length > 0 ? (
          <Table<FaultDevice>
            rowKey="deviceId"
            columns={faultColumns}
            dataSource={data.faultDevices}
            pagination={{ pageSize: 10 }}
            size="middle"
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="所有设备运行正常"
          />
        )}
      </ProCard>

      {/* ── Section 3: Calendar Heatmap ── */}
      <ProCard title="全年故障热力图" bordered headerBordered loading={calendarLoading} style={{ marginTop: 16 }}>
        <CalendarHeatmap data={calendarData} loading={calendarLoading} />
      </ProCard>
    </PageContainer>
  );
};

export default HealthDashboard;

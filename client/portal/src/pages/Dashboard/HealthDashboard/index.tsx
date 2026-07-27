import { useEffect, useState } from 'react';
import { history } from '@umijs/max';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { Button, Col, Empty, Row, Space, Table, Tag, Tooltip, Typography, message } from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  MinusOutlined,
  ReloadOutlined,
  CheckCircleFilled,
  InfoCircleFilled,
  InfoCircleOutlined,
  ExclamationCircleFilled,
  WarningFilled,
  FireFilled,
  DashboardOutlined,
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
  abnormal: number;
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
  异常: '#fa8c16',
  警告: '#f5222d',
  严重: '#a8071a',
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

import CalendarHeatmap from '../components/CalendarHeatmap';

const emptyData: HealthDashboardData = {
  healthSummary: {
    total: 0,
    normal: 0,
    attention: 0,
    abnormal: 0,
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
  const faultCount = summary.attention + summary.abnormal + summary.warning + summary.severe;

  const faultColumns: ColumnsType<FaultDevice> = [
    {
      title: '等级',
      dataIndex: 'level',
      width: 76,
      render: level => <Tag color={levelColor[level]}>{level === '严重' ? '危险' : level}</Tag>,
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

  const healthMetrics = [
    { 
      key: 'severe', title: '危险', value: summary.severe, color: '#ffffff', bg: 'linear-gradient(135deg, #cb2d3e 0%, #ef473a 100%)', icon: <FireFilled />,
      desc: '诊断算法评估：指标动态负荷占比突破 70% 甚至触及绝对红线，或发生秒级瞬态突变，随时可能引发停机事故。'
    },
    { 
      key: 'warning', title: '警告', value: summary.warning, color: '#ffffff', bg: 'linear-gradient(135deg, #ec008c 0%, #fc6767 100%)', icon: <WarningFilled />,
      desc: '诊断算法评估：指标动态负荷占比达 40%~70%，趋势劣化或横向偏离被高倍率放大，处于带病运行状态。'
    },
    { 
      key: 'abnormal', title: '异常', value: summary.abnormal, color: '#ffffff', bg: 'linear-gradient(135deg, #ff7e5f 0%, #feb47b 100%)', icon: <ExclamationCircleFilled />,
      desc: '诊断算法评估：指标动态负荷占比达 20%~40%，或设备出现 24/72 小时历史趋势恶化、同规格对等组横向偏离。'
    },
    { 
      key: 'attention', title: '关注', value: summary.attention, color: '#ffffff', bg: 'linear-gradient(135deg, #f2c94c 0%, #f2994a 100%)', icon: <InfoCircleFilled />,
      desc: '诊断算法评估：指标动态负荷占比达 10%~20%，存在轻微波动，作为后续趋势劣化的敏感度基点。'
    },
    { 
      key: 'normal', title: '正常', value: summary.normal, color: '#ffffff', bg: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)', icon: <CheckCircleFilled />,
      desc: '诊断算法评估：指标动态负荷占比 < 10%，且未触发任何长短期劣化趋势或横向同组偏离，运行平稳。'
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
      <style>{`
        .health-card {
          transition: all 0.3s ease;
          border: 1px solid rgba(255, 255, 255, 0.4);
        }
        .health-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 10px 20px rgba(0,0,0,0.08) !important;
        }
      `}</style>
      {/* ── Section 1: Health summary ── */}
      <ProCard
        title={
          <Space>
            <DashboardOutlined style={{ color: '#1890ff', fontSize: 18 }} />
            <span style={{ fontSize: 16, fontWeight: 600, color: '#262626' }}>健康分布</span>
          </Space>
        }
        loading={loading}
        bordered
        headerBordered
        style={{ background: '#fafafa', marginBottom: 24 }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
          {healthMetrics.map(item => {
            const isZero = item.value === undefined || item.value === null || item.value === 0;
            const cardBg = isZero ? '#f5f5f5' : item.bg;
            const textColor = isZero ? '#bfbfbf' : '#ffffff';
            const titleColor = isZero ? '#8c8c8c' : '#ffffff';
            const iconColor = isZero ? '#d9d9d9' : '#ffffff';
            const watermarkColor = isZero ? '#000000' : '#ffffff';
            const watermarkOpacity = isZero ? 0.03 : 0.15;
            const shadow = isZero ? 'none' : '0 1px 2px rgba(0,0,0,0.1)';
            const border = isZero ? '1px dashed #e8e8e8' : '1px solid rgba(255, 255, 255, 0.4)';

            return (
              <div
                key={item.key}
                className="health-card"
                onClick={() => {
                  if (!isZero && item.key !== 'normal') {
                    history.push(`/dashboard/monitoring?level=${item.key}`);
                  }
                }}
                style={{
                  background: cardBg,
                  borderRadius: 12,
                  padding: '20px 24px',
                  position: 'relative',
                  overflow: 'hidden',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
                  cursor: (!isZero && item.key !== 'normal') ? 'pointer' : 'default',
                  height: '100%',
                  border: border,
                }}
              >
                <div style={{ position: 'relative', zIndex: 1 }}>
                  <Space size={8} style={{ color: titleColor, fontSize: 16, fontWeight: 'bold', marginBottom: 12, textShadow: shadow }}>
                    <span style={{ color: iconColor }}>{item.icon}</span>
                    <span>
                      {item.title}
                      <Tooltip title={item.desc} overlayInnerStyle={{ width: 200 }}>
                        <InfoCircleOutlined style={{ fontSize: 14, color: isZero ? '#d9d9d9' : 'rgba(255,255,255,0.7)', marginLeft: 6, cursor: 'help' }} />
                      </Tooltip>
                    </span>
                  </Space>
                  <div style={{ fontSize: 36, fontWeight: '900', color: textColor, lineHeight: 1, textShadow: shadow }}>
                    {isZero ? 0 : item.value} <span style={{ fontSize: 14, fontWeight: 'normal', color: isZero ? '#d9d9d9' : 'rgba(255,255,255,0.85)' }}>台</span>
                  </div>
                </div>
                {/* Background Icon Watermark */}
                <div
                  style={{
                    position: 'absolute',
                    right: -15,
                    bottom: -20,
                    fontSize: 100,
                    color: watermarkColor,
                    opacity: watermarkOpacity,
                    zIndex: 0,
                    transform: 'rotate(-15deg)',
                  }}
                >
                  {item.icon}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
          <Space size="large" split={<span style={{ color: '#e8e8e8' }}>|</span>}>
            <Space size={4}>
              <Text type="secondary">设备总数:</Text>
              <Text strong style={{ fontSize: 16, color: '#595959' }}>{summary.total}</Text>
              <Text type="secondary">台</Text>
            </Space>
            <Space size={4}>
              <Text type="secondary">已接入监测:</Text>
              <Text strong style={{ fontSize: 16, color: '#1890ff' }}>{summary.total - summary.unconfigured}</Text>
              <Text type="secondary">台</Text>
            </Space>
            <Space size={4}>
              <Text type="secondary">待接入监测:</Text>
              <Text strong style={{ fontSize: 16, color: '#bfbfbf' }}>{summary.unconfigured}</Text>
              <Text type="secondary">台</Text>
            </Space>
          </Space>
        </div>
      </ProCard>



      {/* ── Section 2: Problem distribution ── */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="设备分类视图"
            data={data.problemDistribution.byCategory}
          />
        </Col>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="车间区域视图"
            data={data.problemDistribution.byArea}
          />
        </Col>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="诊断项视图"
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

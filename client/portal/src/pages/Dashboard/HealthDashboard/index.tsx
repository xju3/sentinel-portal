import { useEffect, useRef, useState } from 'react';
import { history } from '@umijs/max';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import {
  Button,
  Col,
  ConfigProvider,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Progress,
  Row,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
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
  ClockCircleOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
} from '@ant-design/icons';
import { request } from '@umijs/max';
import type { ColumnsType } from 'antd/es/table';
import CalendarHeatmap from '../components/CalendarHeatmap';

const { Text } = Typography;

// ── Types ──────────────────────────────────────────────

type HealthSummary = {
  total: number;
  normal: number;
  attention: number;
  abnormal: number;
  warning: number;
  severe: number;
  monitored: number;
  diagnosed: number;
  online: number;
  uninspected: number;
  offline: number;
  unconfigured: number;
};

type DistributionItem = {
  name: string;
  attention: number;
  abnormal: number;
  warning: number;
  severe: number;
};

type DiagnosisEvidence = {
  ratio?: number | null;
  current?: number | null;
  healthyMedian?: number | null;
  peerMedian?: number | null;
  stSlope?: number | null;
  mtSlope?: number | null;
  mutation?: number | null;
  confirmationStatus?: string | null;
};

type DiagnosisDetail = {
  metricId: number;
  metricLabel: string;
  level: string;
  levelScore: number;
  description?: string | null;
  diagnosedAt?: string | null;
  occurrenceCount: number;
  firstDetectedAt?: string | null;
  lastDetectedAt?: string | null;
  evidence: DiagnosisEvidence;
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
  issueState: 'new' | 'repeated' | 'worsening' | 'improving';
  occurrenceCount: number;
  firstDetectedAt?: string | null;
  lastDetectedAt?: string | null;
  diagnosisDetails: DiagnosisDetail[];
};

type HealthDashboardData = {
  healthSummary: HealthSummary;
  issueSummary: {
    new: number;
    repeated: number;
    worsening: number;
    improving: number;
    pendingConfirmation: number;
  };
  problemDistribution: {
    byCategory: DistributionItem[];
    byArea: DistributionItem[];
    byMetric?: DistributionItem[];
  };
  faultDevices: FaultDevice[];
  snapshot?: {
    generatedAt: string;
    stale: boolean;
    refreshing: boolean;
    source: string;
  };
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

const issueStateLabel: Record<FaultDevice['issueState'], string> = {
  new: '首次检出',
  repeated: '重复检出',
  worsening: '趋势恶化',
  improving: '趋势好转',
};

const issueStateColor: Record<FaultDevice['issueState'], string> = {
  new: 'blue',
  repeated: 'gold',
  worsening: 'red',
  improving: 'green',
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
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
          } else if (item.warning > 0 || item.abnormal > 0) {
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
                {item.abnormal > 0 && (
                  <div style={{ padding: '4px 8px', background: '#fff', color: '#fa541c', fontWeight: 600 }}>
                    <Tooltip title="异常">{item.abnormal}</Tooltip>
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

const DiagnosisPreviewDrawer = ({
  device,
  open,
  onClose,
  getContainer,
}: {
  device: FaultDevice | null;
  open: boolean;
  onClose: () => void;
  getContainer: () => HTMLElement;
}) => {
  if (!device) return null;

  return (
    <Drawer
      title={
        <Space>
          <span>{device.deviceName}</span>
          <Tag color={levelColor[device.level]}>{device.level === '严重' ? '危险' : device.level}</Tag>
        </Space>
      }
      width={560}
      open={open}
      onClose={onClose}
      getContainer={getContainer}
      destroyOnClose
      extra={
        <Button
          type="link"
          onClick={() => history.push(`/dashboard/monitoring?level=${device.level === '严重' ? 'severe' : device.level === '警告' ? 'warning' : device.level === '异常' ? 'abnormal' : 'attention'}`)}
        >
          查看全部同等级设备
        </Button>
      }
    >
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="设备编号">{device.deviceCode || '-'}</Descriptions.Item>
        <Descriptions.Item label="设备类型">{device.category}</Descriptions.Item>
        <Descriptions.Item label="所属设备分组">{device.area}</Descriptions.Item>
        <Descriptions.Item label="问题状态">
          <Tag color={issueStateColor[device.issueState]}>
            {issueStateLabel[device.issueState]}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="首次检出">{formatDateTime(device.firstDetectedAt)}</Descriptions.Item>
        <Descriptions.Item label="最近检出">{formatDateTime(device.lastDetectedAt)}</Descriptions.Item>
        <Descriptions.Item label="累计检出">
          {device.occurrenceCount > 0 ? `${device.occurrenceCount} 次` : '待最终确认'}
        </Descriptions.Item>
        <Descriptions.Item label="等级趋势">
          <Space size={4}>
            {trendIcon[device.trending]}
            {trendLabel[device.trending]}
          </Space>
        </Descriptions.Item>
      </Descriptions>

      <Divider orientation="left">当前诊断依据</Divider>

      {device.diagnosisDetails.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="诊断明细正在确认中" />
      ) : (
        device.diagnosisDetails.map(detail => {
          const ratio = detail.evidence.ratio;
          const isTemperature = detail.metricLabel.includes('温度');
          return (
            <div
              key={`${detail.metricId}-${detail.diagnosedAt || ''}`}
              style={{
                border: '1px solid #f0f0f0',
                borderLeft: `3px solid ${levelColor[detail.level] || '#8c8c8c'}`,
                borderRadius: 8,
                padding: 16,
                marginBottom: 12,
                background: '#fafafa',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <Space>
                  <Text strong>{detail.metricLabel}</Text>
                  <Tag color={levelColor[detail.level]}>{detail.level === '严重' ? '危险' : detail.level}</Tag>
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <ClockCircleOutlined /> {formatDateTime(detail.diagnosedAt)}
                </Text>
              </div>

              {detail.description && (
                <div style={{ color: '#595959', lineHeight: 1.7, marginBottom: 10 }}>
                  {detail.description}
                </div>
              )}

              {ratio != null && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span>动态负荷占比</span>
                    <strong>{(ratio * 100).toFixed(1)}%</strong>
                  </div>
                  <Progress
                    percent={Math.min(100, Math.round(ratio * 100))}
                    showInfo={false}
                    size="small"
                    strokeColor={levelColor[detail.level]}
                  />
                </div>
              )}

              <Descriptions size="small" column={2}>
                {detail.evidence.current != null && (
                  <Descriptions.Item label="当前值">
                    {Number(detail.evidence.current).toFixed(3)} {isTemperature ? '°C' : 'mm/s'}
                  </Descriptions.Item>
                )}
                {detail.evidence.healthyMedian != null && (
                  <Descriptions.Item label="健康基准">
                    {Number(detail.evidence.healthyMedian).toFixed(3)} {isTemperature ? '°C' : 'mm/s'}
                  </Descriptions.Item>
                )}
                <Descriptions.Item label="历史检出">
                  {detail.occurrenceCount > 0 ? `${detail.occurrenceCount} 次` : '待最终确认'}
                </Descriptions.Item>
                <Descriptions.Item label="确认状态">
                  {detail.evidence.confirmationStatus && detail.evidence.confirmationStatus !== 'confirmed'
                    ? <Tag color="processing">复采确认中</Tag>
                    : <Tag color="success">当前结论</Tag>}
                </Descriptions.Item>
              </Descriptions>
            </div>
          );
        })
      )}
    </Drawer>
  );
};

const emptyData: HealthDashboardData = {
  healthSummary: {
    total: 0,
    normal: 0,
    attention: 0,
    abnormal: 0,
    warning: 0,
    severe: 0,
    monitored: 0,
    diagnosed: 0,
    online: 0,
    uninspected: 0,
    offline: 0,
    unconfigured: 0,
  },
  issueSummary: {
    new: 0,
    repeated: 0,
    worsening: 0,
    improving: 0,
    pendingConfirmation: 0,
  },
  problemDistribution: { byCategory: [], byArea: [], byMetric: [] },
  faultDevices: [],
};

const HealthDashboard = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<HealthDashboardData>(emptyData);
  const [calendarData, setCalendarData] = useState<any>();
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [previewDevice, setPreviewDevice] = useState<FaultDevice | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const fullscreenRef = useRef<HTMLDivElement>(null);
  const refreshRetryRef = useRef(0);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const fetchData = async ({
    force = false,
    silent = false,
  }: { force?: boolean; silent?: boolean } = {}) => {
    if (!silent) setLoading(true);
    try {
      const res = await request<HealthDashboardData>(
        `/api/v1/dashboard/health${force ? '?refresh=true' : ''}`,
      );
      setData(res || emptyData);
      if (res?.snapshot?.refreshing && refreshRetryRef.current < 2) {
        refreshRetryRef.current += 1;
        clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = setTimeout(() => {
          fetchData({ silent: true });
        }, 1500);
      } else if (!res?.snapshot?.stale) {
        refreshRetryRef.current = 0;
      }
    } catch {
      if (!silent) message.error('获取健康总览数据失败');
    } finally {
      if (!silent) setLoading(false);
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
    return () => clearTimeout(refreshTimerRef.current);
  }, []);

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

  // Auto-refresh every 10 minutes
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      const jitter = Math.floor(Math.random() * 60000);
      timer = setTimeout(() => {
        if (!document.hidden) fetchData({ silent: true });
        schedule();
      }, 600000 + jitter);
    };
    schedule();
    return () => clearTimeout(timer);
  }, []);

  const { healthSummary: summary } = data;
  const faultColumns: ColumnsType<FaultDevice> = [
    {
      title: '等级',
      dataIndex: 'level',
      width: 76,
      render: level => <Tag color={levelColor[level]}>{level === '严重' ? '危险' : level}</Tag>,
    },
    {
      title: '问题状态',
      dataIndex: 'issueState',
      width: 100,
      render: (issueState: FaultDevice['issueState'], record) => (
        <Space direction="vertical" size={2}>
          <Tag color={issueStateColor[issueState]}>{issueStateLabel[issueState]}</Tag>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {trendIcon[record.trending]} {trendLabel[record.trending]}
          </Text>
        </Space>
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
      title: '设备类型',
      dataIndex: 'category',
      width: 120,
    },
    {
      title: '设备分组',
      dataIndex: 'area',
      width: 120,
    },
    {
      title: '当前问题',
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
      title: '检出情况',
      dataIndex: 'occurrenceCount',
      width: 150,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>
            {record.occurrenceCount > 0 ? `累计 ${record.occurrenceCount} 次` : '待最终确认'}
          </Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            最近 {formatDateTime(record.lastDetectedAt)}
          </Text>
        </Space>
      ),
    },
  ];

  const healthMetrics = [
    { 
      key: 'severe', title: '危险', value: summary.severe, bg: 'linear-gradient(135deg, #cb2d3e 0%, #ef473a 100%)', icon: <FireFilled />, clickable: true,
      desc: '诊断算法评估：指标动态负荷占比突破 70% 甚至触及绝对红线，或发生秒级瞬态突变，随时可能引发停机事故。'
    },
    { 
      key: 'warning', title: '警告', value: summary.warning, bg: 'linear-gradient(135deg, #ec008c 0%, #fc6767 100%)', icon: <WarningFilled />, clickable: true,
      desc: '诊断算法评估：指标动态负荷占比达 40%~70%，趋势劣化或横向偏离被高倍率放大，处于带病运行状态。'
    },
    { 
      key: 'abnormal', title: '异常', value: summary.abnormal, bg: 'linear-gradient(135deg, #ff7e5f 0%, #feb47b 100%)', icon: <ExclamationCircleFilled />, clickable: true,
      desc: '诊断算法评估：指标动态负荷占比达 20%~40%，或设备出现 24/72 小时历史趋势恶化、同规格对等组横向偏离。'
    },
    { 
      key: 'attention', title: '关注', value: summary.attention, bg: 'linear-gradient(135deg, #f2c94c 0%, #f2994a 100%)', icon: <InfoCircleFilled />, clickable: true,
      desc: '诊断算法评估：指标动态负荷占比达 10%~20%，存在轻微波动，作为后续趋势劣化的敏感度基点。'
    },
    { 
      key: 'normal', title: '正常', value: summary.normal, bg: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)', icon: <CheckCircleFilled />, clickable: false,
      desc: '诊断算法评估：指标动态负荷占比 < 10%，且未触发任何长短期劣化趋势或横向同组偏离，运行平稳。'
    },
    {
      key: 'uninspected', title: '漏检', value: summary.uninspected, bg: 'linear-gradient(135deg, #8c8c8c 0%, #bfbfbf 100%)', icon: <InfoCircleOutlined />, clickable: false,
      desc: '设备已接入监测，但还没有可用的最新诊断结论。该状态不会计入正常设备。'
    },
  ];

  return (
    <ConfigProvider
      getPopupContainer={(trigger) =>
        trigger?.parentElement || fullscreenRef.current || document.body
      }
    >
      <div ref={fullscreenRef} className="health-dashboard-fullscreen">
        <PageContainer
      title="设备健康总览"
      subTitle={
        data.snapshot?.generatedAt
          ? `数据生成于 ${new Date(data.snapshot.generatedAt).toLocaleString('zh-CN')}${data.snapshot.refreshing ? '，正在后台更新' : ''}`
          : '当前设备健康状态与异常定位'
      }
      extra={[
        <Button
          key="fullscreen"
          icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
          onClick={() => void toggleFullscreen()}
        >
          {fullscreen ? '退出全屏' : '全屏'}
        </Button>,
        <Button
          key="refresh"
          icon={<ReloadOutlined />}
          onClick={() => {
            refreshRetryRef.current = 0;
            fetchData({ force: true });
          }}
          loading={loading}
        >
          刷新
        </Button>,
      ]}
    >
      <style>{`
        .health-dashboard-fullscreen {
          min-height: 100%;
        }
        .health-dashboard-fullscreen:fullscreen {
          min-height: 100vh;
          overflow: auto;
          background: #f5f5f5;
        }
        .health-card {
          transition: all 0.3s ease;
          border: 1px solid rgba(255, 255, 255, 0.4);
        }
        .health-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 10px 20px rgba(0,0,0,0.08) !important;
        }
        .health-grid {
          display: grid;
          grid-template-columns: repeat(6, minmax(0, 1fr));
          gap: 16px;
        }
        .issue-summary-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
          gap: 16px;
          width: 100%;
        }
        @media (max-width: 900px) {
          .health-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
        @media (max-width: 600px) {
          .health-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
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
        <div className="health-grid">
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
                  if (!isZero && item.clickable) {
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
                  cursor: (!isZero && item.clickable) ? 'pointer' : 'default',
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
              <Text strong style={{ fontSize: 16, color: '#1890ff' }}>{summary.monitored}</Text>
              <Text type="secondary">台</Text>
            </Space>
            <Space size={4}>
              <Text type="secondary">在线:</Text>
              <Text strong style={{ fontSize: 16, color: '#52c41a' }}>{summary.online}</Text>
              <Text type="secondary">台</Text>
            </Space>
            <Space size={4}>
              <Text type="secondary">离线:</Text>
              <Text strong style={{ fontSize: 16, color: summary.offline ? '#fa8c16' : '#8c8c8c' }}>{summary.offline}</Text>
              <Text type="secondary">台</Text>
            </Space>
            <Space size={4}>
              <Text type="secondary">未接入:</Text>
              <Text strong style={{ fontSize: 16, color: '#bfbfbf' }}>{summary.unconfigured}</Text>
              <Text type="secondary">台</Text>
            </Space>
          </Space>
        </div>
      </ProCard>

      <ProCard
        title="当前异常特征"
        subTitle="基于已落库诊断记录归纳；重复检出不等同于连续异常"
        bordered
        headerBordered
        style={{ marginTop: 16 }}
      >
        <div className="issue-summary-grid">
          {[
            { label: '首次检出', value: data.issueSummary.new, color: '#1677ff' },
            { label: '重复检出', value: data.issueSummary.repeated, color: '#d48806' },
            { label: '趋势恶化', value: data.issueSummary.worsening, color: '#cf1322' },
            { label: '趋势好转', value: data.issueSummary.improving, color: '#389e0d' },
            { label: '复采确认中', value: data.issueSummary.pendingConfirmation, color: '#722ed1' },
          ].map(item => (
            <div
              key={item.label}
              style={{ padding: '12px 16px', borderRadius: 8, background: '#fafafa', border: '1px solid #f0f0f0' }}
            >
              <Text type="secondary">{item.label}</Text>
              <div style={{ marginTop: 4 }}>
                <Text strong style={{ fontSize: 26, color: item.color }}>{item.value}</Text>
                <Text type="secondary" style={{ marginLeft: 4 }}>台</Text>
              </div>
            </div>
          ))}
        </div>
      </ProCard>

      {/* ── Section 2: Problem distribution ── */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="问题设备类型"
            data={data.problemDistribution.byCategory}
          />
        </Col>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="问题设备分组"
            data={data.problemDistribution.byArea}
          />
        </Col>
        <Col xs={24} lg={8}>
          <DistributionTags
            title="问题诊断项"
            data={data.problemDistribution.byMetric || []}
          />
        </Col>
      </Row>



      {/* ── Section 3: Fault devices ── */}
      <ProCard
        title={`当前异常设备 (${data.faultDevices.length})`}
        subTitle="点击设备查看当前诊断依据"
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
            onRow={record => ({
              onClick: () => setPreviewDevice(record),
              style: { cursor: 'pointer' },
            })}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="所有设备运行正常"
          />
        )}
      </ProCard>

      <DiagnosisPreviewDrawer
        device={previewDevice}
        open={previewDevice !== null}
        onClose={() => setPreviewDevice(null)}
        getContainer={() => fullscreenRef.current || document.body}
      />

      {/* ── Section 4: Calendar Heatmap ── */}
      <ProCard
        title="全年异常检出热力图"
        subTitle="表示当天检出异常的设备数量，不等同于当天新发生故障"
        bordered
        headerBordered
        loading={calendarLoading}
        style={{ marginTop: 16 }}
      >
        <CalendarHeatmap data={calendarData} loading={calendarLoading} />
      </ProCard>
        </PageContainer>
      </div>
    </ConfigProvider>
  );
};

export default HealthDashboard;

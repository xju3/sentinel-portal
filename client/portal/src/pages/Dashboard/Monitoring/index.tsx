import { useEffect, useMemo, useState } from 'react';
import { history, useSearchParams } from '@umijs/max';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import {
  Button,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Progress,
  Row,
  Space,
  Spin,
  Tag,
  Tabs,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusOutlined,
  ReloadOutlined,
  FireFilled,
  WarningFilled,
  ExclamationCircleFilled,
  InfoCircleFilled,
  ArrowLeftOutlined,
  ClockCircleOutlined,
  ThunderboltFilled,
  FireOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { request } from '@umijs/max';

const { Text, Title } = Typography;

// ── Types ──────────────────────────────────────────────

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
  metricId: number;    // 0=温度, 1=振动X, 2=振动Y, 3=振动Z
  metricLabel: string;
  level: string;
  levelScore: number;
  description?: string | null;
  diagnosedAt?: string | null;
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
  diagnosisDetails: DiagnosisDetail[];
};

// ── Constants ──────────────────────────────────────────

const LEVEL_CONFIG: Record<string, {
  label: string; headerBg: string; borderColor: string;
  badgeColor: string; icon: React.ReactNode; tabKey: string;
}> = {
  '严重': {
    label: '危险', badgeColor: '#cf1322',
    headerBg: 'linear-gradient(135deg, #cb2d3e 0%, #ef473a 100%)',
    borderColor: '#ffa39e', icon: <FireFilled />, tabKey: 'severe',
  },
  '警告': {
    label: '警告', badgeColor: '#d46b08',
    headerBg: 'linear-gradient(135deg, #d46b08 0%, #fa8c16 100%)',
    borderColor: '#ffd591', icon: <WarningFilled />, tabKey: 'warning',
  },
  '异常': {
    label: '异常', badgeColor: '#d4380d',
    headerBg: 'linear-gradient(135deg, #d4380d 0%, #ff7a45 100%)',
    borderColor: '#ffbb96', icon: <ExclamationCircleFilled />, tabKey: 'abnormal',
  },
  '关注': {
    label: '关注', badgeColor: '#d4b106',
    headerBg: 'linear-gradient(135deg, #b8860b 0%, #d4b106 100%)',
    borderColor: '#ffe58f', icon: <InfoCircleFilled />, tabKey: 'attention',
  },
};

const LEVEL_TAG_COLOR: Record<string, string> = {
  '严重': 'error', '警告': 'warning', '异常': 'volcano', '关注': 'gold',
};

const TAB_KEY_TO_LEVEL: Record<string, string> = {
  severe: '严重', warning: '警告', abnormal: '异常', attention: '关注',
};

const TRENDING_CONFIG = {
  worsening: { icon: <ArrowUpOutlined />, color: '#ff4d4f', label: '趋势恶化' },
  stable:    { icon: <MinusOutlined />,   color: '#8c8c8c', label: '趋势平稳' },
  improving: { icon: <ArrowDownOutlined />, color: '#52c41a', label: '趋势好转' },
};

// Is this metric temperature or vibration?
const isTemperature = (metricId: number) => metricId === 0;

const RATIO_THRESHOLDS = [
  { max: 0.10, label: '正常',  color: '#52c41a' },
  { max: 0.20, label: '关注',  color: '#d4b106' },
  { max: 0.40, label: '异常',  color: '#d4380d' },
  { max: 0.70, label: '警告',  color: '#d46b08' },
  { max: Infinity, label: '危险', color: '#cf1322' },
];

const getRatioColor = (ratio: number) =>
  RATIO_THRESHOLDS.find(t => ratio < t.max)?.color ?? '#cf1322';

const toErrorMessage = (error: unknown): string => {
  const e = error as { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string } | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const formatDuration = (hours: number | null): string => {
  if (hours === null) return '首次发现';
  if (hours < 1) return `${Math.round(hours * 60)} 分钟`;
  if (hours < 24) return `${hours} 小时`;
  return `${Math.floor(hours / 24)} 天 ${Math.floor(hours % 24)} 小时`;
};

const fmt3 = (v?: number | null) => v != null ? Number(v).toFixed(3) : '-';
const fmtPct = (v?: number | null) => v != null ? `${(v * 100).toFixed(1)}%` : '-';

// ── Problem type badges shown on card ──────────────────

const ProblemTypeTags = ({ details }: { details: DiagnosisDetail[] }) => {
  const hasTemp = details.some(d => isTemperature(d.metricId) && d.levelScore > 0);
  const hasVib  = details.some(d => !isTemperature(d.metricId) && d.levelScore > 0);
  return (
    <Space size={4} wrap>
      {hasTemp && (
        <Tag icon={<FireOutlined />} color="volcano" style={{ fontSize: 12 }}>
          温度异常
        </Tag>
      )}
      {hasVib && (
        <Tag icon={<ThunderboltFilled />} color="processing" style={{ fontSize: 12 }}>
          振动异常
        </Tag>
      )}
    </Space>
  );
};

// ── Drawer: detailed diagnosis per metric ──────────────

const DetailDrawer = ({ dev, open, onClose }: {
  dev: FaultDevice | null; open: boolean; onClose: () => void;
}) => {
  if (!dev) return null;
  const cfg = LEVEL_CONFIG[dev.level];
  const trendCfg = TRENDING_CONFIG[dev.trending] || TRENDING_CONFIG.stable;

  return (
    <Drawer
      title={
        <Space>
          <span style={{ color: cfg?.badgeColor }}>{cfg?.icon}</span>
          <span>{dev.deviceName}</span>
          <Tag color={LEVEL_TAG_COLOR[dev.level]}>{cfg?.label}</Tag>
        </Space>
      }
      placement="right"
      width={560}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      {/* Device profile */}
      <Descriptions size="small" column={2} style={{ marginBottom: 20 }}>
        <Descriptions.Item label="设备编号">{dev.deviceCode}</Descriptions.Item>
        <Descriptions.Item label="设备分类">{dev.category}</Descriptions.Item>
        <Descriptions.Item label="所属区域">{dev.area}</Descriptions.Item>
        <Descriptions.Item label="持续时长">{formatDuration(dev.durationHours)}</Descriptions.Item>
        <Descriptions.Item label="趋势">
          <span style={{ color: trendCfg.color }}>
            {trendCfg.icon} {trendCfg.label}
          </span>
        </Descriptions.Item>
      </Descriptions>

      <Divider orientation="left" style={{ fontSize: 13, color: '#595959' }}>诊断明细</Divider>

      {dev.diagnosisDetails.length === 0 ? (
        <Empty description="暂无详细诊断记录" style={{ margin: '32px 0' }} />
      ) : (
        dev.diagnosisDetails.map((detail, idx) => {
          const ev = detail.evidence;
          const ratio = ev.ratio;
          const ratioColor = ratio != null ? getRatioColor(ratio) : '#8c8c8c';
          const isThermal = isTemperature(detail.metricId);

          return (
            <div
              key={idx}
              style={{
                border: '1px solid #f0f0f0',
                borderLeft: `3px solid ${ratioColor}`,
                borderRadius: 8,
                padding: '14px 16px',
                marginBottom: 14,
                background: '#fafafa',
              }}
            >
              {/* Metric header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <Space size={6}>
                  <span style={{ fontSize: 15 }}>
                    {isThermal ? <FireOutlined style={{ color: '#d4380d' }} /> : <ThunderboltFilled style={{ color: '#1890ff' }} />}
                  </span>
                  <Text strong style={{ fontSize: 14 }}>{detail.metricLabel}</Text>
                  <Tag color={LEVEL_TAG_COLOR[detail.level] || 'default'} style={{ fontSize: 11 }}>
                    {detail.level}
                  </Tag>
                </Space>
                {detail.diagnosedAt && (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    <ClockCircleOutlined style={{ marginRight: 3 }} />
                    {new Date(detail.diagnosedAt).toLocaleString('zh-CN', {
                      month: '2-digit', day: '2-digit',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </Text>
                )}
              </div>

              {/* Fault description */}
              {detail.description && (
                <div style={{
                  background: '#fff3cd',
                  border: '1px solid #ffe58f',
                  borderRadius: 6,
                  padding: '8px 12px',
                  fontSize: 13,
                  color: '#7d4e00',
                  marginBottom: 12,
                  lineHeight: '20px',
                }}>
                  {detail.description}
                </div>
              )}

              {/* Load ratio bar */}
              {ratio != null && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#595959', marginBottom: 4 }}>
                    <span>动态负荷占比</span>
                    <span style={{ fontWeight: 700, color: ratioColor }}>{fmtPct(ratio)}</span>
                  </div>
                  <Progress
                    percent={Math.min(Math.round(ratio * 100), 100)}
                    strokeColor={ratioColor}
                    showInfo={false}
                    size="small"
                    trailColor="#e8e8e8"
                  />
                  {/* Threshold markers */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#bfbfbf', marginTop: 2 }}>
                    <span>0%</span><span>10%</span><span>20%</span><span>40%</span><span>70%</span><span>100%</span>
                  </div>
                </div>
              )}

              {/* Evidence grid */}
              <Descriptions size="small" column={2} labelStyle={{ fontSize: 12, color: '#8c8c8c' }} contentStyle={{ fontSize: 12 }}>
                {ev.current != null && (
                  <Descriptions.Item label="当前值">
                    <strong>{fmt3(ev.current)} {isThermal ? '°C' : 'mm/s'}</strong>
                  </Descriptions.Item>
                )}
                {ev.healthyMedian != null && (
                  <Descriptions.Item label="健康基准">
                    {fmt3(ev.healthyMedian)} {isThermal ? '°C' : 'mm/s'}
                  </Descriptions.Item>
                )}
                {ev.peerMedian != null && (
                  <Descriptions.Item label="同组中位值">
                    {fmt3(ev.peerMedian)} {isThermal ? '°C' : 'mm/s'}
                  </Descriptions.Item>
                )}
                {ev.stSlope != null && (
                  <Descriptions.Item label="24h 趋势斜率">
                    <span style={{ color: ev.stSlope > 0 ? '#cf1322' : '#52c41a' }}>
                      {ev.stSlope > 0 ? '↑' : '↓'} {fmt3(ev.stSlope)}
                    </span>
                  </Descriptions.Item>
                )}
                {ev.mtSlope != null && (
                  <Descriptions.Item label="72h 趋势斜率">
                    <span style={{ color: ev.mtSlope > 0 ? '#cf1322' : '#52c41a' }}>
                      {ev.mtSlope > 0 ? '↑' : '↓'} {fmt3(ev.mtSlope)}
                    </span>
                  </Descriptions.Item>
                )}
                {ev.mutation != null && (
                  <Descriptions.Item label="突变量">
                    {fmt3(ev.mutation)}
                  </Descriptions.Item>
                )}
              </Descriptions>

              {/* Resampling status */}
              {ev.confirmationStatus && ev.confirmationStatus !== 'confirmed' && (
                <div style={{ marginTop: 8 }}>
                  <Tag color="processing" style={{ fontSize: 11 }}>复采确认中</Tag>
                </div>
              )}
            </div>
          );
        })
      )}
    </Drawer>
  );
};

// ── FaultDeviceCard (compact) ───────────────────────────

const FaultDeviceCard = ({ dev, onClick }: { dev: FaultDevice; onClick: () => void }) => {
  const cfg = LEVEL_CONFIG[dev.level] || {
    label: dev.level, badgeColor: '#8c8c8c',
    headerBg: '#8c8c8c', borderColor: '#d9d9d9', icon: null, tabKey: 'unknown',
  };
  const trendCfg = TRENDING_CONFIG[dev.trending] || TRENDING_CONFIG.stable;

  return (
    <div
      onClick={onClick}
      className="fault-device-card"
      style={{
        borderRadius: 10,
        overflow: 'hidden',
        border: `1px solid ${cfg.borderColor}`,
        boxShadow: '0 2px 10px rgba(0,0,0,0.06)',
        background: '#fff',
        cursor: 'pointer',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        transition: 'all 0.22s ease',
      }}
    >
      {/* Header strip */}
      <div style={{
        background: cfg.headerBg,
        padding: '12px 14px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <Space size={8}>
          <span style={{ color: '#fff', fontSize: 16 }}>{cfg.icon}</span>
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 14, lineHeight: 1.2 }}>
              {dev.deviceName}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 11, marginTop: 1 }}>
              {dev.deviceCode}
            </div>
          </div>
        </Space>
        <Tooltip title={trendCfg.label}>
          <span style={{ color: 'rgba(255,255,255,0.9)', fontSize: 14 }}>
            {trendCfg.icon}
          </span>
        </Tooltip>
      </div>

      {/* Body */}
      <div style={{ padding: '12px 14px', flex: 1 }}>
        {/* Category / Area */}
        <Space size={[4, 4]} wrap style={{ marginBottom: 10 }}>
          {dev.category && <Tag color="purple" style={{ fontSize: 11 }}>{dev.category}</Tag>}
          {dev.area && <Tag color="cyan" style={{ fontSize: 11 }}>{dev.area}</Tag>}
        </Space>

        {/* Problem type */}
        <ProblemTypeTags details={dev.diagnosisDetails} />
      </div>

      {/* Footer */}
      <div style={{
        padding: '8px 14px',
        borderTop: '1px solid #f5f5f5',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: '#fafafa',
      }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          持续 {formatDuration(dev.durationHours)}
        </Text>
        <Text type="secondary" style={{ fontSize: 11 }}>
          查看详情 <RightOutlined style={{ fontSize: 9 }} />
        </Text>
      </div>
    </div>
  );
};

// ── Main Page ───────────────────────────────────────────

const MonitoringPage = () => {
  const [searchParams] = useSearchParams();
  const levelFromUrl = searchParams.get('level') || 'all';

  const [loading, setLoading] = useState(false);
  const [faultDevices, setFaultDevices] = useState<FaultDevice[]>([]);
  const [activeTab, setActiveTab] = useState(levelFromUrl);
  const [drawerDev, setDrawerDev] = useState<FaultDevice | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      // 建议: 调用一个只返回 faultDevices 的专用接口，以减少数据传输量
      // const res = await request('/api/v1/dashboard/health');
      // setFaultDevices(res?.data?.faultDevices || []);
      const res = await request<FaultDevice[]>('/api/v1/devices/faults');
      setFaultDevices(res || []);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);
  useEffect(() => { setActiveTab(levelFromUrl); }, [levelFromUrl]);

  const filteredDevices = useMemo(() => {
    if (activeTab === 'all') return faultDevices;
    const targetLevel = TAB_KEY_TO_LEVEL[activeTab];
    return faultDevices.filter(d => d.level === targetLevel);
  }, [faultDevices, activeTab]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { severe: 0, warning: 0, abnormal: 0, attention: 0 };
    faultDevices.forEach(d => {
      const cfg = LEVEL_CONFIG[d.level];
      if (cfg) c[cfg.tabKey] = (c[cfg.tabKey] || 0) + 1;
    });
    return c;
  }, [faultDevices]);

  const tabItems = [
    {
      key: 'all',
      label: <Space size={4}><span>全部异常</span><Tag style={{ fontSize: 11 }}>{faultDevices.length}</Tag></Space>,
    },
    {
      key: 'severe',
      label: <Space size={4}><FireFilled style={{ color: '#cf1322' }} /><span>危险</span>{counts.severe > 0 && <Tag color="error" style={{ fontSize: 11 }}>{counts.severe}</Tag>}</Space>,
    },
    {
      key: 'warning',
      label: <Space size={4}><WarningFilled style={{ color: '#d46b08' }} /><span>警告</span>{counts.warning > 0 && <Tag color="warning" style={{ fontSize: 11 }}>{counts.warning}</Tag>}</Space>,
    },
    {
      key: 'abnormal',
      label: <Space size={4}><ExclamationCircleFilled style={{ color: '#d4380d' }} /><span>异常</span>{counts.abnormal > 0 && <Tag color="volcano" style={{ fontSize: 11 }}>{counts.abnormal}</Tag>}</Space>,
    },
    {
      key: 'attention',
      label: <Space size={4}><InfoCircleFilled style={{ color: '#d4b106' }} /><span>关注</span>{counts.attention > 0 && <Tag color="gold" style={{ fontSize: 11 }}>{counts.attention}</Tag>}</Space>,
    },
  ];

  return (
    <PageContainer
      title="异常设备监控"
      subTitle="显示最新一次诊断结论为非正常状态的设备"
      extra={
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => history.push('/dashboard/health')}>
            返回健康总览
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
            刷新
          </Button>
        </Space>
      }
    >
      <ProCard bordered>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            setActiveTab(key);
            history.push(key === 'all' ? '/dashboard/monitoring' : `/dashboard/monitoring?level=${key}`);
          }}
          items={tabItems}
          style={{ marginBottom: 16 }}
        />

        <Spin spinning={loading}>
          {filteredDevices.length === 0 ? (
            <Empty description={loading ? '加载中...' : '当前筛选条件下无异常设备'} style={{ margin: '60px 0' }} />
          ) : (
            <Row gutter={[16, 16]}>
              {filteredDevices.map(dev => (
                <Col xs={24} sm={12} lg={8} xl={6} key={dev.deviceId}>
                  <FaultDeviceCard dev={dev} onClick={() => setDrawerDev(dev)} />
                </Col>
              ))}
            </Row>
          )}
        </Spin>
      </ProCard>

      <DetailDrawer
        dev={drawerDev}
        open={drawerDev !== null}
        onClose={() => setDrawerDev(null)}
      />

      <style>{`
        .fault-device-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 24px rgba(0,0,0,0.1) !important;
        }
      `}</style>
    </PageContainer>
  );
};

export default MonitoringPage;
import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Result,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useParams } from '@umijs/max';

import {
  DiagnosisAttempt,
  DiagnosisDetailStatus,
  DiagnosisFault,
  DiagnosisTrend,
  getWxDiagnosisDetail,
  type DiagnosisReportDetail,
} from '@/services/diagnosisDetail';

import styles from './index.less';

const { Paragraph, Text, Title } = Typography;

const REPORT_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const LEVEL_COLORS: Record<string, string> = {
  正常: 'green',
  关注: 'gold',
  异常: 'orange',
  告警: 'red',
  危险: 'magenta',
};

const STATUS_META: Record<
  DiagnosisDetailStatus,
  { label: string; color: string; note: string }
> = {
  pending: {
    label: '处理中',
    color: 'processing',
    note: '分析流程还没有完成，页面会在数据就绪后显示完整依据。',
  },
  complete: {
    label: '已完成',
    color: 'success',
    note: '当前区域已拿到完整可展示数据。',
  },
  unavailable: {
    label: '暂不可用',
    color: 'default',
    note: '当前没有可展示的结构化数据，不能把它解释为正常。',
  },
  legacy_partial: {
    label: '历史数据不完整',
    color: 'warning',
    note: '该报告来自旧链路，只能展示已留存的部分证据。',
  },
};

function formatDateTime(value?: string | null) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatNumber(value?: number | null, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-';
  }
  return value.toFixed(digits);
}

function formatMaybeNumber(value: string | number | null, unit?: string | null) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  if (typeof value === 'number') {
    return `${formatNumber(value)}${unit ? ` ${unit}` : ''}`;
  }
  return `${value}${unit ? ` ${unit}` : ''}`;
}

function truncateId(value?: string | null) {
  if (!value) {
    return '-';
  }
  if (value.length <= 16) {
    return value;
  }
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

function sortAttempts(attempts: DiagnosisAttempt[]) {
  return [...attempts].sort((left, right) => {
    const leftSequence = left.sequence ?? 0;
    const rightSequence = right.sequence ?? 0;
    if (leftSequence !== rightSequence) {
      return leftSequence - rightSequence;
    }
    return (left.diagnosed_at || '').localeCompare(right.diagnosed_at || '');
  });
}

function getStatusMeta(status: DiagnosisDetailStatus) {
  return STATUS_META[status] || STATUS_META.unavailable;
}

function getGapMarkArea(points: Array<number | null>, times: string[]) {
  const markAreas: Array<Array<{ xAxis: string }>> = [];
  let gapStartIndex = -1;

  for (let index = 0; index < points.length; index += 1) {
    if (points[index] === null) {
      if (gapStartIndex === -1) {
        gapStartIndex = index;
      }
    } else if (gapStartIndex !== -1) {
      const startIndex = Math.max(0, gapStartIndex - 1);
      markAreas.push([{ xAxis: times[startIndex] }, { xAxis: times[index] }]);
      gapStartIndex = -1;
    }
  }

  if (gapStartIndex !== -1 && times.length) {
    const startIndex = Math.max(0, gapStartIndex - 1);
    markAreas.push([{ xAxis: times[startIndex] }, { xAxis: times[times.length - 1] }]);
  }

  if (!markAreas.length) {
    return undefined;
  }

  return {
    itemStyle: { color: 'rgba(148, 163, 184, 0.16)' },
    label: {
      show: true,
      position: 'insideTop',
      color: '#64748b',
      formatter: '缺失/离线',
      padding: [8, 0, 0, 0],
    },
    data: markAreas,
  };
}

function buildTrendOption(trend: DiagnosisTrend) {
  const validSeries = trend.series.filter((series) => series.points.length > 0);
  if (!validSeries.length) {
    return null;
  }

  const timeSet = new Set<string>();
  validSeries.forEach((series) => {
    series.points.forEach((point) => {
      timeSet.add(point.sampled_at);
    });
  });

  const times = Array.from(timeSet).sort((left, right) => left.localeCompare(right));
  const primarySeries = validSeries[0];
  const primaryValues = times.map((time) => {
    const point = primarySeries.points.find((item) => item.sampled_at === time);
    return point?.value ?? null;
  });

  const series: any[] = validSeries.map((item, index) => {
    const pointMap = new Map(item.points.map((point) => [point.sampled_at, point]));
    const colorPalette = ['#1677ff', '#13c2c2', '#fa8c16', '#722ed1'];
    const color = colorPalette[index % colorPalette.length];
    return {
      name: item.label,
      type: 'line',
      smooth: true,
      showSymbol: false,
      connectNulls: false,
      data: times.map((time) => pointMap.get(time)?.value ?? null),
      lineStyle: { width: 2, color },
      itemStyle: { color },
      areaStyle:
        index === 0
          ? {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(22, 119, 255, 0.20)' },
                { offset: 1, color: 'rgba(22, 119, 255, 0.02)' },
              ]),
            }
          : undefined,
      markArea: index === 0 ? getGapMarkArea(primaryValues, times) : undefined,
    };
  });

  const thresholdConfigs = [
    { field: 'threshold', name: '阈值', color: '#cf1322' },
    { field: 'upper_threshold', name: '上阈值', color: '#d4380d' },
    { field: 'lower_threshold', name: '下阈值', color: '#389e0d' },
  ] as const;

  thresholdConfigs.forEach((config) => {
    const values = times.map((time) => {
      const point = primarySeries.points.find((item) => item.sampled_at === time);
      return point?.[config.field] ?? null;
    });
    if (values.some((value) => value !== null)) {
      series.push({
        name: config.name,
        type: 'line',
        showSymbol: false,
        connectNulls: false,
        data: values,
        lineStyle: { width: 1.5, type: 'dashed', color: config.color },
        itemStyle: { color: config.color },
      });
    }
  });

  return {
    animation: false,
    tooltip: { trigger: 'axis' },
    legend: { top: 8, type: 'scroll' },
    grid: { left: 52, right: 18, top: 48, bottom: 52, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: times.map((time) => formatDateTime(time)),
      axisLabel: { color: '#64748b', hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      name: primarySeries.unit || '',
      axisLabel: { color: '#64748b' },
      splitLine: { lineStyle: { color: '#e5e7eb' } },
    },
    dataZoom: [
      { type: 'inside' },
      { type: 'slider', height: 16, bottom: 16 },
    ],
    series,
  };
}

const EChartPanel = ({
  option,
  height = 280,
}: {
  option: any;
  height?: number;
}) => {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!chartRef.current || !option) {
      return undefined;
    }
    const chart = echarts.getInstanceByDom(chartRef.current) || echarts.init(chartRef.current);
    chart.setOption(option, true);
    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
    };
  }, [option]);

  return <div ref={chartRef} style={{ width: '100%', height }} />;
};

const StateHint = ({
  status,
  title,
}: {
  status: DiagnosisDetailStatus;
  title: string;
}) => {
  const meta = getStatusMeta(status);
  const type =
    status === 'complete'
      ? 'success'
      : status === 'pending'
        ? 'info'
        : status === 'legacy_partial'
          ? 'warning'
          : 'info';
  return (
    <Alert
      showIcon
      type={type}
      message={`${title}：${meta.label}`}
      description={meta.note}
    />
  );
};

const FaultHeader = ({ fault }: { fault: DiagnosisFault }) => (
  <div className={styles.faultHeader}>
    <div>
      <Space wrap size={[8, 8]}>
        <Tag color="blue">{fault.fault_label}</Tag>
        {fault.level_label ? (
          <Tag color={LEVEL_COLORS[fault.level_label] || 'default'}>{fault.level_label}</Tag>
        ) : null}
        <Tag color={getStatusMeta(fault.status).color}>{getStatusMeta(fault.status).label}</Tag>
        {fault.evidence_schema_version ? (
          <Tag bordered={false}>evidence v{fault.evidence_schema_version}</Tag>
        ) : null}
      </Space>
      <Title level={4} className={styles.faultTitle}>
        {fault.summary || `${fault.fault_label}诊断详情`}
      </Title>
    </div>
  </div>
);

function renderChecks(fault: DiagnosisFault) {
  if (!fault.checks.length) {
    return <StateHint status={fault.status} title="规则判定" />;
  }

  return (
    <div className={styles.checkList}>
      {fault.checks.map((check) => (
        <div key={check.key} className={styles.checkRow}>
          <div className={styles.checkTitleRow}>
            <Text strong>{check.label}</Text>
            <Tag color={check.triggered ? 'red' : 'default'}>
              {check.triggered ? '触发' : '未触发'}
            </Tag>
          </div>
          <div className={styles.checkMetaGrid}>
            <div>
              <Text type="secondary">实际值</Text>
              <div>{formatMaybeNumber(check.actual, check.unit)}</div>
            </div>
            <div>
              <Text type="secondary">比较符</Text>
              <div>{check.comparator || '-'}</div>
            </div>
            <div>
              <Text type="secondary">阈值</Text>
              <div>{formatMaybeNumber(check.threshold, check.unit)}</div>
            </div>
          </div>
          {check.summary ? <Text type="secondary">{check.summary}</Text> : null}
        </div>
      ))}
    </div>
  );
}

function renderTrend(fault: DiagnosisFault) {
  const trend = fault.trend;
  if (!trend) {
    return <StateHint status="unavailable" title="温度趋势" />;
  }

  const option = buildTrendOption(trend);
  return (
    <div className={styles.sectionBlock}>
      <div className={styles.sectionTitleRow}>
        <Title level={5}>24 / 72 小时趋势</Title>
        <Tag color={getStatusMeta(trend.status).color}>{getStatusMeta(trend.status).label}</Tag>
      </div>
      {trend.note ? <Paragraph type="secondary">{trend.note}</Paragraph> : null}
      {option ? (
        <div className={styles.chartScroller}>
          <div className={styles.chartCanvas}>
            <EChartPanel option={option} height={300} />
          </div>
        </div>
      ) : (
        <StateHint status={trend.status} title="温度趋势" />
      )}
    </div>
  );
}

function renderAttempts(fault: DiagnosisFault) {
  if (!fault.attempts.length) {
    return <StateHint status={fault.status} title="复采时间线" />;
  }

  return (
    <Timeline
      items={sortAttempts(fault.attempts).map((attempt) => ({
        color:
          attempt.level_label && LEVEL_COLORS[attempt.level_label]
            ? LEVEL_COLORS[attempt.level_label]
            : '#1677ff',
        children: (
          <div className={styles.attemptCard}>
            <Space wrap size={[8, 8]}>
              <Tag>{attempt.phase || '未知阶段'}</Tag>
              {attempt.sequence !== null ? <Tag>序号 {attempt.sequence}</Tag> : null}
              {attempt.result_status ? <Tag>{attempt.result_status}</Tag> : null}
              {attempt.level_label ? (
                <Tag color={LEVEL_COLORS[attempt.level_label] || 'default'}>
                  {attempt.level_label}
                </Tag>
              ) : null}
            </Space>
            <div className={styles.attemptMetaGrid}>
              <div>
                <Text type="secondary">时间</Text>
                <div>{formatDateTime(attempt.diagnosed_at)}</div>
              </div>
              <div>
                <Text type="secondary">RMS</Text>
                <div>{formatMaybeNumber(attempt.rms, 'mm/s')}</div>
              </div>
              <div>
                <Text type="secondary">报告</Text>
                <div className={styles.breakAll}>{truncateId(attempt.report_id)}</div>
              </div>
            </div>
            {attempt.confirmation_status ? (
              <Text type="secondary">{`确认状态：${attempt.confirmation_status}`}</Text>
            ) : null}
            {attempt.description ? <Paragraph>{attempt.description}</Paragraph> : null}
          </div>
        ),
      }))}
    />
  );
}

const WxDiagnosisDetailPage = () => {
  const { reportId = '' } = useParams<{ reportId: string }>();
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<DiagnosisReportDetail | null>(null);
  const [pageError, setPageError] = useState<
    'invalid' | 'forbidden' | 'not_found' | 'load_failed' | null
  >(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    const run = async () => {
      if (!REPORT_ID_RE.test(reportId)) {
        setDetail(null);
        setPageError('invalid');
        setLoading(false);
        return;
      }

      setLoading(true);
      setPageError(null);
      try {
        const data = await getWxDiagnosisDetail(reportId);
        setDetail(data);
      } catch (error: any) {
        const code = Number(error?.code || error?.response?.status || 0);
        setDetail(null);
        if (code === 401 || code === 403) {
          setPageError('forbidden');
        } else if (code === 404) {
          setPageError('not_found');
        } else {
          setPageError('load_failed');
          if (!error?.businessErrorShown) {
            message.error(error?.data?.detail || error?.message || '诊断详情加载失败');
          }
        }
      } finally {
        setLoading(false);
      }
    };

    void run();
  }, [reportId, reloadTick]);

  let content = null;

  if (loading) {
    content = (
      <Card className={styles.contentCard}>
        <div className={styles.loadingWrap}>
          <Spin size="large" />
          <Text type="secondary">正在加载诊断详情…</Text>
        </div>
      </Card>
    );
  } else if (pageError === 'invalid') {
    content = (
      <Result
        status="warning"
        title="报告编号格式不正确"
        subTitle="该页面只能通过合法的诊断详情链接访问。"
      />
    );
  } else if (pageError === 'forbidden') {
    content = (
      <Result
        status="403"
        title="授权已失效或无权查看"
        subTitle="请从微信通知消息重新进入该页面，或联系管理员确认接收权限。"
      />
    );
  } else if (pageError === 'not_found') {
    content = (
      <Result
        status="404"
        title="没有找到这次诊断记录"
        subTitle="该 report_id 可能已失效，或当前账号不在可查看范围内。"
      />
    );
  } else if (!detail || pageError === 'load_failed') {
    content = (
      <Result
        status="error"
        title="诊断详情暂时无法打开"
        subTitle="请稍后刷新重试；如果持续失败，请联系系统管理员检查服务状态。"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => setReloadTick((value) => value + 1)}>
            重新加载
          </Button>
        }
      />
    );
  } else {
    const orderedFaults = [...detail.faults].sort((left, right) => {
      const order = { temperature: 0, vibration: 1 } as Record<string, number>;
      return (order[left.fault_type] ?? 99) - (order[right.fault_type] ?? 99);
    });

    content = (
      <>
        <Card className={styles.heroCard}>
          <div className={styles.heroHead}>
            <div>
              <Space wrap size={[8, 8]}>
                {detail.report.overall_label ? (
                  <Tag color={LEVEL_COLORS[detail.report.overall_label] || 'default'}>
                    {detail.report.overall_label}
                  </Tag>
                ) : null}
                {orderedFaults.map((fault) => (
                  <Tag key={fault.case_id} color="blue">
                    {fault.fault_label}
                  </Tag>
                ))}
              </Space>
              <Title level={3} className={styles.heroTitle}>
                {detail.device.name || '诊断详情'}
              </Title>
              <Paragraph type="secondary" className={styles.heroSubtitle}>
                以本次报告为主线展示当时的判定依据、复采过程和频谱分析结果。
              </Paragraph>
            </div>
            <Button icon={<ReloadOutlined />} onClick={() => setReloadTick((value) => value + 1)}>
              刷新
            </Button>
          </div>
          <Descriptions column={1} size="small" className={styles.summaryDescriptions}>
            <Descriptions.Item label="设备编码">{detail.device.code || '-'}</Descriptions.Item>
            <Descriptions.Item label="设备分类">{detail.device.category || '-'}</Descriptions.Item>
            <Descriptions.Item label="工艺段">{detail.device.process || '-'}</Descriptions.Item>
            <Descriptions.Item label="安装位置">{detail.device.location || '-'}</Descriptions.Item>
            <Descriptions.Item label="采样时间">{formatDateTime(detail.report.sampled_at)}</Descriptions.Item>
            <Descriptions.Item label="诊断时间">{formatDateTime(detail.report.diagnosed_at)}</Descriptions.Item>
            <Descriptions.Item label="报告编号">
              <span className={styles.breakAll}>{detail.report.report_id || reportId}</span>
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {!orderedFaults.length ? (
          <Card className={styles.contentCard}>
            <Empty description="该诊断记录没有可展示的故障项。" />
          </Card>
        ) : null}

        {orderedFaults.map((fault) => (
          <Card key={fault.case_id} className={styles.contentCard}>
            <FaultHeader fault={fault} />
            {fault.status === 'legacy_partial' ? (
              <Alert
                showIcon
                type="warning"
                message="该故障项来自旧链路"
                description="页面只展示已留存字段；缺失数据不会被伪造成正常或已完成。"
                style={{ marginBottom: 16 }}
              />
            ) : null}

            {fault.fault_type === 'temperature' ? (
              <div className={styles.sectionStack}>
                <div className={styles.sectionBlock}>
                  <Title level={5}>规则判定</Title>
                  {renderChecks(fault)}
                </div>
                {renderTrend(fault)}
              </div>
            ) : (
              <div className={styles.sectionStack}>
                <div className={styles.sectionBlock}>
                  <Title level={5}>复采时间线</Title>
                  {renderAttempts(fault)}
                </div>
              </div>
            )}
          </Card>
        ))}

        <Card className={styles.contentCard}>
          <Title level={5}>数据来源与说明</Title>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="阈值快照">
              {detail.provenance.thresholds || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="趋势数据">
              {detail.provenance.trend_series || '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </>
    );
  }

  return <div className={styles.page}>{content}</div>;
};

export default WxDiagnosisDetailPage;

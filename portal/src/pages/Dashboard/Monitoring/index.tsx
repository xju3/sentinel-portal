import { useEffect, useMemo, useState } from 'react';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Badge, Button, Col, Drawer, Empty, List, Row, Space, Spin, Tag, Tooltip, message } from 'antd';

import { listAllSensorMonitorings } from '@/services/sensorMonitoring';
import HistoryPage from '@/pages/Monitoring/Sensors/History';

// 异常映射字典
const ANOMALY_MAP: Record<number, { text: string; color: string; status: 'warning' | 'error' }> = {
  1: { text: '振动异常', color: 'warning', status: 'warning' },
  2: { text: '温度异常', color: 'error', status: 'error' },
  3: { text: '振动+温度异常', color: 'magenta', status: 'error' },
};

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | {
        data?: { detail?: string };
        info?: { errorMessage?: string };
        message?: string;
      }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const getArray = (data: any) => (Array.isArray(data) ? data : data?.items || data?.data || []);

const MonitoringSensorsPage = () => {
  const [loading, setLoading] = useState(false);

  // 数据源
  const [monitorings, setMonitorings] = useState<any[]>([]);

  // 侧边栏图表状态
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [activeSensorSn, setActiveSensorSn] = useState<string | undefined>();
  const [activeLocationName, setActiveLocationName] = useState<string | undefined>();

  const loadData = async () => {
    setLoading(true);
    try {
      const mRes = await listAllSensorMonitorings();
      setMonitorings(mRes || []);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const alertGroups = useMemo(() => {
    const safeMonitorings = getArray(monitorings);

    const anomalousMonitorings = safeMonitorings.filter((m: any) => m && m.anomaly > 0);

    const groups = new Map<string, any>();
    anomalousMonitorings.forEach((m: any) => {
      const deviceId = m.device_inst_id;
      if (!deviceId) return;

      if (!groups.has(deviceId)) {
        groups.set(deviceId, {
          device: m.device_inst || { id: deviceId, code: '未知设备', name: '未知设备' },
          alerts: [],
        });
      }

      groups.get(deviceId).alerts.push({
        monitoring: m,
        location: m.location || { name: '未知测点' },
        sensor: m.sensor || { sn: '未知SN' },
      });
    });

    return Array.from(groups.values());
  }, [monitorings]);

  return (
    <PageContainer title="设备报警监控" subTitle="实时监控存在异常状态的设备及其测点">
      <Spin spinning={loading}>
        {alertGroups.length === 0 ? (
          <Empty description="当前所有设备运行正常" style={{ margin: '80px 0' }} />
        ) : (
          <Row gutter={[16, 16]}>
            {alertGroups.map((group) => {
              const dev = group.device;
              const spec = dev?.device_spec;
              const categoryName = spec?.device_category?.name;
              // 假设后端返回了工段/区域信息，或者可为空
              const processName = dev?.process_device?.process?.name;
              const areaName = dev?.process_device?.area?.name;
              return (
                <Col xs={24} lg={12} xl={8} key={group.device.id}>
                  <ProCard
                    bordered
                    hoverable
                    style={{ height: '100%', borderRadius: 8 }}
                    bodyStyle={{ paddingTop: 0 }}
                  >
                    {/* 标题区域：四行结构 */}
                    <div style={{ marginBottom: 12 }}>
                      {/* 第1行：Code + 异常Badge */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Badge status="error" />
                        <span style={{ fontWeight: 600, fontSize: 15, color: '#1f1f1f' }}>
                          {group.device.code || '-'}
                        </span>
                      </div>
                      {/* 第2行：Name */}
                      <div style={{ marginBottom: 6, fontSize: 13, color: '#666' }}>
                        {group.device.name || '-'}
                      </div>
                      {/* 第3行：标签（分类 / 工段 / 区域） */}
                      {(categoryName || processName || areaName) && (
                        <div style={{ marginBottom: 6 }}>
                          <Space size={[4, 4]} wrap>
                            {categoryName && (
                              <Tag color="purple">{categoryName}</Tag>
                            )}
                            {processName && (
                              <Tag color="cyan">{processName}</Tag>
                            )}
                            {areaName && (
                              <Tag color="green">{areaName}</Tag>
                            )}
                          </Space>
                        </div>
                      )}
                      {/* 第4行：规格 + 描述 */}
                      {(spec?.name || group.device.desc) && (
                        <div style={{ fontSize: 12, color: '#8c8c8c', lineHeight: '18px' }}>
                          {spec?.name && (
                            <span>
                              规格：{spec.name}{spec.model ? ` / ${spec.model}` : ''}{spec.brand ? ` / ${spec.brand}` : ''}
                            </span>
                          )}
                          {spec?.name && group.device.desc && <span style={{ margin: '0 6px' }}>|</span>}
                          {group.device.desc && (
                            <Tooltip title={group.device.desc}>
                              <span
                                style={{
                                  display: 'inline-block',
                                  maxWidth: 160,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                  verticalAlign: 'bottom',
                                }}
                              >
                                {group.device.desc}
                              </span>
                            </Tooltip>
                          )}
                        </div>
                      )}
                    </div>

                    <List
                      itemLayout="horizontal"
                      dataSource={group.alerts}
                      renderItem={(item: any) => {
                        const meta = ANOMALY_MAP[item.monitoring.anomaly] || { text: '未知异常', color: 'default' };
                        return (
                          <List.Item
                            actions={[
                              <Button
                                type="link"
                                size="small"
                                onClick={() => {
                                  setActiveSensorSn(item.sensor?.sn);
                                  setActiveLocationName(item.location?.name || '未知测点');
                                  setDrawerVisible(true);
                                }}
                              >
                                分析
                              </Button>,
                            ]}
                          >
                            <List.Item.Meta
                              title={item.location?.name || '未知测点'}
                              description={`时间: ${item.monitoring.ts ? new Date(item.monitoring.ts).toLocaleString() : '-'}`}
                            />
                            <Tag color={meta.color}>{meta.text}</Tag>
                          </List.Item>
                        );
                      }}
                    />
                  </ProCard>
                </Col>
              );
            })}
          </Row>
        )}
      </Spin>

      <Drawer
        title={`测点分析图表 - ${activeLocationName || ''}`}
        placement="right"
        width={960}
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
        destroyOnClose
      >
        {activeSensorSn && <HistoryPage sensorSn={activeSensorSn} locationName={activeLocationName} embedded />}
      </Drawer>
    </PageContainer>
  );
};

export default MonitoringSensorsPage;
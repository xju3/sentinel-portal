import { useEffect, useMemo, useState } from 'react';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Badge, Button, Col, Drawer, Empty, List, Row, Spin, Tag, message } from 'antd';

import { listAllSensorMonitorings, listSensorMonitoringDeviceInstOptions } from '@/services/sensorMonitoring';
import { listAllLocations } from '@/services/location';
import { listAllSensors } from '@/services/tenantSensor';
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

const MonitoringSensorsPage = () => {
  const [loading, setLoading] = useState(false);
  
  // 数据源
  const [monitorings, setMonitorings] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [sensors, setSensors] = useState<any[]>([]);

  // 侧边栏图表状态
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [activeSensorSn, setActiveSensorSn] = useState<string | undefined>();
  const [activeLocationName, setActiveLocationName] = useState<string | undefined>();

  const loadData = async () => {
    setLoading(true);
    try {
      const [mRes, dRes, lRes, sRes] = await Promise.all([
        listAllSensorMonitorings(),
        listSensorMonitoringDeviceInstOptions(),
        listAllLocations(),
        listAllSensors(),
      ]);
      setMonitorings(mRes || []);
      setDevices(dRes || []);
      setLocations(lRes || []);
      setSensors(sRes || []);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // 核心分组逻辑：只找出存在报警的测点，并按设备实例归类
  const alertGroups = useMemo(() => {
    const getArray = (data: any) => (Array.isArray(data) ? data : data?.items || data?.data || []);

    const safeMonitorings = getArray(monitorings);
    const safeDevices = getArray(devices);
    const safeLocations = getArray(locations);
    const safeSensors = getArray(sensors);

    const anomalousMonitorings = safeMonitorings.filter((m: any) => m && m.anomaly > 0);
    
    const groups = new Map<string, any>();
    anomalousMonitorings.forEach((m: any) => {
      const device = safeDevices.find((d: any) => d && d.id === m.device_inst_id);
      if (!device) return;
      
      if (!groups.has(device.id)) {
        groups.set(device.id, {
          device,
          alerts: [],
        });
      }
      
      groups.get(device.id).alerts.push({
        monitoring: m,
        location: safeLocations.find((l: any) => l && l.id === m.location_id),
        sensor: safeSensors.find((s: any) => s && s.id === m.sensor_id),
      });
    });

    return Array.from(groups.values());
  }, [monitorings, devices, locations, sensors]);

  return (
    <PageContainer title="设备报警监控" subTitle="实时监控存在异常状态的设备及其测点">
      <Spin spinning={loading}>
        {alertGroups.length === 0 ? (
          <Empty description="当前所有设备运行正常" style={{ margin: '80px 0' }} />
        ) : (
          <Row gutter={[16, 16]}>
            {alertGroups.map((group) => (
              <Col xs={24} lg={12} xl={8} key={group.device.id}>
                <ProCard
                  title={<span><Badge status="error" style={{ marginRight: 8 }} />{group.device.code}</span>}
                  subTitle={group.device.sn}
                  headerBordered
                  bordered
                  hoverable
                  style={{ height: '100%' }}
                >
                  <List
                    itemLayout="horizontal"
                    dataSource={group.alerts}
                    renderItem={(item: any) => {
                      const meta = ANOMALY_MAP[item.monitoring.anomaly] || { text: '未知异常', color: 'default' };
                      return (
                        <List.Item
                          actions={[
                            <Button type="link" size="small" onClick={() => {
                              setActiveSensorSn(item.sensor?.sn);
                              setActiveLocationName(item.location?.name || '未知测点');
                              setDrawerVisible(true);
                            }}>分析</Button>
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
            ))}
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

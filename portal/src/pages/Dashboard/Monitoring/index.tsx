import { useEffect, useMemo, useState } from 'react';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Badge, Button, Col, Drawer, Empty, List, Row, Space, Spin, Tag, Tooltip, message } from 'antd';

import { listAllSensorMonitorings, listSensorMonitoringDeviceInstOptions } from '@/services/sensorMonitoring';
import { listAllLocations } from '@/services/location';
import { listAllSensors } from '@/services/tenantSensor';
import { listAllDeviceSpecs } from '@/services/deviceSpec';
import { listAllDeviceCategories } from '@/services/deviceCategory';
import { listAllProcessDeviceItems, listAllProcessDevices, listAllProcesses } from '@/services/process';
import { listAllAreas } from '@/services/area';
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
  const [devices, setDevices] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [sensors, setSensors] = useState<any[]>([]);
  const [specs, setSpecs] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [processes, setProcesses] = useState<any[]>([]);
  const [processDevices, setProcessDevices] = useState<any[]>([]);
  const [processDeviceItems, setProcessDeviceItems] = useState<any[]>([]);
  const [areas, setAreas] = useState<any[]>([]);

  // 侧边栏图表状态
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [activeSensorSn, setActiveSensorSn] = useState<string | undefined>();
  const [activeLocationName, setActiveLocationName] = useState<string | undefined>();

  const loadData = async () => {
    setLoading(true);
    try {
      const [mRes, dRes, lRes, sRes, specRes, catRes, procRes, pdRes, pdiRes, areaRes] = await Promise.all([
        listAllSensorMonitorings(),
        listSensorMonitoringDeviceInstOptions(),
        listAllLocations(),
        listAllSensors(),
        listAllDeviceSpecs(),
        listAllDeviceCategories(),
        listAllProcesses(),
        listAllProcessDevices(),
        listAllProcessDeviceItems(),
        listAllAreas(),
      ]);
      setMonitorings(mRes || []);
      setDevices(dRes || []);
      setLocations(lRes || []);
      setSensors(sRes || []);
      setSpecs(specRes || []);
      setCategories(catRes || []);
      setProcesses(procRes || []);
      setProcessDevices(pdRes || []);
      setProcessDeviceItems(pdiRes || []);
      setAreas(areaRes || []);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // 构建设备关系映射：DeviceInst → DeviceSpec → DeviceCategory → Process → Area
  const deviceRelationMap = useMemo(() => {
    const safeDevices = getArray(devices);
    const safeProcessDeviceItems = getArray(processDeviceItems);
    const safeProcessDevices = getArray(processDevices);
    const safeAreas = getArray(areas);
    const safeProcesses = getArray(processes);
    const safeCategories = getArray(categories);
    const safeSpecs = getArray(specs);

    // processDeviceItem → processDevice 映射 (按 device_inst_id)
    const pdiToPd = new Map<string, string>();
    safeProcessDeviceItems.forEach((pdi: any) => {
      if (pdi?.device_inst_id && pdi?.process_device_id) {
        pdiToPd.set(pdi.device_inst_id, pdi.process_device_id);
      }
    });

    // processDevice 快速查找表
    const pdMap = new Map<string, any>();
    safeProcessDevices.forEach((pd: any) => {
      if (pd?.id) {
        pdMap.set(pd.id, pd);
      }
    });

    // 各实体快速查找表
    const areaMap = new Map(safeAreas.map((a: any) => [a.id, a]));
    const processMap = new Map(safeProcesses.map((p: any) => [p.id, p]));
    const categoryMap = new Map(safeCategories.map((c: any) => [c.id, c]));
    const specMap = new Map(safeSpecs.map((s: any) => [s.id, s]));

    // 按 device_inst_id 汇总关系
    const result = new Map<string, any>();
    safeDevices.forEach((d: any) => {
      if (!d?.id) return;

      const spec = specMap.get(d.device_spec_id);
      const category = spec ? categoryMap.get(spec.device_category_id) : undefined;

      const pdId = pdiToPd.get(d.id);
      const pd = pdId ? pdMap.get(pdId) : undefined;
      const process = pd ? processMap.get(pd.process_id) : undefined;
      const area = pd?.area_id ? areaMap.get(pd.area_id) : undefined;

      result.set(d.id, {
        specName: spec?.name || undefined,
        specModel: spec?.model || undefined,
        specBrand: spec?.brand || undefined,
        categoryName: category?.name || undefined,
        processName: process?.name || undefined,
        areaName: area?.name || undefined,
      });
    });

    return result;
  }, [devices, specs, categories, processes, processDevices, processDeviceItems, areas]);

  // 核心分组逻辑：只找出存在报警的测点，并按设备实例归类
  const alertGroups = useMemo(() => {
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
          relation: deviceRelationMap.get(device.id),
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
  }, [monitorings, devices, locations, sensors, deviceRelationMap]);

  return (
    <PageContainer title="设备报警监控" subTitle="实时监控存在异常状态的设备及其测点">
      <Spin spinning={loading}>
        {alertGroups.length === 0 ? (
          <Empty description="当前所有设备运行正常" style={{ margin: '80px 0' }} />
        ) : (
          <Row gutter={[16, 16]}>
            {alertGroups.map((group) => {
              const rel = group.relation;
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
                      {(rel?.categoryName || rel?.processName || rel?.areaName) && (
                        <div style={{ marginBottom: 6 }}>
                          <Space size={[4, 4]} wrap>
                            {rel?.categoryName && (
                              <Tag color="purple">{rel.categoryName}</Tag>
                            )}
                            {rel?.processName && (
                              <Tag color="cyan">{rel.processName}</Tag>
                            )}
                            {rel?.areaName && (
                              <Tag color="green">{rel.areaName}</Tag>
                            )}
                          </Space>
                        </div>
                      )}
                      {/* 第4行：规格 + 描述 */}
                      {(rel?.specName || group.device.desc) && (
                        <div style={{ fontSize: 12, color: '#8c8c8c', lineHeight: '18px' }}>
                          {rel?.specName && (
                            <span>
                              规格：{rel.specName}{rel.specModel ? ` / ${rel.specModel}` : ''}{rel.specBrand ? ` / ${rel.specBrand}` : ''}
                            </span>
                          )}
                          {rel?.specName && group.device.desc && <span style={{ margin: '0 6px' }}>|</span>}
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
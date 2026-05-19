import { useEffect, useMemo, useState } from 'react';
import { PageContainer, ProColumns, ProTable } from '@ant-design/pro-components';
import { Tag, message } from 'antd';

import { listAllSensors, listAllTenantSensors, Sensor, TenantSensor } from '@/services/tenantSensor';

type SensorViewRow = TenantSensor & {
  sensor_sn: string;
  sensor_type_id: string;
  description?: string;
  battery?: number;
  active?: boolean;
  active_at?: string;
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
  const [rows, setRows] = useState<SensorViewRow[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});

  const loadRows = async () => {
    setLoading(true);
    try {
      const [tenantSensors, sensors] = await Promise.all([listAllTenantSensors(), listAllSensors()]);
      const sensorMap = new Map<string, Sensor>(sensors.map((item) => [item.id, item]));
      const merged: SensorViewRow[] = tenantSensors.map((item) => {
        const sensor = sensorMap.get(item.sensor_id);
        return {
          ...item,
          sensor_sn: sensor?.sn || '-',
          sensor_type_id: sensor?.sensor_type_id || '-',
          description: sensor?.description,
          battery: sensor?.battery,
          active: sensor?.active,
          active_at: sensor?.active_at,
        };
      });
      setRows(merged);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.sensor_sn && !norm(row.sensor_sn).includes(norm(query.sensor_sn))) {
        return false;
      }
      if (query.sensor_id && !norm(row.sensor_id).includes(norm(query.sensor_id))) {
        return false;
      }
      if (query.sensor_type_id && !norm(row.sensor_type_id).includes(norm(query.sensor_type_id))) {
        return false;
      }
      if (query.tenant_id && !norm(row.tenant_id).includes(norm(query.tenant_id))) {
        return false;
      }
      if (query.available !== undefined && query.available !== null && query.available !== '') {
        if (String(row.available) !== String(query.available)) {
          return false;
        }
      }
      if (query.active !== undefined && query.active !== null && query.active !== '') {
        if (String(row.active) !== String(query.active)) {
          return false;
        }
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<SensorViewRow>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '传感器SN',
      dataIndex: 'sensor_sn',
      width: 180,
    },
    {
      title: '电量(%)',
      dataIndex: 'battery',
      width: 100,
      hideInSearch: true,
      render: (_, row) => (row.battery === undefined ? '-' : Number(row.battery).toFixed(1)),
    },
    {
      title: '可用状态',
      dataIndex: 'available',
      width: 110,
      valueType: 'select',
      valueEnum: {
        true: { text: '可用' },
        false: { text: '不可用' },
      },
      render: (_, row) => (row.available ? <Tag color="green">可用</Tag> : <Tag>不可用</Tag>),
    },
    {
      title: '设备状态',
      dataIndex: 'active',
      width: 110,
      valueType: 'select',
      valueEnum: {
        true: { text: '在线' },
        false: { text: '离线' },
      },
      render: (_, row) =>
        row.active === undefined ? '-' : row.active ? <Tag color="green">在线</Tag> : <Tag>离线</Tag>,
    },
    {
      title: '最近活跃',
      dataIndex: 'active_at',
      width: 180,
      valueType: 'dateTime',
      hideInSearch: true,
      render: (_, row) => row.active_at || '-',
    },
    {
      title: '备注',
      dataIndex: 'description',
      hideInSearch: true,
      ellipsis: true,
      render: (_, row) => row.description || '-',
    },
  ];

  return (
    <PageContainer title="传感器">
      <ProTable<SensorViewRow>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadRows }}
        toolBarRender={false}
      />
    </PageContainer>
  );
};

export default MonitoringSensorsPage;

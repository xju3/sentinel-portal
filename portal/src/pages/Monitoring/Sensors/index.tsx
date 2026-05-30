import { useEffect, useMemo, useState } from 'react';
import { PageContainer, ProColumns, ProTable } from '@ant-design/pro-components';
import { Button, Space, Tag, message } from 'antd';
import { useNavigate } from 'react-router-dom';

import {
  SensorBatch,
  listSensorBatches,
} from '@/services/sensorBatch';
import { listSensorTypes, SensorType } from '@/services/sensorType';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const STATUS_MAP: Record<number, { text: string; color: string }> = {
  0: { text: '计划中', color: 'default' },
  1: { text: '生产中', color: 'processing' },
  2: { text: '交付中', color: 'warning' },
  3: { text: '已交付', color: 'success' },
};

const MonitoringSensorsPage = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<SensorBatch[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [sensorTypes, setSensorTypes] = useState<SensorType[]>([]);

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listSensorBatches());
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const loadSensorTypes = async () => {
    try {
      setSensorTypes(await listSensorTypes());
    } catch (error) {
      message.error(toErrorMessage(error));
    }
  };

  useEffect(() => {
    loadRows();
    loadSensorTypes();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.code && !norm(row.code).includes(norm(query.code))) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const getSensorTypeName = (id: string) => {
    const found = sensorTypes.find((t) => t.id === id);
    return found ? found.name : id;
  };

  const columns: ProColumns<SensorBatch>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '批次编码',
      dataIndex: 'code',
      width: 180,
      sorter: (a, b) => (a.code || '').localeCompare(b.code || '', 'zh-CN'),
    },
    {
      title: '序列号前缀',
      dataIndex: 'sn',
      width: 120,
      hideInSearch: true,
      render: (_, row) => <Tag>{row.sn}</Tag>,
      sorter: (a, b) => (a.sn || '').localeCompare(b.sn || '', 'zh-CN'),
    },
    {
      title: '数量',
      dataIndex: 'qty',
      width: 80,
      hideInSearch: true,
      render: (_, row) => <Tag color="blue">{row.qty}</Tag>,
      sorter: (a, b) => Number(a.qty) - Number(b.qty),
    },
    {
      title: '传感器型号',
      dataIndex: 'sensor_type_id',
      width: 120,
      hideInSearch: true,
      render: (_, row) => getSensorTypeName(row.sensor_type_id),
      sorter: (a, b) => {
        const labelA = getSensorTypeName(a.sensor_type_id);
        const labelB = getSensorTypeName(b.sensor_type_id);
        return labelA.localeCompare(labelB, 'zh-CN');
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: OPERATION_COL_WIDTH,
      valueType: 'select',
      valueEnum: {
        0: { text: '计划中', status: 'Default' },
        1: { text: '生产中', status: 'Processing' },
        2: { text: '交付中', status: 'Warning' },
        3: { text: '已交付', status: 'Success' },
      },
      render: (_, row) => {
        const info = STATUS_MAP[row.status] || { text: `${row.status}`, color: 'default' };
        return <Tag color={info.color}>{info.text}</Tag>;
      },
      sorter: (a, b) => Number(a.status) - Number(b.status),
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
      sorter: (a, b) => (a.description || '').localeCompare(b.description || '', 'zh-CN'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      valueType: 'dateTime',
      hideInSearch: true,
      sorter: (a, b) => (a.created_at || '').localeCompare(b.created_at || '', 'zh-CN'),
    },
    {
      title: '操作',
      valueType: 'option',
      width: OPERATION_COL_WIDTH,
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="middle">
          <a
            key="devices"
            onClick={() => navigate(`/monitoring/sensors/batch-devices/${row.id}`)}
          >
            设备
          </a>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="传感器">
      <ProTable<SensorBatch>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadRows }}
        optionsRender={renderRefSafeTableOptions}
        cardProps={{ bodyStyle: { paddingInline: 24 } }}
        toolBarRender={false}
      />
    </PageContainer>
  );
};

export default MonitoringSensorsPage;

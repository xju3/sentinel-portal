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
  const [total, setTotal] = useState(0);
  const [current, setCurrent] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [sort, setSort] = useState<Record<string, any>>({});

  const loadRows = async (page: number, size: number, currentSort = sort) => {
    setLoading(true);
    try {
      const skip = (page - 1) * size;
      const res = await listSensorBatches(skip, size, { sort_field: currentSort.field, sort_order: currentSort.order }) as any;
      const items = Array.isArray(res) ? res : res?.items || res?.data || [];
      setRows(items);
      if (res && res.total !== undefined) {
        setTotal(res.total);
      } else if (items.length < size) {
        setTotal(skip + items.length);
      } else {
        setTotal(skip + size + 1);
      }
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows(current, pageSize);
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

  const handleSearch = (values: Record<string, any>) => {
    setQuery(values);
    setCurrent(1);
    loadRows(1, pageSize, sort);
  };

  const handleReset = () => {
    setQuery({});
    setCurrent(1);
    loadRows(1, pageSize, sort);
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
      width: 120,
      sorter: true,
    },
    {
      title: '序列号前缀',
      dataIndex: 'sn',
      width: 120,
      hideInSearch: true,
      render: (_, row) => <Tag>{row.sn}</Tag>,
      sorter: true,
    },
    {
      title: '数量',
      dataIndex: 'qty',
      width: 80,
      hideInSearch: true,
      render: (_, row) => <Tag color="blue">{row.qty}</Tag>,
      sorter: true,
    },
    {
      title: '传感器型号',
      dataIndex: 'sensor_type_id',
      width: 120,
      hideInSearch: true,
      render: (_, row) => row.sensor_type?.name || row.sensor_type_id,
      sorter: true,
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
      sorter: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      width: 120,
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
      sorter: true,
    },
    // {
    //   title: '创建时间',
    //   dataIndex: 'created_at',
    //   width: 180,
    //   valueType: 'dateTime',
    //   hideInSearch: true,
    //   sorter: true,
    // },
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
        onSubmit={handleSearch}
        onReset={handleReset}
        onChange={(pagination, filters, sorter: any) => {
          const currentSort = sorter.order ? { field: sorter.field, order: sorter.order } : {};
          setSort(currentSort);
          const newPage = pagination.current || current;
          const newSize = pagination.pageSize || pageSize;
          setCurrent(newPage);
          setPageSize(newSize);
          loadRows(newPage, newSize, currentSort);
        }}
        options={{ reload: () => loadRows(current, pageSize, sort) }}
        optionsRender={renderRefSafeTableOptions}
        cardProps={{ bodyStyle: { paddingInline: 24 } }}
        toolBarRender={false}
        pagination={{
          current,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (page, size) => {
            setCurrent(page);
            setPageSize(size);
            loadRows(page, size, sort);
          },
        }}
      />
    </PageContainer>
  );
};

export default MonitoringSensorsPage;

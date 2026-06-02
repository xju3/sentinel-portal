import { useEffect, useState } from 'react';
import { PageContainer, ProColumns, ProTable } from '@ant-design/pro-components';
import { Tag, message } from 'antd';
import { useParams, useNavigate } from '@umijs/max';

import { Sensor, listSensorsByBatch } from '@/services/sensorBatch';
import { renderRefSafeTableOptions } from '@/utils/proTableOptions';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const BatchDevicesPage = () => {
  const { batchId } = useParams<{ batchId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<Sensor[]>([]);
  const [total, setTotal] = useState(0);
  const [current, setCurrent] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [querySn, setQuerySn] = useState('');
  const [sort, setSort] = useState<Record<string, any>>({});

  const loadRows = async (page: number, size: number, sn?: string, currentSort = sort) => {
    if (!batchId) return;
    setLoading(true);
    try {
      const skip = (page - 1) * size;
      const sensors = await listSensorsByBatch(batchId, skip, size, { sort_field: currentSort.field, sort_order: currentSort.order });
      setRows(sensors);
      // If the result count is less than pageSize, we know we've reached the end
      // For a more accurate total, we'd need a count endpoint, but this is sufficient
      if (sensors.length < size) {
        setTotal(skip + sensors.length);
      } else {
        setTotal(skip + size + 1); // approximate, allows next page to load
      }
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (batchId) {
      loadRows(current, pageSize, querySn);
    }
  }, [batchId]);

  const handleSearch = (values: Record<string, any>) => {
    const sn = values?.sn || '';
    setQuerySn(sn);
    setCurrent(1);
    loadRows(1, pageSize, sn);
  };

  const handleReset = () => {
    setQuerySn('');
    setCurrent(1);
    loadRows(1, pageSize, '');
  };

  const handleTableChange = (pagination: any) => {
    const { current: page, pageSize: size } = pagination;
    setCurrent(page);
    setPageSize(size);
    loadRows(page, size, querySn);
  };

  const columns: ProColumns<Sensor>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
    },
    {
      title: '传感器SN',
      dataIndex: 'sn',
      width: 180,
      sorter: true,
    },
    {
      title: '设备状态',
      dataIndex: 'active',
      width: 100,
      hideInSearch: true,
      render: (_, row) =>
        row.active === undefined ? '-' : row.active ? <Tag color="green">在线</Tag> : <Tag>离线</Tag>,
      sorter: true,
    },
    {
      title: '最近活跃',
      dataIndex: 'active_at',
      width: 180,
      valueType: 'dateTime',
      hideInSearch: true,
      render: (_, row) => row.active_at || '-',
      sorter: true,
    },
    {
      title: '备注',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
      sorter: true,
    },
  ];

  return (
    <PageContainer
      title="批次设备列表"
      onBack={() => navigate('/monitoring/sensors')}
    >
      <ProTable<Sensor>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rows}
        search={{
          labelWidth: 'auto',
          defaultCollapsed: false,
        }}
        onSubmit={handleSearch}
        onReset={handleReset}
      onChange={(pagination, filters, sorter: any) => {
        const currentSort = sorter.order ? { field: sorter.field, order: sorter.order } : {};
        setSort(currentSort);
        // 分页参数如果有变化这里也能一同接收到，并传入 loadRows
        loadRows(pagination.current || current, pagination.pageSize || pageSize, querySn, currentSort);
      }}
      options={{ reload: () => loadRows(current, pageSize, querySn, sort) }}
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
          loadRows(page, size, querySn, sort);
          },
        }}
      />
    </PageContainer>
  );
};

export default BatchDevicesPage;

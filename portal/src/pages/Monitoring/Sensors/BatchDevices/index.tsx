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

  const loadRows = async (page: number, size: number, sn?: string) => {
    if (!batchId) return;
    setLoading(true);
    try {
      const skip = (page - 1) * size;
      const sensors = await listSensorsByBatch(batchId, skip, size);
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
      sorter: (a, b) => (a.sn || '').localeCompare(b.sn || '', 'zh-CN'),
    },
    {
      title: '设备状态',
      dataIndex: 'active',
      width: 100,
      hideInSearch: true,
      render: (_, row) =>
        row.active === undefined ? '-' : row.active ? <Tag color="green">在线</Tag> : <Tag>离线</Tag>,
      sorter: (a, b) => Number(a.active || 0) - Number(b.active || 0),
    },
    {
      title: '最近活跃',
      dataIndex: 'active_at',
      width: 180,
      valueType: 'dateTime',
      hideInSearch: true,
      render: (_, row) => row.active_at || '-',
      sorter: (a, b) => (a.active_at || '').localeCompare(b.active_at || '', 'zh-CN'),
    },
    {
      title: '备注',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
      sorter: (a, b) => (a.description || '').localeCompare(b.description || '', 'zh-CN'),
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
        options={{ reload: () => loadRows(current, pageSize, querySn) }}
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
            loadRows(page, size, querySn);
          },
        }}
      />
    </PageContainer>
  );
};

export default BatchDevicesPage;

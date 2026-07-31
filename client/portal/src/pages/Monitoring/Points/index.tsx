import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProForm,
  ProFormSelect,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import EntityPicker from '@/components/EntityPicker';
import { Location, queryLocations } from '@/services/location';
import {
  createSensorMonitoring,
  deleteSensorMonitoring,
  listAllSensorMonitorings,
  querySensorMonitoringDeviceInsts,
  SensorMonitoring,
  SensorMonitoringDeviceInstOption,
  SensorMonitoringPayload,
  updateSensorMonitoring,
} from '@/services/sensorMonitoring';
import { querySensors, Sensor } from '@/services/tenantSensor';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
type SensorMonitoringFormValues = {
  device_inst_id: string;
  location_id?: string;
  sensor_id?: string;
  direction?: string;
  status: number;
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

const MonitoringPointsPage = () => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [rows, setRows] = useState<SensorMonitoring[]>([]);
  const [editing, setEditing] = useState<SensorMonitoring | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [sort, setSort] = useState<Record<string, any>>({});

  const loadData = async (currentSort = sort) => {
    setLoading(true);
    try {
      const monitorings = await listAllSensorMonitorings({ sort_field: currentSort.field, sort_order: currentSort.order });
      setRows(monitorings || []);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.device_inst_id) {
        const display = deviceInstMap.get(row.device_inst_id) || row.device_inst_id;
        const hit =
          norm(display).includes(norm(query.device_inst_id)) ||
          norm(row.device_inst_id).includes(norm(query.device_inst_id));
        if (!hit) {
          return false;
        }
      }
      if (query.location_id) {
        const display = row.location_id ? locationMap.get(row.location_id) || row.location_id : '';
        const hit = norm(display).includes(norm(query.location_id));
        if (!hit) {
          return false;
        }
      }
      if (query.sensor_id) {
        const display = row.sensor_id ? sensorMap.get(row.sensor_id) || row.sensor_id : '';
        const hit = norm(display).includes(norm(query.sensor_id));
        if (!hit) {
          return false;
        }
      }
      if (query.direction && !norm(row.direction).includes(norm(query.direction))) {
        return false;
      }
      if (
        query.status !== undefined &&
        query.status !== null &&
        query.status !== '' &&
        String(row.status) !== String(query.status)
      ) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<SensorMonitoring>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '设备实例',
      dataIndex: 'device_inst_id',
      width: 160,
      render: (_, row) => row.device_inst ? [row.device_inst.code, row.device_inst.sn].filter(Boolean).join(' / ') : row.device_inst_id,
      sorter: true,
    },
    {
      title: '测点',
      dataIndex: 'location_id',
      width: 80,
      render: (_, row) => row.location?.name || row.location_id || '-',
      sorter: true,
    },
    {
      title: '传感器',
      dataIndex: 'sensor_id',
      width: 100,
      render: (_, row) => row.sensor?.sn || row.sensor_id || '-',
      sorter: true,
    },

    {
      title: '方向',
      dataIndex: 'direction',
      width: 80,
      valueType: 'select',
      valueEnum: {
        horizontal: { text: '水平' },
        vertical: { text: '垂直' },
        axial: { text: '轴向' },
      },
      render: (_, row) => {
        const map: Record<string, string> = {
          horizontal: '水平',
          vertical: '垂直',
          axial: '轴向',
        };
        return row.direction ? map[row.direction] || row.direction : '-';
      },
      sorter: true,
    },
    // {
    //   title: '故障类型',
    //   dataIndex: 'anomaly',
    //   width: 100,
    //   hideInSearch: true,
    //   render: (_, row) => {
    //     const map: Record<number, string> = {
    //       0: '-',
    //       1: '振动',
    //       2: '温度',
    //       3: '振动+温度',
    //     };
    //     return map[Number(row.anomaly)] || '正常';
    //   },
    //   sorter: true,
    // },
    // {
    //   title: '故障时间',
    //   dataIndex: 'ts',
    //   width: 150,
    //   hideInSearch: true,
    //   render: (_: any, row: any) => {
    //     if (!row.ts) return '-';
    //     const d = new Date(Number(row.ts));
    //     return d.toLocaleString('zh-CN', { hour12: false });
    //   },
    //   sorter: true,
    // },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      valueType: 'select',
      valueEnum: {
        1: { text: '启用' },
        0: { text: '停用' },
      },
      render: (_, row) => (Number(row.status) === 1 ? '启用' : '停用'),
      sorter: true,
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
            key="edit"
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            key="delete"
            title="确认删除该测点绑定吗？"
            onConfirm={async () => {
              try {
                await deleteSensorMonitoring(row.id);
                message.success('删除成功');
                await loadData();
              } catch (error) {
                message.error(toErrorMessage(error));
              }
            }}
          >
            <a style={{ color: '#ff4d4f' }}>
              删除
            </a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="测点设置">
      <ProTable<SensorMonitoring>
        rowKey="id"
        loading={loading}
        columns={columns}
        scroll={{ x: 'max-content' }}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        onChange={(pagination, filters, sorter: any) => {
          const currentSort = sorter.order ? { field: sorter.field, order: sorter.order } : {};
          setSort(currentSort);
          loadData(currentSort);
        }}
        options={{ reload: loadData }}
        optionsRender={renderRefSafeTableOptions}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            新建绑定
          </Button>,
        ]}
      />

      <ModalForm<SensorMonitoringFormValues>
        title={editing ? '编辑测点绑定' : '新建测点绑定'}
        open={modalOpen}
        initialValues={
          editing
            ? {
              device_inst_id: editing.device_inst_id,
              location_id: editing.location_id || undefined,
              sensor_id: editing.sensor_id || undefined,
              direction: editing.direction || undefined,
              status: Number(editing.status),
            }
            : {
              status: 1,
            }
        }
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setModalOpen(false);
            setEditing(null);
          },
        }}
        submitter={{
          submitButtonProps: { loading: saving },
          searchConfig: { submitText: '保存' },
        }}
        onFinish={async (values) => {
          const payload: SensorMonitoringPayload = {
            device_inst_id: values.device_inst_id,
            location_id: values.location_id || null,
            sensor_id: values.sensor_id || null,
            direction: values.direction || null,
            status: Number(values.status ?? 1),
          };

          setSaving(true);
          try {
            if (editing) {
              await updateSensorMonitoring(editing.id, payload);
            } else {
              await createSensorMonitoring(payload);
            }
            message.success('保存成功');
            setModalOpen(false);
            setEditing(null);
            await loadData();
            return true;
          } catch (error) {
            message.error(toErrorMessage(error));
            return false;
          } finally {
            setSaving(false);
          }
        }}
      >
        <ProForm.Item
          name="device_inst_id"
          label="设备实例"
          rules={[{ required: true, message: '请选择设备实例' }]}
        >
          <EntityPicker<SensorMonitoringDeviceInstOption>
            modalTitle="选择设备实例"
            triggerText="选择设备"
            placeholder="请选择设备实例"
            valueLabel={
              editing?.device_inst
                ? [editing.device_inst.code, editing.device_inst.sn].filter(Boolean).join(' / ')
                : editing?.device_inst_id
            }
            fetcher={async ({ current, pageSize, keyword }) => {
              const result = await querySensorMonitoringDeviceInsts(current, pageSize, keyword);
              return { items: result.items, total: result.total };
            }}
            columns={[
              { title: '编码', dataIndex: 'code', width: 160 },
              { title: '序列号', dataIndex: 'sn', width: 160 },
            ]}
            getRecordLabel={(row) => [row.code, row.sn].filter(Boolean).join(' / ')}
          />
        </ProForm.Item>
        <ProForm.Item
          name="location_id"
          label="故障测点"
        >
          <EntityPicker<Location>
            modalTitle="选择故障测点"
            triggerText="选择测点"
            placeholder="请选择故障测点"
            valueLabel={
              editing?.location?.name || editing?.location_id
            }
            fetcher={async ({ current, pageSize, keyword }) => {
              const result = await queryLocations(current, pageSize, keyword);
              return { items: result.items, total: result.total };
            }}
            columns={[
              { title: '名称', dataIndex: 'name', width: 200 },
            ]}
            getRecordLabel={(row) => row.name}
          />
        </ProForm.Item>
        <ProForm.Item
          name="sensor_id"
          label="传感器"
        >
          <EntityPicker<Sensor>
            modalTitle="选择传感器"
            triggerText="选择传感器"
            placeholder="请选择传感器"
            valueLabel={
              editing?.sensor?.sn || editing?.sensor_id
            }
            fetcher={async ({ current, pageSize, keyword }) => {
              const result = await querySensors(current, pageSize, keyword);
              return { items: result.items, total: result.total };
            }}
            columns={[
              { title: '序列号', dataIndex: 'sn', width: 200 },
            ]}
            getRecordLabel={(row) => row.sn}
          />
        </ProForm.Item>
        <ProFormSelect
          name="direction"
          label="方向"
          options={[
            { label: '水平', value: 'horizontal' },
            { label: '垂直', value: 'vertical' },
            { label: '轴向', value: 'axial' },
          ]}
        />
        <ProFormSelect
          name="status"
          label="状态"
          options={[
            { label: '启用', value: 1 },
            { label: '停用', value: 0 },
          ]}
          rules={[{ required: true, message: '请选择状态' }]}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default MonitoringPointsPage;

import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSelect,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, message } from 'antd';

import { listAllLocations, Location } from '@/services/location';
import {
  createSensorMonitoring,
  deleteSensorMonitoring,
  listAllSensorMonitorings,
  listSensorMonitoringDeviceInstOptions,
  SensorMonitoring,
  SensorMonitoringDeviceInstOption,
  SensorMonitoringPayload,
  updateSensorMonitoring,
} from '@/services/sensorMonitoring';
import { listAllSensors, listAllTenantSensors, Sensor, TenantSensor } from '@/services/tenantSensor';

import { renderRefSafeTableOptions } from '@/utils/proTableOptions';
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

  const [deviceInstOptions, setDeviceInstOptions] = useState<SensorMonitoringDeviceInstOption[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [sensors, setSensors] = useState<Sensor[]>([]);

  const deviceInstMap = useMemo(
    () => new Map(deviceInstOptions.map((item) => [item.id, `${item.code} / ${item.sn}`])),
    [deviceInstOptions],
  );
  const locationMap = useMemo(() => new Map(locations.map((item) => [item.id, item.name])), [locations]);
  const sensorMap = useMemo(() => new Map(sensors.map((item) => [item.id, item.sn])), [sensors]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [monitorings, instOptions, locationRows, tenantSensors, sensorRows] = await Promise.all([
        listAllSensorMonitorings(),
        listSensorMonitoringDeviceInstOptions(),
        listAllLocations(),
        listAllTenantSensors(),
        listAllSensors(),
      ]);
      const ownedSensorIds = new Set((tenantSensors || []).map((item: TenantSensor) => item.sensor_id));
      setRows(monitorings || []);
      setDeviceInstOptions(instOptions || []);
      setLocations(locationRows || []);
      setSensors((sensorRows || []).filter((item) => ownedSensorIds.has(item.id)));
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
  }, [deviceInstMap, locationMap, query, rows, sensorMap]);

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
      width: 220,
      render: (_, row) => deviceInstMap.get(row.device_inst_id) || row.device_inst_id,
    },
    {
      title: '故障测点',
      dataIndex: 'location_id',
      width: 180,
      render: (_, row) => (row.location_id ? locationMap.get(row.location_id) || row.location_id : '-'),
    },
    {
      title: '传感器',
      dataIndex: 'sensor_id',
      width: 180,
      render: (_, row) => (row.sensor_id ? sensorMap.get(row.sensor_id) || row.sensor_id : '-'),
    },
    {
      title: '方向',
      dataIndex: 'direction',
      width: 120,
      valueType: 'select',
      valueEnum: {
        horizontal: { text: '水平' },
        vertical: { text: '垂直' },
        axial: { text: '轴向' },
      },
      render: (_, row) => row.direction || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        1: { text: '启用' },
        0: { text: '停用' },
      },
      render: (_, row) => (Number(row.status) === 1 ? '启用' : '停用'),
    },
    {
      title: '操作',
      valueType: 'option',
      width: 180,
      render: (_, row) => [
        <Button
          key="edit"
          type="link"
          onClick={() => {
            setEditing(row);
            setModalOpen(true);
          }}
        >
          编辑
        </Button>,
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
          <Button danger type="link">
            删除
          </Button>
        </Popconfirm>,
      ],
    },
  ];

  return (
    <PageContainer title="测点设置">
      <ProTable<SensorMonitoring>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
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
        <ProFormSelect
          name="device_inst_id"
          label="设备实例"
          options={deviceInstOptions.map((item) => ({
            label: `${item.code} / ${item.sn}`,
            value: item.id,
          }))}
          rules={[{ required: true, message: '请选择设备实例' }]}
        />
        <ProFormSelect
          name="location_id"
          label="故障测点"
          options={locations.map((item) => ({
            label: item.name,
            value: item.id,
          }))}
        />
        <ProFormSelect
          name="sensor_id"
          label="传感器"
          options={sensors.map((item) => ({
            label: item.sn,
            value: item.id,
          }))}
        />
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

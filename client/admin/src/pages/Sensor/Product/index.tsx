import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Switch, message } from 'antd';

import {
  Sensor,
  SensorPayload,
  createSensor,
  deleteSensor,
  listSensors,
  updateSensor,
} from '@/services/sensor';
import { getSimCards } from '@/services/simCard';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const SensorProductPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<Sensor[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<Sensor | null>(null);

  const loadRows = async () => {
    setLoading(true);
    try {
      const result = await listSensors();
      setRows(result.items);
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
      if (query.sn && !norm(row.sn).includes(norm(query.sn))) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<Sensor>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '序列号',
      dataIndex: 'sn',
      width: 120,
    },
    {
      title: 'SIM卡',
      dataIndex: 'sim_id',
      hideInSearch: true,
      width: 260,
      render: (_, row) => row.sim_card ? `${row.sim_card.iccid} (${row.sim_card.carrier})` : (row.sim_id || '-'),
    },
    {
      title: '状态',
      dataIndex: 'active',
      width: 100,
      valueType: 'select',
      valueEnum: {
        true: { text: '在线', status: 'Success' },
        false: { text: '离线', status: 'Default' },
      },
      render: (_, row) => (
        <Switch
          checked={row.active}
          checkedChildren="在线"
          unCheckedChildren="离线"
          onChange={async (checked) => {
            try {
              await updateSensor(row.id, { active: checked });
              message.success('更新成功');
              await loadRows();
            } catch (error) {
              message.error(toErrorMessage(error));
            }
          }}
        />
      ),
    },

    {
      title: '激活时间',
      dataIndex: 'active_at',
      width: 180,
      valueType: 'dateTime',
      hideInSearch: true,
    },
    {
      title: '最新状态',
      dataIndex: 'latest_status',
      hideInSearch: true,
      render: (_, row) => {
        if (!row.latest_status) return '-';
        const { temperature, battery, rssi, ts } = row.latest_status;
        return (
          <div style={{ display: 'flex', flexDirection: 'column', fontSize: '12px', lineHeight: '18px' }}>
            <span>电量: {battery != null ? `${battery}%` : '-'} | 温度: {temperature != null ? `${temperature}℃` : '-'}</span>
            <span>RSSI: {rssi != null ? `${rssi}dBm` : '-'}</span>
            <span style={{ color: '#888' }}>更新于: {ts ? new Date(ts).toLocaleString() : '-'}</span>
          </div>
        );
      },
    },
    {
      title: '描述',
      width: 120,
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    // {
    //   title: '创建时间',
    //   dataIndex: 'created_at',
    //   width: 180,
    //   valueType: 'dateTime',
    //   hideInSearch: true,
    // },
    {
      title: '操作',
      valueType: 'option',
      // fixed: 'right',
      width: 160,
      render: (_, row) => [
        <a
          key="edit"
          onClick={() => {
            setEditing(row);
            setModalOpen(true);
          }}
        >
          编辑
        </a>,
        <Popconfirm
          key="delete"
          title="确认删除该传感器吗？"
          onConfirm={async () => {
            try {
              await deleteSensor(row.id);
              message.success('删除成功');
              await loadRows();
            } catch (error) {
              message.error(toErrorMessage(error));
            }
          }}
        >
          <a style={{ color: 'red' }}>
            删除
          </a>
        </Popconfirm>,
      ],
    },
  ];

  return (
    <PageContainer
      title="传感器产品管理"
      subTitle="管理所有传感器产品"
    >
      <ProTable<Sensor>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadRows }}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            新建传感器
          </Button>,
        ]}
      />

      <ModalForm<SensorPayload>
        title={editing ? '编辑传感器' : '新建传感器'}
        open={modalOpen}
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
        initialValues={
          editing
            ? {
              sn: editing.sn,
              description: editing.description,
              active: editing.active,
              sensor_type_id: editing.sensor_type_id,
              sim_id: editing.sim_id,
            }
            : { active: true }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: SensorPayload = {
              sn: values.sn.trim(),
              description: values.description?.trim(),
              active: values.active,
              sensor_type_id: values.sensor_type_id,
              sim_id: values.sim_id || null,
            };

            if (editing) {
              await updateSensor(editing.id, payload);
              message.success('更新成功');
            } else {
              await createSensor(payload);
              message.success('创建成功');
            }
            setModalOpen(false);
            setEditing(null);
            await loadRows();
            return true;
          } catch (error) {
            message.error(toErrorMessage(error));
            return false;
          } finally {
            setSaving(false);
          }
        }}
      >
        <ProFormText
          name="sn"
          label="序列号"
          rules={[
            { required: true, message: '请输入传感器序列号' },
            { max: 255, message: '序列号最多255个字符' },
          ]}
        />

        <ProFormSelect
          name="sim_id"
          label="绑定 SIM 卡"
          showSearch
          allowClear
          placeholder="请选择要绑定的 SIM 卡（可选）"
          request={async () => {
            try {
              // 请求接口：只显示 status=1 (正常) 且 unbound_only=true (尚未分配) 的 SIM 卡
              const res = await getSimCards({ pageSize: 1000, status: 1, unbound_only: true });
              const options = (res?.list || []).map((item: any) => ({
                label: `${item.iccid} (${item.carrier})`,
                value: item.id,
              }));

              // 如果当前正在编辑，且该传感器已经绑定了 SIM 卡，将该卡补充进下拉列表防止只显示 UUID
              if (editing?.sim_card) {
                const currentSim = editing.sim_card;
                if (!options.find((opt: any) => opt.value === currentSim.id)) {
                  options.unshift({
                    label: `${currentSim.iccid} (${currentSim.carrier}) - 当前绑定`,
                    value: currentSim.id,
                  });
                }
              }
              return options;
            } catch (e) {
              return [];
            }
          }}
        />

        <ProFormSelect
          name="active"
          label="状态"
          options={[
            { label: '在线', value: true },
            { label: '离线', value: false },
          ]}
          rules={[{ required: true, message: '请选择状态' }]}
        />
        <ProFormTextArea
          name="description"
          label="描述"
        />
      </ModalForm>
    </PageContainer>
  );
};

export default SensorProductPage;

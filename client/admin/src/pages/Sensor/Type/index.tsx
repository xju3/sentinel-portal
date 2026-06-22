import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Switch, Tag, message } from 'antd';

import {
  SensorType,
  SensorTypePayload,
  createSensorType,
  deleteSensorType,
  listSensorTypes,
  updateSensorType,
} from '@/services/sensorType';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const SensorTypePage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<SensorType[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<SensorType | null>(null);

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listSensorTypes());
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
      if (query.name && !norm(row.name).includes(norm(query.name))) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<SensorType>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 160,
    },
    {
      title: '电池容量',
      dataIndex: 'battery',
      width: 100,
      hideInSearch: true,
      render: (_, row) => `${row.battery}`,
    },
    {
      title: '网络类型',
      dataIndex: 'network',
      width: 100,
      hideInSearch: true,
      render: (_, row) => {
        const map: Record<number, { text: string; color: string }> = {
          1: { text: '4G', color: 'blue' },
          2: { text: 'WiFi', color: 'green' },
        };
        const info = map[row.network] || { text: `${row.network}`, color: 'default' };
        return <Tag color={info.color}>{info.text}</Tag>;
      },
    },
    {
      title: '蓝牙',
      dataIndex: 'bluetooth',
      width: 80,
      hideInSearch: true,
      render: (_, row) =>
        row.bluetooth ? <Tag color="blue">支持</Tag> : <Tag>不支持</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
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
          title="确认删除该传感器型号吗？"
          onConfirm={async () => {
            try {
              await deleteSensorType(row.id);
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
      title="传感器型号管理"
      subTitle="管理所有传感器型号规格"
    >
      <ProTable<SensorType>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        scroll={{ x: 900 }}
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
            新建型号
          </Button>,
        ]}
      />

      <ModalForm<SensorTypePayload>
        title={editing ? '编辑传感器型号' : '新建传感器型号'}
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
                name: editing.name,
                battery: editing.battery,
                network: editing.network,
                bluetooth: editing.bluetooth,
                description: editing.description,
              }
            : {
                battery: 0,
                network: 1,
                bluetooth: false,
              }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: SensorTypePayload = {
              name: values.name.trim(),
              battery: Number(values.battery ?? 0),
              network: Number(values.network ?? 1),
              bluetooth: values.bluetooth ?? false,
              description: values.description?.trim(),
            };

            if (editing) {
              await updateSensorType(editing.id, payload);
              message.success('更新成功');
            } else {
              await createSensorType(payload);
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
          name="name"
          label="名称"
          rules={[
            { required: true, message: '请输入传感器型号名称' },
            { max: 100, message: '名称最多100个字符' },
          ]}
        />
        <ProFormDigit
          name="battery"
          label="电池容量"
          min={0}
          fieldProps={{ precision: 0 }}
        />
        <ProFormSelect
          name="network"
          label="网络类型"
          options={[
            { label: '4G', value: 1 },
            { label: 'WiFi', value: 2 },
          ]}
          rules={[{ required: true, message: '请选择网络类型' }]}
        />
        <ProFormSwitch name="bluetooth" label="蓝牙支持" />
        <ProFormTextArea
          name="description"
          label="描述"
        />
      </ModalForm>
    </PageContainer>
  );
};

export default SensorTypePage;

import { useRef, useState } from 'react';
import {
  ActionType,
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, message } from 'antd';

import { listSensors } from '@/services/sensor';
import {
  SensorTask,
  SensorTaskPayload,
  createSensorTask,
  listSensorTasks,
} from '@/services/sensorTask';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const statusValueEnum = {
  0: { text: '待下发', status: 'Default' },
  2: { text: '执行中', status: 'Processing' },
  1: { text: '已完成', status: 'Success' },
};

const SensorTaskPage = () => {
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const columns: ProColumns<SensorTask>[] = [
    {
      title: '任务名称 / 传感器',
      dataIndex: 'keyword',
      hideInTable: true,
    },
    {
      title: '任务名称',
      dataIndex: 'name',
      hideInSearch: true,
      width: 180,
    },
    {
      title: '传感器 SN',
      dataIndex: 'sn',
      hideInSearch: true,
      width: 180,
    },
    {
      title: '动作编码',
      dataIndex: 'action',
      hideInSearch: true,
      width: 100,
    },
    {
      title: '执行次数',
      dataIndex: 'val',
      hideInSearch: true,
      width: 100,
    },
    {
      title: '状态',
      dataIndex: 'status',
      valueType: 'select',
      valueEnum: statusValueEnum,
      width: 100,
    },
    {
      title: '任务说明',
      dataIndex: 'remark',
      hideInSearch: true,
      ellipsis: true,
      render: (_, row) => row.remark || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'create_time',
      valueType: 'dateTime',
      hideInSearch: true,
      width: 180,
    },
    {
      title: '下发时间',
      dataIndex: 'dispatched_at',
      valueType: 'dateTime',
      hideInSearch: true,
      width: 180,
      render: (_, row) => row.dispatched_at || '-',
    },
    {
      title: '完成时间',
      dataIndex: 'complete_time',
      valueType: 'dateTime',
      hideInSearch: true,
      width: 180,
      render: (_, row) => row.complete_time || '-',
    },
  ];

  return (
    <PageContainer title="传感器任务" subTitle="查看任务状态并手动创建待下发任务">
      <ProTable<SensorTask>
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        scroll={{ x: 1300 }}
        search={{ labelWidth: 'auto' }}
        request={async (params) => {
          try {
            const result = await listSensorTasks({
              current: params.current,
              pageSize: params.pageSize,
              keyword: params.keyword,
              status: params.status === undefined ? undefined : Number(params.status),
            });
            return { data: result.items, total: result.total, success: true };
          } catch (error) {
            message.error(toErrorMessage(error));
            return { data: [], total: 0, success: false };
          }
        }}
        toolBarRender={() => [
          <Button key="create" type="primary" onClick={() => setModalOpen(true)}>
            新建任务
          </Button>,
        ]}
      />

      <ModalForm<SensorTaskPayload>
        title="新建传感器任务"
        open={modalOpen}
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => setModalOpen(false),
        }}
        submitter={{
          submitButtonProps: { loading: saving },
          searchConfig: { submitText: '创建任务' },
        }}
        onFinish={async (values) => {
          setSaving(true);
          try {
            await createSensorTask({
              ...values,
              name: values.name.trim(),
              remark: values.remark?.trim() || undefined,
            });
            message.success('任务创建成功');
            setModalOpen(false);
            actionRef.current?.reload();
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
          name="sensor_id"
          label="传感器"
          showSearch
          debounceTime={300}
          placeholder="输入 SN 搜索并选择传感器"
          request={async ({ keyWords }) => {
            const result = await listSensors(1, 100, keyWords);
            return result.items.map((sensor) => ({
              label: sensor.description ? `${sensor.sn} - ${sensor.description}` : sensor.sn,
              value: sensor.id,
            }));
          }}
          rules={[{ required: true, message: '请选择传感器' }]}
        />
        <ProFormText
          name="name"
          label="任务名称"
          rules={[
            { required: true, whitespace: true, message: '请输入任务名称' },
            { max: 255, message: '任务名称最多 255 个字符' },
          ]}
        />
        <ProFormDigit
          name="action"
          label="动作编码"
          fieldProps={{ precision: 0, min: 0, max: 9999 }}
          extra="0=固件升级，1=配置更新，3=状态上报；11..99、1000..9999 为采集任务编码"
          rules={[
            { required: true, message: '请输入动作编码' },
            {
              validator: async (_, value) => {
                const valid = value === 0 || value === 1 || value === 3
                  || (value >= 11 && value <= 99)
                  || (value >= 1000 && value <= 9999);
                if (!valid) {
                  throw new Error('动作编码必须为 0、1、3、11..99 或 1000..9999');
                }
              },
            },
          ]}
        />
        <ProFormDigit
          name="val"
          label="执行次数"
          initialValue={1}
          fieldProps={{ precision: 0, min: 0, max: 32767 }}
          extra="系统任务可填 0；采集任务必须至少执行 1 次"
          rules={[{ required: true, message: '请输入执行次数' }]}
        />
        <ProFormTextArea name="remark" label="任务说明" />
      </ModalForm>
    </PageContainer>
  );
};

export default SensorTaskPage;

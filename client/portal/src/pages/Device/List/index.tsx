import { useRef, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProForm,
  ProFormDatePicker,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import type { ActionType } from '@ant-design/pro-components';
import { Button, Popconfirm, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { type Dayjs } from 'dayjs';
import { useNavigate } from 'react-router-dom';

import EntityPicker from '@/components/EntityPicker';
import {
  createDeviceInst,
  deleteDeviceInst,
  DeviceInst,
  DeviceInstPayload,
  updateDeviceInst,
} from '@/services/deviceInst';
import { DeviceSpec, queryDeviceSpecs } from '@/services/deviceSpec';
import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
import { requestPagedList } from '@/utils/proTableRequest';

type DeviceInstFormValues = {
  name: string;
  device_spec_id: string;
  code: string;
  purchase_date?: string | Dayjs;
  life_span: number;
  desc?: string;
  status: number;
  active: number;
  available: number;
};

type DeviceInstRecord = DeviceInst & {
  sensor_monitorings?: Array<{
    id?: string;
    location?: { name?: string };
    sensor?: { sn?: string };
  }>;
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

const toApiDate = (value?: string | Dayjs): string | null => {
  if (!value) {
    return null;
  }
  if (typeof value === 'string') {
    return value.trim() || null;
  }
  return value.format('YYYY-MM-DD');
};

const DeviceListPage = () => {
  const actionRef = useRef<ActionType>();
  const navigate = useNavigate();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<DeviceInstRecord | null>(null);
  const [copyMode, setCopyMode] = useState(false);

  const specPickerColumns: ColumnsType<DeviceSpec> = [
    { title: '名称', dataIndex: 'name' },
    { title: '型号', dataIndex: 'model' },
    { title: '品牌', dataIndex: 'brand' },
    { title: '电压(V)', dataIndex: 'voltage' },
    { title: '转速(RPM)', dataIndex: 'rpm' },
  ];

  const columns: ProColumns<DeviceInstRecord>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '编号',
      dataIndex: 'code',
      width: 180,
      sorter: true,
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 120,
      ellipsis: true,
      sorter: true,
    },
    {
      title: '设备规格',
      dataIndex: 'device_spec_id',
      width: 160,
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => {
        const spec = row.device_spec;
        return spec ? `${spec.name} / ${spec.model}${spec.brand ? ` / ${spec.brand}` : ''}` : '-';
      },
    },
    {
      title: '服役日期',
      dataIndex: 'purchase_date',
      width: 100,
      align: 'center',
      valueType: 'date',
      hideInSearch: true,
      sorter: true,
    },
    {
      title: '年限(月)',
      dataIndex: 'life_span',
      width: 100,
      align: 'center',
      valueType: 'digit',
      hideInSearch: true,
      sorter: true,
    },
    {
      title: '测点',
      hideInSearch: true,
      render: (_, row) => {
        const monitorings = row.sensor_monitorings || [];
        if (!monitorings.length) {
          return '-';
        }
        return (
          <Space size={[0, 2]} wrap>
            {monitorings.map((monitoring, index) => {
              const sn = monitoring.sensor?.sn || '未知SN';
              const locationName = monitoring.location?.name || '未知测点';
              return (
                <Tag
                  color="blue"
                  key={monitoring.id || index}
                  style={{ cursor: sn !== '未知SN' ? 'pointer' : 'default' }}
                  onClick={() => {
                    if (sn !== '未知SN') {
                      navigate(
                        `/monitoring/sensors/${sn}/history?location=${encodeURIComponent(locationName)}`,
                      );
                    }
                  }}
                >
                  {locationName}
                </Tag>
              );
            })}
          </Space>
        );
      },
    },
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
      title: '描述',
      dataIndex: 'desc',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.desc || '-',
    },
    {
      title: '操作',
      valueType: 'option',
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="small">
          <a key="health-archive" onClick={() => navigate(`/device/${row.id}/health-archive`)}>
            档案
          </a>
          <a
            key="edit"
            onClick={() => {
              setEditing(row);
              setCopyMode(false);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <a
            key="copy"
            onClick={() => {
              setEditing(row);
              setCopyMode(true);
              setModalOpen(true);
            }}
          >
            复制
          </a>
          <Popconfirm
            key="delete"
            title="确认删除该设备实例吗？"
            onConfirm={async () => {
              try {
                await deleteDeviceInst(row.id);
                message.success('删除成功');
                actionRef.current?.reload();
              } catch (error) {
                message.error(toErrorMessage(error));
              }
            }}
          >
            <a style={{ color: '#ff4d4f' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="设备列表">
      <ProTable<DeviceInstRecord>
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        request={(params, sort) =>
          requestPagedList<DeviceInstRecord>('/api/v1/device-insts', {
            params,
            sort: sort as any,
            defaultPageSize: 20,
          })
        }
        search={{ labelWidth: 'auto' }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        options={{ reload: () => actionRef.current?.reload() }}
        optionsRender={renderRefSafeTableOptions}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditing(null);
              setCopyMode(false);
              setModalOpen(true);
            }}
          >
            新建设备实例
          </Button>,
        ]}
      />

      <ModalForm<DeviceInstFormValues>
        title={copyMode ? '复制设备实例' : editing ? '编辑设备实例' : '新建设备实例'}
        open={modalOpen}
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setModalOpen(false);
            setEditing(null);
            setCopyMode(false);
          },
        }}
        submitter={{
          submitButtonProps: { loading: saving },
          searchConfig: { submitText: '保存' },
        }}
        initialValues={
          editing && !copyMode
            ? {
                name: editing.name,
                device_spec_id: editing.device_spec_id,
                code: editing.code,
                purchase_date: editing.purchase_date ? dayjs(editing.purchase_date) : undefined,
                life_span: editing.life_span,
                desc: editing.desc || undefined,
                status: Number(editing.status),
                active: Number(editing.active),
                available: Number(editing.available),
              }
            : editing && copyMode
              ? {
                  name: '',
                  device_spec_id: editing.device_spec_id,
                  code: editing.code,
                  purchase_date: editing.purchase_date ? dayjs(editing.purchase_date) : undefined,
                  life_span: editing.life_span,
                  desc: editing.desc || undefined,
                  status: Number(editing.status),
                  active: Number(editing.active),
                  available: Number(editing.available),
                }
              : {
                  life_span: 0,
                  status: 1,
                  active: 1,
                  available: 1,
                }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: DeviceInstPayload = {
              name: values.name.trim(),
              device_spec_id: values.device_spec_id,
              code: values.code.trim(),
              purchase_date: toApiDate(values.purchase_date),
              life_span: Number(values.life_span ?? 0),
              desc: values.desc?.trim() || null,
              status: Number(values.status ?? 1),
              active: Number(values.active ?? 1),
              available: Number(values.available ?? 1),
            };

            if (editing && !copyMode) {
              await updateDeviceInst(editing.id, payload);
              message.success('更新成功');
            } else {
              await createDeviceInst(payload);
              message.success('创建成功');
            }
            setModalOpen(false);
            setEditing(null);
            setCopyMode(false);
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
        <ProFormText
          name="code"
          label="编号"
          rules={[
            { required: true, message: '请输入设备编号' },
            { max: 36, message: '设备编号最多36个字符' },
          ]}
        />
        <ProFormText
          name="name"
          label="名称"
          rules={[
            { required: true, message: '请输入设备名称' },
            { max: 128, message: '设备名称最多128个字符' },
          ]}
        />
        <ProForm.Item
          name="device_spec_id"
          label="设备规格"
          rules={[{ required: true, message: '请选择设备规格' }]}
        >
          <EntityPicker<DeviceSpec>
            modalTitle="选择设备规格"
            triggerText="选择规格"
            placeholder="请选择设备规格"
            valueLabel={
              editing?.device_spec
                ? `${editing.device_spec.name} / ${editing.device_spec.model}${
                    editing.device_spec.brand ? ` / ${editing.device_spec.brand}` : ''
                  }`
                : undefined
            }
            fetcher={async (query) => {
              const result = await queryDeviceSpecs(query);
              return {
                items: result.items || result.data,
                total: result.total,
              };
            }}
            columns={specPickerColumns}
            getRecordLabel={(row) => `${row.name} / ${row.model} / ${row.brand}`}
          />
        </ProForm.Item>
        <ProFormDatePicker
          name="purchase_date"
          label="服役日期"
          fieldProps={{ format: 'YYYY-MM-DD' }}
        />
        <ProFormDigit
          name="life_span"
          label="可用年限(月)"
          min={0}
          fieldProps={{ precision: 0 }}
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
        <ProFormText
          name="desc"
          label="描述"
          rules={[{ max: 128, message: '描述最多128个字符' }]}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default DeviceListPage;

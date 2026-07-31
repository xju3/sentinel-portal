import { useEffect, useMemo, useState } from 'react';
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
import { Button, Popconfirm, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from '@umijs/max';
import dayjs, { type Dayjs } from 'dayjs';

import EntityPicker from '@/components/EntityPicker';
import {
  createDeviceInst,
  deleteDeviceInst,
  DeviceInst,
  DeviceInstPayload,
  listAllDeviceInsts,
  updateDeviceInst,
} from '@/services/deviceInst';
import { DeviceSpec, queryDeviceSpecs } from '@/services/deviceSpec';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
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

type DeviceSort = {
  field?: string;
  order?: 'ascend' | 'descend';
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
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<DeviceInst[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [sort, setSort] = useState<DeviceSort>({});
  const [editing, setEditing] = useState<DeviceInst | null>(null);
  const [copyMode, setCopyMode] = useState(false);

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listAllDeviceInsts());
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
    const purchaseDateQuery =
      query.purchase_date === undefined || query.purchase_date === null || query.purchase_date === ''
        ? ''
        : dayjs.isDayjs(query.purchase_date)
          ? query.purchase_date.format('YYYY-MM-DD').toLowerCase()
          : norm(query.purchase_date);
    return rows.filter((row) => {
      if (query.code && !norm(row.name).includes(norm(query.code))) {
        return false;
      }
      if (query.sn && !norm(row.code).includes(norm(query.sn))) {
        return false;
      }
      if (purchaseDateQuery && !norm(row.purchase_date).includes(purchaseDateQuery)) {
        return false;
      }
      if (query.desc && !norm(row.desc).includes(norm(query.desc))) {
        return false;
      }
      if (
        query.life_span !== undefined &&
        query.life_span !== null &&
        String(row.life_span) !== String(query.life_span)
      ) {
        return false;
      }
      if (
        query.status !== undefined &&
        query.status !== null &&
        String(row.status) !== String(query.status)
      ) {
        return false;
      }
      if (query.device_spec_id) {
        const spec = row.device_spec;
        const specText = spec ? `${spec.name} / ${spec.model}${spec.brand ? ` / ${spec.brand}` : ''}` : '';
        const hit =
          norm(specText).includes(norm(query.device_spec_id)) ||
          norm(row.device_spec_id).includes(norm(query.device_spec_id));
        if (!hit) {
          return false;
        }
      }
      return true;
    });
  }, [query, rows]);

  const displayedRows = useMemo(() => {
    if (!sort.field || !sort.order) {
      return filteredRows;
    }

    const direction = sort.order === 'ascend' ? 1 : -1;
    const valueOf = (row: DeviceInst): unknown => {
      if (sort.field === 'device_spec_id') {
        const spec = row.device_spec;
        return spec ? `${spec.name} ${spec.model} ${spec.brand}` : '';
      }
      return row[sort.field as keyof DeviceInst];
    };

    return [...filteredRows].sort((left, right) => {
      const leftValue = valueOf(left);
      const rightValue = valueOf(right);
      if (leftValue == null && rightValue == null) return 0;
      if (leftValue == null) return 1;
      if (rightValue == null) return -1;
      if (typeof leftValue === 'number' && typeof rightValue === 'number') {
        return (leftValue - rightValue) * direction;
      }
      return (
        String(leftValue).localeCompare(String(rightValue), 'zh-CN', {
          numeric: true,
          sensitivity: 'base',
        }) * direction
      );
    });
  }, [filteredRows, sort]);

  const specPickerColumns: ColumnsType<DeviceSpec> = [
    { title: '名称', dataIndex: 'name' },
    { title: '型号', dataIndex: 'model' },
    { title: '品牌', dataIndex: 'brand' },
    {
      title: '电压(V)',
      dataIndex: 'voltage',
    },
    {
      title: '转速(RPM)',
      dataIndex: 'rpm',
    },
  ];

  const columns: ProColumns<DeviceInst>[] = [
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
      width: 140,
      sorter: true,
    },
    {
      title: '设备规格',
      dataIndex: 'device_spec_id',
      width: 180,
      ellipsis: true,
      render: (_, row: any) => {
        const spec = row.device_spec;
        return spec ? `${spec.name} / ${spec.model}${spec.brand ? ` / ${spec.brand}` : ''}` : '-';
      },
      sorter: true,
    },
    {
      title: '服役日期',
      dataIndex: 'purchase_date',
      width: 100,
      align: 'center',
      valueType: 'date',
      sorter: true,
    },
    {
      title: '年限',
      dataIndex: 'life_span',
      width: 80,
      align: 'center',
      valueType: 'digit',
      sorter: true,
    },
    {
      title: '测点',
      hideInSearch: true,
      width: 120,
      render: (_, row: any) => {
        const monitorings = row.sensor_monitorings || [];
        if (!monitorings?.length) return '-';
        return (
          <Space size={[0, 2]} wrap>
            {monitorings.map((m: any, idx: number) => {
              const sn = m.sensor?.sn || '未知SN';
              const loc = m.location?.name || '未知测点';
              return (
                <Tag
                  color="blue"
                  key={m.id || idx}
                  style={{ cursor: sn !== '未知SN' ? 'pointer' : 'default' }}
                  onClick={() => {
                    if (sn !== '未知SN') {
                      navigate(`/monitoring/sensors/${sn}/history?location=${encodeURIComponent(loc)}`);
                    }
                  }}
                >{`${loc}`}</Tag>
              );
            })}
          </Space>
        );
      },
    },
    // {
    //   title: '状态',
    //   dataIndex: 'active',
    //   width: 80,
    //   valueType: 'select',
    //   valueEnum: {
    //     1: { text: '运行中', status: 'Success' },
    //     0: { text: '已停止', status: 'Default' },
    //   },
    //   render: (_, row) => (Number(row.active) === 1 ? '运行中' : '已停止'),
    //   sorter: true,
    // },
    {
      title: '服役',
      dataIndex: 'available',
      width: 80,
      valueType: 'select',
      valueEnum: {
        1: { text: '服役中', status: 'Success' },
        0: { text: '不可用', status: 'Error' },
      },
      render: (_, row) => (Number(row.available) === 1 ? '服役中' : '不可用'),
      sorter: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 60,
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
      render: (_, row) => row.desc || '-',
      sorter: true,
    },
    {
      title: '操作',
      valueType: 'option',
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="small">
          <a
            key="health-archive"
            onClick={() => navigate(`/device/${row.id}/health-archive`)}
          >
            档案
          </a>
          <a
            key="edit"
            onClick={() => {
              setEditing(row);
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
                await loadRows();
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
    <PageContainer title="设备列表">
      <ProTable<DeviceInst>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={displayedRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        onChange={(_pagination, _filters, sorter: any) => {
          const activeSorter = Array.isArray(sorter)
            ? sorter.find((item) => item.order)
            : sorter;
          setSort(
            activeSorter?.field && activeSorter.order
              ? {
                field: String(activeSorter.field),
                order: activeSorter.order,
              }
              : {},
          );
        }}
        options={{ reload: loadRows }}
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
              desc: editing.desc,
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
                desc: editing.desc,
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
            { required: true, message: '请输入设备编码' },
            { max: 128, message: '设备编码最多128个字符' },
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
                ? `${editing.device_spec.name} / ${editing.device_spec.model}${editing.device_spec.brand ? ` / ${editing.device_spec.brand}` : ''}`
                : undefined
            }
            fetcher={queryDeviceSpecs}
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
          rules={[
            { max: 128, message: '描述最多128个字符' },
          ]}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default DeviceListPage;

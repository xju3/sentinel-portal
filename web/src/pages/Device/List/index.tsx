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
import { Button, Popconfirm, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
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
import { DeviceSpec, listAllDeviceSpecs, queryDeviceSpecs } from '@/services/deviceSpec';

import { renderRefSafeTableOptions } from '@/utils/proTableOptions';
type DeviceInstFormValues = {
  code: string;
  device_spec_id: string;
  sn: string;
  purchase_date: string | Dayjs;
  life_span: number;
  desc: string;
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

const toApiDate = (value: string | Dayjs): string => {
  if (typeof value === 'string') {
    return value.trim();
  }
  return value.format('YYYY-MM-DD');
};

const DeviceListPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<DeviceInst[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<DeviceInst | null>(null);
  const [specs, setSpecs] = useState<DeviceSpec[]>([]);

  const specMap = useMemo(
    () =>
      new Map(
        specs.map((item) => [
          item.id,
          `${item.name} / ${item.model}${item.brand ? ` / ${item.brand}` : ''}`,
        ]),
      ),
    [specs],
  );

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

  const loadSpecs = async () => {
    try {
      setSpecs(await listAllDeviceSpecs());
    } catch (error) {
      message.error(toErrorMessage(error));
    }
  };

  useEffect(() => {
    loadRows();
    loadSpecs();
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
      if (query.code && !norm(row.code).includes(norm(query.code))) {
        return false;
      }
      if (query.sn && !norm(row.sn).includes(norm(query.sn))) {
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
        const specText = specMap.get(row.device_spec_id) || '';
        const hit =
          norm(specText).includes(norm(query.device_spec_id)) ||
          norm(row.device_spec_id).includes(norm(query.device_spec_id));
        if (!hit) {
          return false;
        }
      }
      return true;
    });
  }, [query, rows, specMap]);

  const specPickerColumns: ColumnsType<DeviceSpec> = [
    { title: '规格名称', dataIndex: 'name' },
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
      title: '实例编码',
      dataIndex: 'code',
      width: 140,
    },
    {
      title: '设备SN',
      dataIndex: 'sn',
      width: 180,
    },
    {
      title: '设备规格',
      dataIndex: 'device_spec_id',
      width: 260,
      render: (_, row) => specMap.get(row.device_spec_id) || row.device_spec_id,
    },
    {
      title: '采购日期',
      dataIndex: 'purchase_date',
      width: 140,
      valueType: 'date',
    },
    {
      title: '寿命(月)',
      dataIndex: 'life_span',
      width: 110,
      valueType: 'digit',
    },
    {
      title: '描述',
      dataIndex: 'desc',
      ellipsis: true,
      render: (_, row) => row.desc || '-',
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
          <Button danger type="link">
            删除
          </Button>
        </Popconfirm>,
      ],
    },
  ];

  return (
    <PageContainer title="设备列表">
      <ProTable<DeviceInst>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
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
        title={editing ? '编辑设备实例' : '新建设备实例'}
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
                code: editing.code,
                device_spec_id: editing.device_spec_id,
                sn: editing.sn,
                purchase_date: dayjs(editing.purchase_date),
                life_span: editing.life_span,
                desc: editing.desc,
                status: Number(editing.status),
              }
            : {
                life_span: 0,
                status: 1,
              }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: DeviceInstPayload = {
              code: values.code.trim(),
              device_spec_id: values.device_spec_id,
              sn: values.sn.trim(),
              purchase_date: toApiDate(values.purchase_date),
              life_span: Number(values.life_span ?? 0),
              desc: values.desc.trim(),
              status: Number(values.status ?? 1),
            };

            if (editing) {
              await updateDeviceInst(editing.id, payload);
              message.success('更新成功');
            } else {
              await createDeviceInst(payload);
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
          name="code"
          label="实例编码"
          rules={[
            { required: true, message: '请输入实例编码' },
            { max: 16, message: '实例编码最多16个字符' },
          ]}
        />
        <ProFormText
          name="sn"
          label="设备SN"
          rules={[
            { required: true, message: '请输入设备SN' },
            { max: 64, message: '设备SN最多64个字符' },
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
              editing?.device_spec_id ? specMap.get(editing.device_spec_id) || editing.device_spec_id : undefined
            }
            fetcher={queryDeviceSpecs}
            columns={specPickerColumns}
            getRecordLabel={(row) => `${row.name} / ${row.model} / ${row.brand}`}
          />
        </ProForm.Item>
        <ProFormDatePicker
          name="purchase_date"
          label="采购日期"
          fieldProps={{ format: 'YYYY-MM-DD' }}
          rules={[{ required: true, message: '请选择采购日期' }]}
        />
        <ProFormDigit
          name="life_span"
          label="寿命(月)"
          min={0}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入寿命(月)' }]}
        />
        <ProFormText
          name="desc"
          label="描述"
          rules={[
            { required: true, message: '请输入描述' },
            { max: 128, message: '描述最多128个字符' },
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

export default DeviceListPage;

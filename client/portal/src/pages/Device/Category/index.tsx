import { useRef, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProForm,
  ActionType,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, message, Tag, Tooltip, Modal, Transfer } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { TransferProps } from 'antd';
import EntityPicker from '@/components/EntityPicker';
import { listEmployees } from '@/services/org';

import {
  DeviceCategory,
  DeviceCategoryPayload,
  createDeviceCategory,
  deleteDeviceCategory,
  listHealthCheckFreqs,
  listIsoStandards,
  queryDeviceCategories,
  updateDeviceCategory,
  updateDeviceCategoryEmployees,
} from '@/services/deviceCategory';
import { listSensorThresholds } from '@/services/sensorThreshold';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

type CategoryFormValues = {
  name: string;
  description?: string;
  color?: string;
  parent_id?: string;
  health_check_freq_id: string;
  iso_standard_id?: string;
  vib_threshold_id?: string;
  temp_threshold_id?: string;
};

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | {
      data?: { detail?: string };
      info?: { errorMessage?: string };
      message?: string;
    }
    | undefined;
  return (
    e?.data?.detail ||
    e?.info?.errorMessage ||
    e?.message ||
    '请求失败，请稍后重试'
  );
};

const DeviceCategoryPage = () => {
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<DeviceCategory | null>(null);
  const [createChildParent, setCreateChildParent] = useState<DeviceCategory | null>(null);

  const [employees, setEmployees] = useState<{ id: string; name: string; email?: string; mobile?: string }[]>([]);
  const [transferModalOpen, setTransferModalOpen] = useState(false);
  const [currentCategory, setCurrentCategory] = useState<DeviceCategory | null>(null);
  const [targetKeys, setTargetKeys] = useState<TransferProps['targetKeys']>([]);
  const columns: ProColumns<DeviceCategory>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 120,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 120,
      sorter: true,
    },
    {
      title: '标识色',
      dataIndex: 'color',
      width: 100,
      render: (_, row) => {
        if (!row.color) return '-';
        return <Tag color={row.color}>{row.color}</Tag>;
      },
      sorter: true,
    },
    {
      title: '上级分类',
      dataIndex: 'parent_id',
      width: 140,
      render: (_, row) => row.parent?.name || row.parent_id || '-',
    },

    {
      title: '振动阀值',
      dataIndex: 'vib_threshold_id',
      ellipsis: true,
      render: (_, row) => row.vib_threshold?.code || '-',
      sorter: true,
    },
    {
      title: '温度阀值',
      dataIndex: 'temp_threshold_id',
      ellipsis: true,
      render: (_, row) => row.temp_threshold?.code || '-',
      sorter: true,
    },
    {
      title: '监测频率',
      dataIndex: 'health_check_freq_id',
      ellipsis: true,
      render: (_, row) => {
        const freq = row.health_check_freq;
        if (!freq) return row.health_check_freq_id;
        return `巡检${freq.patrol}m / 诊断${freq.diagnosis}m / 上报${freq.report}`;
      },
      sorter: true,
    },
    {
      title: 'ISO',
      dataIndex: 'iso_standard_id',
      ellipsis: true,
      render: (_, row) => {
        const iso = row.iso_standard;
        return iso ? `${iso.code} (ISO-${iso.version === 1 ? '10816' : '20816'})` : '-';
      },
      sorter: true,
    },
    {
      title: '员工',
      key: 'employees',
      hideInSearch: true,
      render: (_, row) => {
        const emps = row.employees || [];
        if (emps.length === 0) {
          return <Tag color="default">无</Tag>;
        }
        const names = emps.map(e => e.name).join(', ');
        return (
          <Tooltip title={names}>
            <Tag color="blue">{emps.length} 名负责员工</Tag>
          </Tooltip>
        );
      },
    },
    {
      title: '备注',
      dataIndex: 'description',
      ellipsis: true,
      render: (_, row) => row.description || '-',
      sorter: true,
    },
    {
      title: '操作',
      valueType: 'option',
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="middle">
          <a
            key="create-child"
            onClick={() => {
              setEditing(null);
              setCreateChildParent(row);
              setModalOpen(true);
            }}
          >
            新建
          </a>
          <a
            key="edit"
            onClick={() => {
              setCreateChildParent(null);
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <a
            key="employees"
            onClick={async () => {
              setCurrentCategory(row);
              setTargetKeys((row.employees || []).map(e => e.id));
              setTransferModalOpen(true);
              if (employees.length === 0) {
                const emps = await listEmployees({ has_wx_user_id: true });
                setEmployees(emps || []);
              }
            }}
          >
            员工
          </a>
          <Popconfirm
            key="delete"
            title="确认删除该分类吗？"
            onConfirm={async () => {
              try {
                await deleteDeviceCategory(row.id);
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

  const parentPickerColumns: ColumnsType<DeviceCategory> = [
    { title: '分类名称', dataIndex: 'name' },
    {
      title: '上级分类',
      dataIndex: 'parent_id',
      render: (_, row) => row.parent?.name || row.parent_id || '-',
    },
    {
      title: '描述',
      dataIndex: 'description',
      render: (_, row) => row.description || '-',
    },
  ];

  return (
    <PageContainer title="设备分类">
      <ProTable
        rowKey="id"
        columns={columns}
        scroll={{ x: 'max-content' }}
        actionRef={actionRef}
        request={queryDeviceCategories}
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
              setCreateChildParent(null);
              setModalOpen(true);
            }}
          >
            新建分类
          </Button>,
        ]}
      />

      <ModalForm<CategoryFormValues>
        title={
          editing
            ? '编辑设备分类'
            : createChildParent
              ? `新建子分类（上级：${createChildParent.name}）`
              : '新建设备分类'
        }
        open={modalOpen}
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setModalOpen(false);
            setEditing(null);
            setCreateChildParent(null);
          },
        }}
        submitter={{
          searchConfig: {
            submitText: '保存',
          },
          submitButtonProps: {
            loading: saving,
          },
        }}
        initialValues={
          editing
            ? {
              name: editing.name,
              description: editing.description,
              color: editing.color || undefined,
              parent_id: editing.parent_id || undefined,
              health_check_freq_id: editing.health_check_freq_id,
              iso_standard_id: editing.iso_standard_id || undefined,
              vib_threshold_id: editing.vib_threshold_id || undefined,
              temp_threshold_id: editing.temp_threshold_id || undefined,
            }
            : createChildParent
              ? {
                parent_id: createChildParent.id,
              }
              : undefined
        }
        onFinish={async (values) => {
          const payload: DeviceCategoryPayload = {
            name: values.name.trim(),
            description: values.description || undefined,
            color: values.color || null,
            parent_id: values.parent_id || null,
            health_check_freq_id: values.health_check_freq_id,
            iso_standard_id: values.iso_standard_id || null,
            vib_threshold_id: values.vib_threshold_id || null,
            temp_threshold_id: values.temp_threshold_id || null,
          };
          setSaving(true);
          try {
            if (editing) {
              await updateDeviceCategory(editing.id, payload);
            } else {
              await createDeviceCategory(payload);
            }
            message.success('保存成功');
            setModalOpen(false);
            setEditing(null);
            setCreateChildParent(null);
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
        <ProFormText name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]} />
        <ProForm.Item name="color" label="标识色">
          <input type="color" style={{ width: 100, height: 32, padding: 0, border: 'none', background: 'none' }} />
        </ProForm.Item>
        <ProFormSelect
          name="vib_threshold_id"
          label="振动阀值"
          request={async () => {
            const thresholds = await listSensorThresholds();
            return (thresholds || [])
              .filter((item) => item.metric === 1)
              .map((item) => ({
                value: item.id,
                label: `${item.code} - 振动阀值`,
              }));
          }}
        />
        <ProFormSelect
          name="temp_threshold_id"
          label="温度阀值"
          request={async () => {
            const thresholds = await listSensorThresholds();
            return (thresholds || [])
              .filter((item) => item.metric === 2)
              .map((item) => ({
                value: item.id,
                label: `${item.code} - 温度阀值`,
              }));
          }}
        />
        <ProFormSelect
          name="health_check_freq_id"
          label="巡检频率"
          rules={[{ required: true, message: '请选择巡检频率' }]}
          request={async () => {
            const freqs = await listHealthCheckFreqs();
            return (freqs || []).map((item) => ({
              value: item.id,
              label: `巡检${item.patrol}m / 诊断${item.diagnosis}m / 上报${item.report}`,
            }));
          }}
        />
        <ProFormSelect
          name="iso_standard_id"
          label="ISO标准"
          request={async () => {
            const isos = await listIsoStandards();
            return (isos || []).map((item) => ({
              value: item.id,
              label: `${item.code} (ISO-${item.version === 1 ? '10816' : '20816'})`,
            }));
          }}
        />

        <ProForm.Item name="parent_id" label="上级分类">
          <EntityPicker<DeviceCategory>
            placeholder="可选，点击选择上级分类"
            modalTitle="选择上级分类"
            triggerText="选择"
            valueLabel={
              editing?.parent
                ? editing.parent.name
                : createChildParent
                  ? createChildParent.name
                  : undefined
            }
            columns={parentPickerColumns}
            getRecordLabel={(record) => record.name}
            fetcher={async ({ current, pageSize, keyword }) => {
              const result = await queryDeviceCategories({ current, pageSize, keyword });
              return {
                items: result.data,
                total: result.total,
              };
            }}
          />
        </ProForm.Item>
        <ProFormText name="description" label="备注" />
      </ModalForm>

      {/* 负责员工配置弹窗 */}
      <Modal
        title={`设置负责员工 - ${currentCategory?.name}`}
        open={transferModalOpen}
        onCancel={() => {
          setTransferModalOpen(false);
          setCurrentCategory(null);
          setTargetKeys([]);
        }}
        onOk={async () => {
          if (!currentCategory) return;
          setSaving(true);
          try {
            await updateDeviceCategoryEmployees(currentCategory.id, targetKeys as string[]);
            message.success('负责员工设置成功');
            setTransferModalOpen(false);
            setCurrentCategory(null);
            setTargetKeys([]);
            actionRef.current?.reload();
          } catch (error) {
            message.error(toErrorMessage(error));
          } finally {
            setSaving(false);
          }
        }}
        confirmLoading={saving}
        width={700}
        destroyOnClose
      >
        <Transfer
          dataSource={employees.map(emp => ({
            key: emp.id,
            title: `${emp.name} (${emp.mobile || '无手机号'})`,
            description: emp.name,
          }))}
          showSearch
          listStyle={{
            width: 300,
            height: 400,
          }}
          targetKeys={targetKeys}
          onChange={(newTargetKeys) => setTargetKeys(newTargetKeys)}
          render={item => item.title}
          titles={['可选员工', '已选负责员工']}
        />
      </Modal>
    </PageContainer>
  );
};

export default DeviceCategoryPage;

import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProForm,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Modal, Popconfirm, Space, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import EntityPicker from '@/components/EntityPicker';
import { DeviceSpec, listAllDeviceSpecs, queryDeviceSpecs } from '@/services/deviceSpec';
import {
  createProcess,
  createProcessItem,
  deleteProcess,
  deleteProcessItem,
  listAllProcessItems,
  listAllProcesses,
  Process,
  ProcessItem,
  updateProcess,
  updateProcessItem,
} from '@/services/process';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
type ProcessFormValues = {
  code: string;
  name: string;
  status: number;
  remark?: string;
};

type ProcessItemFormValues = {
  device_spec_id: string;
  qty: number;
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

const ProcessTemplatePage = () => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Process | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [rows, setRows] = useState<Process[]>([]);

  const [configOpen, setConfigOpen] = useState(false);
  const [currentProcess, setCurrentProcess] = useState<Process | null>(null);
  const [processItems, setProcessItems] = useState<ProcessItem[]>([]);
  const [itemSaving, setItemSaving] = useState(false);
  const [itemModalOpen, setItemModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<ProcessItem | null>(null);

  const loadProcesses = async () => {
    setLoading(true);
    try {
      setRows(await listAllProcesses());
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const loadItems = async () => {
    try {
      setProcessItems(await listAllProcessItems());
    } catch (error) {
      message.error(toErrorMessage(error));
    }
  };

  useEffect(() => {
    loadProcesses();
    loadItems();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.code && !norm(row.code).includes(norm(query.code))) {
        return false;
      }
      if (query.name && !norm(row.name).includes(norm(query.name))) {
        return false;
      }
      if (
        query.status !== undefined &&
        query.status !== null &&
        String(row.status) !== String(query.status)
      ) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const currentProcessItems = useMemo(() => {
    if (!currentProcess?.id) {
      return [];
    }
    return processItems.filter((item) => item.process_id === currentProcess.id);
  }, [currentProcess?.id, processItems]);

  const columns: ProColumns<Process>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    { title: '编码', dataIndex: 'code', width: 140, sorter: (a, b) => (a.code || '').localeCompare(b.code || '', 'zh-CN') },
    { title: '名称', dataIndex: 'name', sorter: (a, b) => (a.name || '').localeCompare(b.name || '', 'zh-CN') },
    {
      title: '工况及说明',
      dataIndex: 'remark',
      hideInSearch: true,
      ellipsis: true,
    },
    {
      title: '状态',
      width: 120,
      dataIndex: 'status',
      valueType: 'select',
      valueEnum: {
        1: { text: '启用' },
        0: { text: '停用' },
      },
      render: (_, row) => (Number(row.status) === 1 ? '启用' : '停用'),
      sorter: (a, b) => Number(a.status) - Number(b.status),
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
            key="config"
            onClick={async () => {
              setCurrentProcess(row);
              setConfigOpen(true);
              await loadItems();
            }}
          >
            配置
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
          <Popconfirm
            key="delete"
            title="确认删除该分组模板吗？"
            onConfirm={async () => {
              try {
                await deleteProcess(row.id);
                message.success('删除成功');
                await loadProcesses();
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

  const itemColumns: ProColumns<ProcessItem>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
    },
    {
      title: '规格',
      dataIndex: 'device_spec_id',
      render: (_, row) => row.device_spec?.name || row.device_spec_id,
    },
    {
      title: '数量',
      dataIndex: 'qty',
      width: 120,
      valueType: 'digit',
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
              setEditingItem(row);
              setItemModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            key="delete"
            title="确认删除该子项吗？"
            onConfirm={async () => {
              try {
                await deleteProcessItem(row.id);
                message.success('删除成功');
                await loadItems();
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

  const specPickerColumns: ColumnsType<DeviceSpec> = [
    { title: '规格', dataIndex: 'name' },
    { title: '型号', dataIndex: 'model' },
    { title: '品牌', dataIndex: 'brand' },
    { title: '电压(V)', dataIndex: 'voltage' },
    { title: '转速(RPM)', dataIndex: 'rpm' },
  ];

  return (
    <PageContainer title="分组模板">
      <ProTable<Process>
        rowKey="id"
        loading={loading}
        columns={columns}
        scroll={{ x: 'max-content' }}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadProcesses }}
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
            新建分组模板
          </Button>,
        ]}
      />

      <ModalForm<ProcessFormValues>
        title={editing ? '编辑分组模板' : '新建分组模板'}
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
            ? { code: editing.code, name: editing.name, status: Number(editing.status), remark: editing.remark }
            : { status: 1 }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload = {
              code: values.code.trim(),
              name: values.name.trim(),
              status: Number(values.status ?? 1),
              remark: values.remark?.trim(),
            };
            if (editing) {
              await updateProcess(editing.id, payload);
              message.success('更新成功');
            } else {
              await createProcess(payload);
              message.success('创建成功');
            }
            setModalOpen(false);
            setEditing(null);
            await loadProcesses();
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
          label="编码"
          rules={[
            { required: true, message: '请输入编码' },
            { max: 8, message: '编码最多8个字符' },
          ]}
        />
        <ProFormText
          name="name"
          label="名称"
          rules={[
            { required: true, message: '请输入名称' },
            { max: 64, message: '名称最多64个字符' },
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
        <ProFormText
          name="remark"
          label="工况/工艺/设备构成"
        />
      </ModalForm>

      <Modal
        title={`分组模板配置 - ${currentProcess?.name || ''}`}
        open={configOpen}
        width={960}
        destroyOnHidden
        onCancel={() => {
          setConfigOpen(false);
          setCurrentProcess(null);
          setEditingItem(null);
          setItemModalOpen(false);
        }}
        footer={null}
      >
        <ProTable<ProcessItem>
          rowKey="id"
          columns={itemColumns}
          scroll={{ x: 'max-content' }}
          dataSource={currentProcessItems}
          search={false}
          pagination={{ pageSize: 8 }}
          options={false}
          toolBarRender={() => [
            <Button
              key="create"
              type="primary"
              onClick={() => {
                setEditingItem(null);
                setItemModalOpen(true);
              }}
            >
              新增子项
            </Button>,
          ]}
        />

        <ModalForm<ProcessItemFormValues>
          title={editingItem ? '编辑子项' : '新增子项'}
          open={itemModalOpen}
          modalProps={{
            destroyOnHidden: true,
            onCancel: () => {
              setItemModalOpen(false);
              setEditingItem(null);
            },
          }}
          submitter={{
            submitButtonProps: { loading: itemSaving },
            searchConfig: { submitText: '保存' },
          }}
          initialValues={
            editingItem
              ? {
                  device_spec_id: editingItem.device_spec_id,
                  qty: editingItem.qty,
                }
              : {
                  qty: 1,
                }
          }
          onFinish={async (values) => {
            if (!currentProcess?.id) {
              message.error('未选择分组模板');
              return false;
            }
            setItemSaving(true);
            try {
              const payload = {
                process_id: currentProcess.id,
                device_spec_id: values.device_spec_id,
                qty: Number(values.qty ?? 1),
              };
              if (editingItem) {
                await updateProcessItem(editingItem.id, payload);
                message.success('更新成功');
              } else {
                await createProcessItem(payload);
                message.success('创建成功');
              }
              setItemModalOpen(false);
              setEditingItem(null);
              await loadItems();
              return true;
            } catch (error) {
              message.error(toErrorMessage(error));
              return false;
            } finally {
              setItemSaving(false);
            }
          }}
        >
          <ProForm.Item
            name="device_spec_id"
            label="设备规格"
            rules={[{ required: true, message: '请选择设备规格' }]}
          >
            <EntityPicker<DeviceSpec>
              placeholder="请点击选择设备规格"
              modalTitle="选择设备规格"
              triggerText="选择"
              valueLabel={
                editingItem?.device_spec
                  ? `${editingItem.device_spec.name} / ${editingItem.device_spec.model}`
                  : editingItem?.device_spec_id
              }
              columns={specPickerColumns}
              getRecordLabel={(record) => `${record.name} / ${record.model} / ${record.brand}`}
              fetcher={queryDeviceSpecs}
            />
          </ProForm.Item>
          <ProFormDigit
            name="qty"
            label="数量"
            min={1}
            fieldProps={{ precision: 0 }}
            rules={[{ required: true, message: '请输入数量' }]}
          />
        </ModalForm>
      </Modal>
    </PageContainer>
  );
};

export default ProcessTemplatePage;

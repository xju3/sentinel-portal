import { useRef, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProForm,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import type { ActionType } from '@ant-design/pro-components';
import { Button, Modal, Popconfirm, Space, message, Tabs } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import EntityPicker from '@/components/EntityPicker';
import { DeviceSpec, queryDeviceSpecs } from '@/services/deviceSpec';
import {
  createProcess,
  createProcessItem,
  deleteProcess,
  deleteProcessItem,
  Process,
  ProcessItem,
  updateProcess,
  updateProcessItem,
} from '@/services/process';
import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
import { requestPagedList } from '@/utils/proTableRequest';

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

type ProcessItemRecord = ProcessItem & {
  device_spec?: DeviceSpec;
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
  const actionRef = useRef<ActionType>();
  const itemActionRef = useRef<ActionType>();
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Process | null>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const [currentProcess, setCurrentProcess] = useState<Process | null>(null);
  const [itemSaving, setItemSaving] = useState(false);
  const [itemModalOpen, setItemModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<ProcessItemRecord | null>(null);

  const columns: ProColumns<Process>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '编码',
      dataIndex: 'code',
      width: 140,
      sorter: true,
    },
    {
      title: '名称',
      dataIndex: 'name',
      sorter: true,
    },
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
            key="config"
            onClick={() => {
              setCurrentProcess(row);
              setEditingItem(null);
              setItemModalOpen(false);
              setConfigOpen(true);
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

  const itemColumns: ProColumns<ProcessItemRecord>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
    },
    {
      title: '规格',
      dataIndex: 'device_spec_id',
      render: (_, row) =>
        row.device_spec
          ? `${row.device_spec.name} / ${row.device_spec.model}${row.device_spec.brand ? ` / ${row.device_spec.brand}` : ''}`
          : row.device_spec_id,
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
                itemActionRef.current?.reload();
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
        columns={columns}
        scroll={{ x: 'max-content' }}
        actionRef={actionRef}
        request={(params, sort) =>
          requestPagedList<Process>('/api/v1/processes', {
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
            ? {
                code: editing.code,
                name: editing.name,
                status: Number(editing.status),
                remark: editing.remark,
              }
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
        <Tabs
          defaultActiveKey="1"
          items={[
            {
              key: '1',
              label: '基本信息',
              children: (
                <>
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
                </>
              ),
            },
            {
              key: '2',
              label: '工况/工艺/设备构成',
              children: (
                <ProFormTextArea
                  name="remark"
                  label=""
                  placeholder="请输入工况、工艺、或设备构成等信息"
                  fieldProps={{ rows: 14 }}
                />
              ),
            },
          ]}
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
        <ProTable<ProcessItemRecord>
          rowKey="id"
          columns={itemColumns}
          scroll={{ x: 'max-content' }}
          actionRef={itemActionRef}
          request={(params, sort) => {
            if (!currentProcess?.id) {
              return Promise.resolve({
                data: [],
                success: true,
                total: 0,
              });
            }
            return requestPagedList<ProcessItemRecord>('/api/v1/process-items', {
              params: {
                ...params,
                process_id: currentProcess.id,
              },
              sort: sort as any,
              defaultPageSize: 20,
            });
          }}
          search={false}
          pagination={{ defaultPageSize: 20, showSizeChanger: true }}
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
              itemActionRef.current?.reload();
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
              fetcher={async (query) => {
                const result = await queryDeviceSpecs(query);
                return {
                  items: result.items || result.data,
                  total: result.total,
                };
              }}
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

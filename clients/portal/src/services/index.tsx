import { PlusOutlined } from '@ant-design/icons';
import {
  ActionType,
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, message, Popconfirm, Space, Tag } from 'antd';
import React, { useRef, useState } from 'react';

import {
  createSensorFirmware,
  deleteSensorFirmware,
  getSensorTypesOptions,
  getTenantsOptions,
  listSensorFirmwares,
  releaseSensorFirmware,
  updateSensorFirmware,
} from '@/services/admin';

const FirmwareAdminPage: React.FC = () => {
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [currentRow, setCurrentRow] = useState<any>(undefined);

  const handleRelease = async (id: string) => {
    try {
      await releaseSensorFirmware(id);
      message.success('固件发布成功，升级任务已生成');
      actionRef.current?.reload();
    } catch (error: any) {
      message.error(error?.data?.detail || '发布失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteSensorFirmware(id);
      message.success('固件删除成功');
      actionRef.current?.reload();
    } catch (error: any) {
      message.error(error?.data?.detail || '删除失败');
    }
  };

  const columns: ProColumns<any>[] = [
    {
      title: '版本号',
      dataIndex: 'version',
      width: 120,
    },
    {
      title: '传感器类型',
      dataIndex: 'sensor_type_id',
      valueType: 'select',
      width: 150,
      request: async () => {
        const res = await getSensorTypesOptions();
        return (res.data || []).map((item: any) => ({
          label: item.name,
          value: item.id,
        }));
      },
    },
    {
      title: '定向租户(客户)',
      dataIndex: 'tenant_id',
      valueType: 'select',
      width: 180,
      request: async () => {
        const res = await getTenantsOptions();
        return (res.data || []).map((item: any) => ({
          label: item.name,
          value: item.id,
        }));
      },
      render: (dom, record) => {
        return record.tenant_id ? dom : <Tag color="blue">全局发布</Tag>;
      },
    },
    {
      title: '固件文件',
      dataIndex: 'file_url',
      hideInSearch: true,
      width: 100,
      render: (_, record) => (
        <a href={record.file_url} target="_blank" rel="noreferrer">
          下载链接
        </a>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        0: { text: '待发布', status: 'Default' },
        1: { text: '已发布', status: 'Success' },
      },
    },
    {
      title: '发布时间',
      dataIndex: 'release_date',
      valueType: 'dateTime',
      hideInSearch: true,
      width: 160,
    },
    {
      title: '描述',
      dataIndex: 'description',
      valueType: 'textarea',
      hideInSearch: true,
      ellipsis: true,
    },
    {
      title: '操作',
      valueType: 'option',
      key: 'option',
      fixed: 'right',
      width: 160,
      render: (_, record) => {
        const isDraft = record.status === 0;
        return (
          <Space>
            {isDraft && (
              <a onClick={() => { setCurrentRow(record); setModalOpen(true); }}>
                编辑
              </a>
            )}
            {isDraft && (
              <Popconfirm
                title="发布固件"
                description="发布后将为所有匹配设备生成升级任务，且不可撤销，确认发布吗？"
                onConfirm={() => handleRelease(record.id)}
              >
                <a style={{ color: '#52c41a' }}>发布</a>
              </Popconfirm>
            )}
            <Popconfirm
              title="删除固件"
              description="确定要删除这个固件记录吗？"
              onConfirm={() => handleDelete(record.id)}
            >
              <a style={{ color: '#ff4d4f' }}>删除</a>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <PageContainer title="固件升级管理 (Admin)" ghost>
      <ProTable
        headerTitle="传感器固件列表"
        actionRef={actionRef}
        rowKey="id"
        search={{ labelWidth: 'auto' }}
        toolBarRender={() => [
          <Button
            type="primary"
            key="primary"
            onClick={() => {
              setCurrentRow(undefined);
              setModalOpen(true);
            }}
          >
            <PlusOutlined /> 新增固件
          </Button>,
        ]}
        request={async (params) => {
          // ProTable 默认传入 current 和 pageSize
          const skip = ((params.current || 1) - 1) * (params.pageSize || 10);
          const limit = params.pageSize || 10;
          const res = await listSensorFirmwares({ skip, limit });
          return {
            data: res.data || [],
            success: res.code === 0,
            total: res.data?.length || 0, // 提示: 真实环境后端最好返回 total 用于标准分页
          };
        }}
        columns={columns}
      />

      <ModalForm
        title={currentRow ? '编辑固件' : '新增固件'}
        open={modalOpen}
        onOpenChange={setModalOpen}
        initialValues={currentRow || {}}
        modalProps={{ destroyOnClose: true }}
        onFinish={async (values) => {
          try {
            if (currentRow) {
              await updateSensorFirmware(currentRow.id, values);
              message.success('更新成功');
            } else {
              await createSensorFirmware(values);
              message.success('创建成功');
            }
            setModalOpen(false);
            actionRef.current?.reload();
            return true;
          } catch (error: any) {
            message.error(error?.data?.detail || '保存失败');
            return false;
          }
        }}
      >
        <ProFormText
          name="version"
          label="版本号"
          placeholder="请输入版本号，例如: v1.0.1"
          rules={[{ required: true, message: '版本号是必填项' }]}
        />
        <ProFormSelect
          name="sensor_type_id"
          label="传感器类型"
          request={async () => {
            const res = await getSensorTypesOptions();
            return (res.data || []).map((item: any) => ({ label: item.name, value: item.id }));
          }}
          rules={[{ required: true, message: '必须选择一个适用的传感器类型' }]}
        />
        <ProFormSelect
          name="tenant_id"
          label="定向租户 (可选)"
          placeholder="清空/不选则代表该固件对所有租户全局发布"
          allowClear
          request={async () => {
            const res = await getTenantsOptions();
            return (res.data || []).map((item: any) => ({ label: item.name, value: item.id }));
          }}
        />
        <ProFormText
          name="file_url"
          label="固件下载地址 (URL)"
          placeholder="请输入可被设备直接访问下载的 URL"
          rules={[{ required: true, message: '固件下载地址是必填项' }]}
        />
        <ProFormTextArea
          name="description"
          label="更新描述"
          placeholder="请输入本次固件升级的修复内容或新增功能描述"
        />
      </ModalForm>
    </PageContainer>
  );
};

export default FirmwareAdminPage;
import { PlusOutlined } from '@ant-design/icons';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import {
  PageContainer,
  ProTable,
  ModalForm,
  ProFormText,
  ProFormSelect,
  ProFormDateTimePicker,
} from '@ant-design/pro-components';
import { Button, message, Popconfirm } from 'antd';
import React, { useRef, useState } from 'react';
import dayjs from 'dayjs';
import { getSimCards, addSimCard, updateSimCard, removeSimCard, SimCardItem } from '@/services/simCard';

const SimCardManager: React.FC = () => {
  const actionRef = useRef<ActionType>();
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [currentRow, setCurrentRow] = useState<SimCardItem | undefined>(undefined);

  const handleAddOrUpdate = async (values: SimCardItem) => {
    const hide = message.loading('正在保存...');
    try {
      if (currentRow?.id) {
        await updateSimCard(currentRow.id, values);
        message.success('更新成功');
      } else {
        await addSimCard(values);
        message.success('添加成功');
      }
      setModalVisible(false);
      setCurrentRow(undefined);
      actionRef.current?.reload();
    } catch (error) {
      message.error('保存失败，请重试');
    } finally {
      hide();
    }
  };

  const handleDelete = async (id: string) => {
    const hide = message.loading('正在删除...');
    try {
      await removeSimCard(id);
      message.success('删除成功');
      actionRef.current?.reload();
    } catch (error) {
      message.error('删除失败，请重试');
    } finally {
      hide();
    }
  };

  const columns: ProColumns<SimCardItem>[] = [
    {
      title: '关键字查询',
      dataIndex: 'keyword',
      hideInTable: true,
      tooltip: '支持按卡号、ICCID、运营商搜索',
    },
    {
      title: 'SIM 卡号',
      dataIndex: 'number',
      search: false,
    },
    {
      title: 'ICCID',
      dataIndex: 'ccid',
      search: false,
    },
    {
      title: '运营商',
      dataIndex: 'carrier',
      search: false,
    },
    {
      title: '数据套餐',
      dataIndex: 'data_plan',
      search: false,
    },
    {
      title: '激活时间',
      dataIndex: 'activated_at',
      valueType: 'dateTime',
      search: false,
    },
    {
      title: '到期时间',
      dataIndex: 'expires_at',
      valueType: 'dateTime',
      search: false,
    },
    {
      title: '状态',
      dataIndex: 'status',
      search: false,
      valueEnum: {
        0: { text: '停用', status: 'Error' },
        1: { text: '正常', status: 'Success' },
      },
    },
    {
      title: '操作',
      dataIndex: 'option',
      valueType: 'option',
      // fixed: 'right',
      width: 120,
      render: (_, record) => [
        <a
          key="edit"
          onClick={() => {
            setCurrentRow(record);
            setModalVisible(true);
          }}
        >
          编辑
        </a>,
        <Popconfirm
          key="delete"
          title="确定要删除这张 SIM 卡吗？"
          onConfirm={() => handleDelete(record.id)}
        >
          <a style={{ color: 'red' }}>删除</a>
        </Popconfirm>,
      ],
    },
  ];

  return (
    <PageContainer>
      <ProTable<SimCardItem>
        headerTitle="SIM 卡列表"
        actionRef={actionRef}
        rowKey="id"
        search={{
          labelWidth: 120,
        }}
        toolBarRender={() => [
          <Button
            type="primary"
            key="primary"
            onClick={() => {
              setCurrentRow(undefined);
              setModalVisible(true);
            }}
          >
            <PlusOutlined /> 新建 SIM 卡
          </Button>,
        ]}
        request={async (params) => {
          const res = await getSimCards(params);
          return {
            data: res?.list || [],
            success: true,
            total: res?.total || 0,
          };
        }}
        columns={columns}
      />

      <ModalForm
        title={currentRow ? '编辑 SIM 卡' : '新建 SIM 卡'}
        width="400px"
        visible={modalVisible}
        onVisibleChange={setModalVisible}
        initialValues={
          currentRow || {
            status: 1,
            data_plan: '300',
            expires_at: dayjs().add(3, 'year').format('YYYY-MM-DD HH:mm:ss')
          }
        }
        onFinish={handleAddOrUpdate}
        modalProps={{ destroyOnClose: true }}
      >
        <ProFormText rules={[{ required: true }]} name="number" label="SIM 卡号" />
        <ProFormText rules={[{ required: true }]} name="ccid" label="ICCID" />
        <ProFormSelect
          rules={[{ required: true }]}
          name="carrier"
          label="运营商"
          options={[
            { label: '联通', value: '联通' },
            { label: '电信', value: '电信' },
            { label: '移动', value: '移动' },
          ]}
        />
        <ProFormText rules={[{ required: true }]} name="data_plan" label="数据套餐" />
        <ProFormDateTimePicker name="activated_at" label="激活时间" />
        <ProFormDateTimePicker rules={[{ required: true }]} name="expires_at" label="到期时间" />
        <ProFormSelect name="status" label="状态" options={[{ label: '正常', value: 1 }, { label: '停用', value: 0 }]} />
      </ModalForm>
    </PageContainer>
  );
};

export default SimCardManager;

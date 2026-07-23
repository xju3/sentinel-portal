import React, { useEffect, useState } from 'react';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { ProCard, PageContainer } from '@ant-design/pro-components';
import { Button, Form, Input, Modal, Space, Table, Tag, message, Popconfirm, TreeSelect, Tree } from 'antd';
import { DepartmentInfo, listDepartments, createDepartment, updateDepartment, deleteDepartment, listEmployees, EmployeeInfo } from '@/services/org';

const Departments: React.FC = () => {
  const [departments, setDepartments] = useState<DepartmentInfo[]>([]);
  const [employees, setEmployees] = useState<EmployeeInfo[]>([]);
  const [loading, setLoading] = useState(false);
  
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);

  // Employee Selection Modal State
  const [employeeModalOpen, setEmployeeModalOpen] = useState(false);
  
  const [form] = Form.useForm();

  const fetchDepartments = async () => {
    setLoading(true);
    try {
      const data = await listDepartments();
      setDepartments(data);
    } catch (error: any) {
      message.error(error?.message || '获取部门列表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchEmployees = async () => {
    try {
      const data = await listEmployees();
      setEmployees(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchDepartments();
    fetchEmployees();
  }, []);

  const handleCreate = (parentId?: string) => {
    setEditId(null);
    form.resetFields();
    if (parentId) {
      form.setFieldsValue({ parent_id: parentId });
    }
    setModalOpen(true);
  };

  const handleEdit = (record: DepartmentInfo) => {
    setEditId(record.id);
    form.setFieldsValue({
      code: record.code,
      name: record.name,
      description: record.description,
      leader_id: record.leader_id,
      parent_id: record.parent_id,
      leader_name: record.leader_name,
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteDepartment(id);
      message.success('部门已删除');
      fetchDepartments();
    } catch (error: any) {
      message.error(error?.message || '删除失败');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      
      const payload = {
        code: values.code,
        name: values.name,
        description: values.description,
        leader_id: values.leader_id,
        parent_id: values.parent_id,
      };

      if (editId) {
        await updateDepartment(editId, payload);
        message.success('部门已更新');
      } else {
        await createDepartment(payload);
        message.success('部门创建成功');
      }
      
      setModalOpen(false);
      fetchDepartments();
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error?.message || '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  // Convert departments to tree data
  const buildTree = (parentId?: string): any[] => {
    return departments
      .filter(d => (parentId ? d.parent_id === parentId : !d.parent_id))
      .map(d => ({
        ...d,
        key: d.id,
        children: buildTree(d.id),
      }));
  };
  const treeData = buildTree();

  const columns = [
    {
      title: '部门名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '部门编号',
      dataIndex: 'code',
      key: 'code',
      width: 150,
    },
    {
      title: '负责人',
      dataIndex: 'leader_name',
      key: 'leader_name',
      width: 150,
      render: (text: string | null) => text || '-',
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: '状态',
      dataIndex: 'active',
      key: 'active',
      width: 100,
      render: (active: boolean) => (
        <Tag color={active ? 'success' : 'error'}>{active ? '启用' : '停用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: DepartmentInfo) => (
        <Space>
          <a onClick={() => handleCreate(record.id)}>新增子部门</a>
          <a onClick={() => handleEdit(record)}>编辑</a>
          <Popconfirm
            title="确认删除"
            description={`确定要删除部门 "${record.name}" 吗？`}
            onConfirm={() => handleDelete(record.id)}
            okText="确认"
            cancelText="取消"
          >
            <a style={{ color: '#ff4d4f' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // Employee Selection columns
  const employeeColumns = [
    { title: '工号', dataIndex: 'code', key: 'code' },
    { title: '姓名', dataIndex: 'name', key: 'name' },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: EmployeeInfo) => (
        <Button 
          type="link" 
          size="small"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            form.setFieldsValue({ 
              leader_id: record.id,
              leader_name: record.name,
            });
            setEmployeeModalOpen(false);
          }}
        >
          选择
        </Button>
      ),
    },
  ];

  return (
    <PageContainer title="部门资料" ghost>
      <ProCard
        title="部门列表"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => handleCreate()}>
            新增部门
          </Button>
        }
      >
        <Table
          dataSource={treeData}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={false}
          size="small"
        />
      </ProCard>

      <Modal
        title={editId ? "编辑部门" : "新增部门"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="code"
            label="部门编号"
            rules={[{ required: true, message: '请输入部门编号' }]}
          >
            <Input placeholder="请输入部门编号" />
          </Form.Item>
          
          <Form.Item
            name="name"
            label="部门名称"
            rules={[{ required: true, message: '请输入部门名称' }]}
          >
            <Input placeholder="请输入部门名称" />
          </Form.Item>

          <Form.Item label="负责人">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="leader_name" noStyle>
                <Input placeholder="请选择负责人" readOnly />
              </Form.Item>
              <Form.Item name="leader_id" noStyle>
                <Input type="hidden" />
              </Form.Item>
              <Button icon={<SearchOutlined />} onClick={() => setEmployeeModalOpen(true)}>选择</Button>
            </Space.Compact>
          </Form.Item>

          <Form.Item
            name="parent_id"
            label="上级部门"
          >
            <TreeSelect
              treeData={treeData.map(t => ({ title: t.name, value: t.id, children: t.children?.map((c: any) => ({ title: c.name, value: c.id })) }))}
              placeholder="请选择上级部门（可选）"
              allowClear
            />
          </Form.Item>

          <Form.Item
            name="description"
            label="描述"
          >
            <Input.TextArea placeholder="请输入描述" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="选择负责人"
        open={employeeModalOpen}
        onCancel={() => setEmployeeModalOpen(false)}
        footer={null}
      >
        <Table
          dataSource={employees}
          columns={employeeColumns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 5 }}
        />
      </Modal>
    </PageContainer>
  );
};

export default Departments;

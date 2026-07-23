import React, { useEffect, useState } from 'react';
import { PlusOutlined } from '@ant-design/icons';
import { ProCard, PageContainer } from '@ant-design/pro-components';
import { Button, Form, Input, Modal, Space, Table, Tag, message, Popconfirm, TreeSelect } from 'antd';
import { EmployeeInfo, listEmployees, createEmployee, updateEmployee, deleteEmployee, listDepartments, DepartmentInfo } from '@/services/org';
import { listTenantAccounts, AccountInfo, updateTenantAccount } from '@/services/tenant';

const Employees: React.FC = () => {
  const [employees, setEmployees] = useState<EmployeeInfo[]>([]);
  const [departments, setDepartments] = useState<DepartmentInfo[]>([]);
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [loading, setLoading] = useState(false);
  
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  
  const [form] = Form.useForm();

  const fetchEmployees = async () => {
    setLoading(true);
    try {
      const data = await listEmployees();
      setEmployees(data);
    } catch (error: any) {
      message.error(error?.message || '获取员工列表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchDependencies = async () => {
    try {
      const [deptData, accData] = await Promise.all([
        listDepartments(),
        listTenantAccounts()
      ]);
      setDepartments(deptData);
      setAccounts(accData);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchEmployees();
    fetchDependencies();
  }, []);

  const handleCreate = () => {
    setEditId(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (record: EmployeeInfo) => {
    setEditId(record.id);
    form.setFieldsValue({
      code: record.code,
      name: record.name,
      mobile: record.mobile,
      department_ids: record.department_ids,
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteEmployee(id);
      message.success('员工已删除');
      fetchEmployees();
    } catch (error: any) {
      message.error(error?.message || '删除失败');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      
      if (editId) {
        await updateEmployee(editId, values);
        message.success('员工已更新');
      } else {
        await createEmployee(values);
        message.success('员工创建成功');
      }
      
      setModalOpen(false);
      fetchEmployees();
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error?.message || '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  // Convert departments to tree data for TreeSelect
  const buildTree = (parentId?: string): any[] => {
    return departments
      .filter(d => (parentId ? d.parent_id === parentId : !d.parent_id))
      .map(d => ({
        title: d.name,
        value: d.id,
        key: d.id,
        children: buildTree(d.id),
      }));
  };
  const treeData = buildTree();

  const columns = [
    {
      title: '员工编号',
      dataIndex: 'code',
      key: 'code',
      width: 150,
    },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      width: 150,
    },
    {
      title: '联系电话',
      dataIndex: 'mobile',
      key: 'mobile',
      width: 150,
    },
    {
      title: '所属部门',
      key: 'departments',
      render: (_: any, record: EmployeeInfo) => {
        if (!record.department_ids || record.department_ids.length === 0) return '-';
        return record.department_ids.map(id => {
          const dept = departments.find(d => d.id === id);
          return dept ? <Tag key={id}>{dept.name}</Tag> : null;
        });
      },
    },
    {
      title: '状态',
      dataIndex: 'active',
      key: 'active',
      width: 100,
      render: (active: boolean) => (
        <Tag color={active ? 'success' : 'error'}>{active ? '在职' : '离职'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: any, record: EmployeeInfo) => (
        <Space>
          <a onClick={() => handleEdit(record)}>编辑</a>
          <Popconfirm
            title="确认删除"
            description={`确定要删除员工 "${record.name}" 吗？`}
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

  return (
    <PageContainer title="员工资料" ghost>
      <ProCard
        title="员工列表"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增员工
          </Button>
        }
      >
        <Table
          dataSource={employees}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={false}
          size="small"
        />
      </ProCard>

      <Modal
        title={editId ? "编辑员工" : "新增员工"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="code"
            label="员工编号"
            rules={[{ required: true, message: '请输入员工编号' }]}
          >
            <Input placeholder="请输入员工编号" />
          </Form.Item>
          
          <Form.Item
            name="name"
            label="姓名"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input placeholder="请输入姓名" />
          </Form.Item>

          <Form.Item
            name="mobile"
            label="联系电话"
          >
            <Input placeholder="请输入联系电话" />
          </Form.Item>

          <Form.Item
            name="department_ids"
            label="所属部门"
          >
            <TreeSelect
              treeData={treeData}
              treeCheckable={true}
              showCheckedStrategy={TreeSelect.SHOW_ALL}
              placeholder="请选择所属部门"
              style={{ width: '100%' }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
};

export default Employees;

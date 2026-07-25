import React, { useEffect, useState } from 'react';
import { PlusOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { ProCard, PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Form, Input, Modal, Space, Table, Tag, message, Popconfirm, TreeSelect, Tree, Transfer } from 'antd';
import { DepartmentInfo, listDepartments, createDepartment, updateDepartment, deleteDepartment, listEmployees, EmployeeInfo, updateDepartmentMembers } from '@/services/org';

const Departments: React.FC = () => {
  const [departments, setDepartments] = useState<DepartmentInfo[]>([]);
  const [employees, setEmployees] = useState<EmployeeInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);

  // Employee Selection Modal State
  const [employeeModalOpen, setEmployeeModalOpen] = useState(false);

  // Member Management Modal State
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [memberSubmitting, setMemberSubmitting] = useState(false);
  const [currentDeptId, setCurrentDeptId] = useState<string | null>(null);
  const [selectedMemberIds, setSelectedMemberIds] = useState<string[]>([]);

  const [form] = Form.useForm();

  const [tableParams, setTableParams] = useState<any>({});

  const fetchDepartments = async (params: any = {}) => {
    setLoading(true);
    try {
      const data = await listDepartments(params);
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
    fetchDepartments(tableParams);
    fetchEmployees();
  }, [tableParams]);

  const handleTableChange = (pagination: any, filters: any, sorter: any) => {
    setTableParams({
      sort_by: sorter.field || undefined,
      sort_order: sorter.order || undefined,
    });
  };

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

  const handleOpenMembers = (record: DepartmentInfo) => {
    setCurrentDeptId(record.id);
    // Find all employees that belong to this department
    const members = employees.filter(e => e.department_ids?.includes(record.id)).map(e => e.id);
    setSelectedMemberIds(members);
    setMemberModalOpen(true);
  };

  const handleMemberSubmit = async () => {
    if (!currentDeptId) return;
    try {
      setMemberSubmitting(true);
      await updateDepartmentMembers(currentDeptId, selectedMemberIds);
      message.success('成员更新成功');
      setMemberModalOpen(false);
      fetchEmployees(); // Refresh employees to reflect new department assignments
    } catch (error: any) {
      message.error(error?.message || '成员更新失败');
    } finally {
      setMemberSubmitting(false);
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
        leader_id: values.leader_id || null,
        parent_id: values.parent_id || null,
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
      sorter: true,
    },
    {
      title: '部门编号',
      dataIndex: 'code',
      key: 'code',
      width: 150,
      sorter: true,
    },
    {
      title: '负责人',
      dataIndex: 'leader_name',
      key: 'leader_name',
      width: 150,
      render: (text: string | null) => text || '-',
    },
    {
      title: '成员数',
      key: 'member_count',
      width: 100,
      render: (_: any, record: DepartmentInfo) => {
        const getAllDescendantIds = (deptId: string): string[] => {
          const children = departments.filter(d => d.parent_id === deptId).map(d => d.id);
          const descendants = children.flatMap(childId => getAllDescendantIds(childId));
          return [deptId, ...descendants];
        };
        const targetDeptIds = getAllDescendantIds(record.id);
        const count = employees.filter(e => e.department_ids?.some(id => targetDeptIds.includes(id))).length;
        
        return <Tag color="blue">{count} 人</Tag>;
      }
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
      width: 220,
      render: (_: any, record: DepartmentInfo) => (
        <Space>
          <a onClick={() => handleCreate(record.id)}>新增子部门</a>
          <a onClick={() => handleEdit(record)}>编辑</a>
          <a onClick={() => handleOpenMembers(record)}>成员管理</a>
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
      <ProTable<DepartmentInfo>
        headerTitle="部门列表"
        dataSource={treeData}
        columns={columns as any}
        rowKey="id"
        loading={loading}
        pagination={false}
        size="small"
        search={false}
        onChange={handleTableChange}
        options={{
          reload: () => { fetchDepartments(tableParams); fetchEmployees(); },
          setting: true,
          density: true,
        }}
        toolBarRender={() => [
          <Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => handleCreate()}>
            新增部门
          </Button>
        ]}
      />

      {/* Member Management Modal */}
      <Modal
        title="成员管理"
        open={memberModalOpen}
        onOk={handleMemberSubmit}
        onCancel={() => setMemberModalOpen(false)}
        confirmLoading={memberSubmitting}
        width={700}
        destroyOnClose
      >
        <Transfer
          dataSource={employees.map(e => ({ key: e.id, title: e.name, description: e.mobile || '' }))}
          showSearch
          filterOption={(inputValue, option) => option.title.indexOf(inputValue) > -1 || option.description.indexOf(inputValue) > -1}
          targetKeys={selectedMemberIds}
          onChange={(newTargetKeys) => setSelectedMemberIds(newTargetKeys as string[])}
          render={item => `${item.title} ${item.description ? `(${item.description})` : ''}`}
          listStyle={{
            width: 300,
            height: 400,
          }}
          titles={['可选成员', '已选成员']}
        />
      </Modal>

      {/* Department Edit Modal */}
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

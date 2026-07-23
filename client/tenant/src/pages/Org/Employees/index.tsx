import React, { useEffect, useState } from 'react';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { ProCard, PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Form, Input, Modal, Space, Table, Tag, message, Popconfirm, TreeSelect } from 'antd';
import { QRCodeCanvas } from 'qrcode.react';
import { EmployeeInfo, listEmployees, createEmployee, updateEmployee, deleteEmployee, listDepartments, DepartmentInfo, unbindEmployeeWx, getEmpBindQrCode, getEmpBindStatus } from '@/services/org';
import { listTenantAccounts, AccountInfo } from '@/services/tenant';

const Employees: React.FC = () => {
  const [employees, setEmployees] = useState<EmployeeInfo[]>([]);
  const [departments, setDepartments] = useState<DepartmentInfo[]>([]);
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [loading, setLoading] = useState(false);
  
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  
  const [form] = Form.useForm();
  
  const [tableParams, setTableParams] = useState<any>({});

  // WeChat Binding State
  const [bindModalOpen, setBindModalOpen] = useState(false);
  const [bindUser, setBindUser] = useState<EmployeeInfo | null>(null);
  const [qrUrl, setQrUrl] = useState('');
  const [sceneStr, setSceneStr] = useState('');
  const [polling, setPolling] = useState(false);

  const fetchEmployees = async (params: any = {}) => {
    setLoading(true);
    try {
      const data = await listEmployees(params);
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
    fetchEmployees(tableParams);
    fetchDependencies();
  }, [tableParams]);

  const handleTableChange = (pagination: any, filters: any, sorter: any) => {
    setTableParams({
      sort_by: sorter.field || undefined,
      sort_order: sorter.order || undefined,
    });
  };

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

  // Poll WeChat binding status
  useEffect(() => {
    let timer: any;
    if (bindModalOpen && sceneStr && polling) {
      timer = setInterval(async () => {
        try {
          const res = await getEmpBindStatus(sceneStr);
          if (res?.code === 200) {
            message.success('微信绑定成功');
            setBindModalOpen(false);
            setSceneStr('');
            setPolling(false);
            fetchEmployees();
          }
        } catch (error) {
          // Keep polling unless it's a hard error
        }
      }, 3000);
    }
    return () => clearInterval(timer);
  }, [bindModalOpen, sceneStr, polling]);

  const handleBindWx = async (record: EmployeeInfo) => {
    try {
      const res = await getEmpBindQrCode(record.id);
      if (res?.data) {
        setQrUrl(res.data.url);
        setSceneStr(res.data.scene_str);
        setBindUser(record);
        setBindModalOpen(true);
        setPolling(true);
      }
    } catch (error: any) {
      message.error(error?.message || '获取绑定二维码失败');
    }
  };

  const handleUnbindWx = async (record: EmployeeInfo) => {
    try {
      await unbindEmployeeWx(record.id);
      message.success('微信解绑成功');
      fetchEmployees();
    } catch (error: any) {
      message.error(error?.message || '微信解绑失败');
    }
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
      const payload = {
        ...values,
        department_ids: values.department_ids || [],
      };

      if (editId) {
        await updateEmployee(editId, payload);
        message.success('员工已更新');
      } else {
        await createEmployee(payload);
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
      sorter: true,
    },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      width: 150,
      sorter: true,
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
        
        // Only show the highest level departments among the selected ones
        const topLevelIds = record.department_ids.filter(id => {
          const dept = departments.find(d => d.id === id);
          if (!dept || !dept.parent_id) return true;
          // If parent is also in the selected list, this is not a top-level selection
          return !record.department_ids!.includes(dept.parent_id);
        });

        return topLevelIds.map(id => {
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
      title: '微信绑定',
      key: 'wx_bind',
      width: 100,
      render: (_: any, record: EmployeeInfo) => (
        record.wx_user_id ? (
          <Tag color="success">已绑定</Tag>
        ) : (
          <Tag color="default">未绑定</Tag>
        )
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 250,
      render: (_: any, record: EmployeeInfo) => (
        <Space>
          <a onClick={() => handleEdit(record)}>编辑</a>
          {record.wx_user_id ? (
            <Popconfirm
              title="确认解绑"
              description={`确定要解绑员工 "${record.name}" 的微信吗？`}
              onConfirm={() => handleUnbindWx(record)}
              okText="确认"
              cancelText="取消"
            >
              <a style={{ color: '#ff4d4f' }}>解绑微信</a>
            </Popconfirm>
          ) : (
            <a onClick={() => handleBindWx(record)}>绑定微信</a>
          )}
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
      <ProTable<EmployeeInfo>
        headerTitle="员工列表"
        dataSource={employees}
        columns={columns as any}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
        size="small"
        search={false}
        onChange={handleTableChange}
        options={{
          reload: () => { fetchEmployees(tableParams); fetchDependencies(); },
          setting: true,
          density: true,
        }}
        toolBarRender={() => [
          <Button key="create" type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增员工
          </Button>
        ]}
      />

      {/* 微信绑定弹窗 */}
      <Modal
        title="绑定微信"
        open={bindModalOpen}
        onCancel={() => {
          setBindModalOpen(false);
          setSceneStr('');
          setBindUser(null);
          setPolling(false);
        }}
        footer={null}
        width={400}
      >
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          {qrUrl ? (
            <>
              <QRCodeCanvas value={qrUrl} size={200} />
              <div style={{ marginTop: 16, color: '#666' }}>
                请使用微信扫一扫绑定此员工
                <br />
                {bindUser?.name}
              </div>
            </>
          ) : (
            <div>二维码加载中...</div>
          )}
        </div>
      </Modal>

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
              showCheckedStrategy={TreeSelect.SHOW_PARENT}
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

import { EditOutlined } from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Button, Descriptions, Form, Input, message, Modal, Typography } from 'antd';
import { useEffect, useState } from 'react';

import { getCurrentTenant, updateCurrentTenant, type TenantInfo } from '@/services/tenant';

const TenantInfoPage = () => {
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const fetchTenant = async () => {
    setLoading(true);
    try {
      const data = await getCurrentTenant();
      setTenant(data);
    } catch (error: any) {
      const detail = error?.data?.detail || '获取公司信息失败';
      message.error(String(detail));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTenant();
  }, []);

  const handleEdit = () => {
    if (!tenant) return;
    form.setFieldsValue({
      name: tenant.name,
      host: tenant.host,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await updateCurrentTenant({
        name: values.name,
        host: values.host,
      });
      message.success('公司信息更新成功');
      setModalOpen(false);
      await fetchTenant();
    } catch (error: any) {
      if (error?.errorFields) {
        return;
      }
      const detail = error?.data?.detail || '更新失败，请重试';
      message.error(String(detail));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PageContainer title="公司信息" ghost>
      <ProCard
        loading={loading}
        extra={
          <Button type="primary" icon={<EditOutlined />} onClick={handleEdit}>
            编辑
          </Button>
        }
        style={{ maxWidth: 680, margin: '0 auto' }}
      >
        {tenant ? (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="公司编码">{tenant.code}</Descriptions.Item>
            <Descriptions.Item label="公司名称">{tenant.name}</Descriptions.Item>
            <Descriptions.Item label="域名">{tenant.host}</Descriptions.Item>
            <Descriptions.Item label="状态">
              {tenant.active ? '启用' : '禁用'}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Typography.Text type="secondary">暂无公司信息</Typography.Text>
        )}
      </ProCard>

      <Modal
        title="编辑公司信息"
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => {
          setModalOpen(false);
          form.resetFields();
        }}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="公司名称"
            rules={[{ required: true, message: '请输入公司名称' }]}
          >
            <Input placeholder="请输入公司名称" />
          </Form.Item>
          <Form.Item
            name="host"
            label="域名"
            rules={[{ required: true, message: '请输入域名' }]}
          >
            <Input placeholder="请输入域名" />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
};

export default TenantInfoPage;

import { PageContainer, ProCard, ProForm, ProFormText } from '@ant-design/pro-components';
import { Button, Descriptions, message, Space } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { useEffect, useState } from 'react';

import {
  getCurrentTenant,
  updateCurrentTenant,
  type TenantInfo,
} from '@/services/tenant';

const TenantPage = () => {
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [isEdit, setIsEdit] = useState(false);

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

  const handleFinish = async (values: any) => {
    try {
      await updateCurrentTenant({
        name: values.name,
        mqtt_server: values.mqtt_server,
        api_server: values.api_server,
      });
      message.success('公司信息更新成功');
      setIsEdit(false);
      fetchTenant();
      return true;
    } catch (error: any) {
      if (error?.errorFields) return false;
      const detail = error?.data?.detail || '更新公司信息失败';
      message.error(String(detail));
      return false;
    }
  };

  return (
    <PageContainer title="公司信息" ghost>
      <ProCard 
        loading={loading}
        title={!isEdit && "基本资料"}
        extra={
          !isEdit && (
            <Button type="primary" icon={<EditOutlined />} onClick={() => setIsEdit(true)}>
              编辑信息
            </Button>
          )
        }
      >
        {tenant && !isEdit && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="公司编码">{tenant.code}</Descriptions.Item>
            <Descriptions.Item label="公司名称">{tenant.name}</Descriptions.Item>
            <Descriptions.Item label="MQTT 服务器">{tenant.mqtt_server || '-'}</Descriptions.Item>
            <Descriptions.Item label="API 服务器">{tenant.api_server || '-'}</Descriptions.Item>
          </Descriptions>
        )}

        {tenant && isEdit && (
          <ProForm
            onFinish={handleFinish}
            initialValues={tenant}
            submitter={{
              render: (props, dom) => (
                <Space>
                  {dom[1]}
                  <Button onClick={() => setIsEdit(false)}>取消</Button>
                </Space>
              ),
              searchConfig: {
                submitText: '保存修改',
              },
            }}
            layout="vertical"
          >
            <ProFormText
              name="code"
              label="公司编码"
              disabled
              tooltip="公司编码系统自动生成，不可修改"
            />
            
            <ProFormText
              name="name"
              label="公司名称"
              rules={[{ required: true, message: '请输入公司名称' }]}
            />
            
            <ProFormText
              name="mqtt_server"
              label="MQTT 服务器"
              placeholder="例如: tcp://mqtt.example.com:1883"
            />

            <ProFormText
              name="api_server"
              label="API 服务器"
              placeholder="例如: https://api.example.com"
            />
          </ProForm>
        )}
      </ProCard>
    </PageContainer>
  );
};

export default TenantPage;

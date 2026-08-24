import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormText,
  ProFormSwitch,
  ProFormCascader,
  ProTable,
  ProFormSelect,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Switch, message } from 'antd';

import { getRegionTree } from '@/services/region';
import {
  Tenant,
  TenantPayload,
  createTenant,
  deleteTenant,
  listTenants,
  updateTenant,
} from '@/services/tenant';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const TenantPage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<Tenant[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<Tenant | null>(null);
  const [regionTree, setRegionTree] = useState<any[]>([]);

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listTenants());
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRows();
    getRegionTree().then(setRegionTree).catch(() => message.error('获取地区信息失败'));
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return (Array.isArray(rows) ? rows : []).filter((row) => {
      if (query.code && !norm(row.code).includes(norm(query.code))) {
        return false;
      }
      if (query.name && !norm(row.name).includes(norm(query.name))) {
        return false;
      }
      if (query.mqtt_server && !norm(row.mqtt_server).includes(norm(query.mqtt_server))) {
        return false;
      }
      if (query.api_server && !norm(row.api_server).includes(norm(query.api_server))) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<Tenant>[] = [
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
      width: 120,
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 200,
    },
    {
      title: '业务场景',
      dataIndex: 'remark',
      width: 200,
      hideInSearch: true,
      ellipsis: true,
    },
    {
      title: '所在地区',
      dataIndex: 'region_id',
      width: 150,
      renderText: (val: string) => {
        if (!val) return '-';
        for (const prov of regionTree) {
          if (prov.value === val) return prov.label;
          if (prov.children) {
            for (const city of prov.children) {
              if (city.value === val) return `${prov.label} / ${city.label}`;
            }
          }
        }
        return val;
      },
    },
    {
      title: 'MQTT 服务器',
      dataIndex: 'mqtt_server',
      width: 200,
    },
    {
      title: 'API 服务器',
      dataIndex: 'api_server',
      width: 200,
    },
    {
      title: '状态',
      dataIndex: 'active',
      width: 80,
      valueType: 'select',
      valueEnum: {
        true: { text: '启用', status: 'Success' },
        false: { text: '停用', status: 'Error' },
      },
      render: (_, row) => (
        <Switch
          checked={row.active}
          checkedChildren="启用"
          unCheckedChildren="停用"
          onChange={async (checked) => {
            try {
              await updateTenant(row.id, { active: checked });
              message.success('更新成功');
              await loadRows();
            } catch (error) {
              message.error(toErrorMessage(error));
            }
          }}
        />
      ),
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      width: 180,
    },
    {
      title: '邮件状态',
      dataIndex: 'email_status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        0: { text: '默认', status: 'Default' },
        1: { text: '已送达', status: 'Success' },
        2: { text: '已打开', status: 'Processing' },
      },
    },
    {
      title: '业务状态',
      dataIndex: 'status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        1: { text: '正常', status: 'Success' },
        0: { text: '异常/停用', status: 'Error' },
      },
    },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 100,
    },
    {
      title: '操作',
      valueType: 'option',
      // fixed: 'right',
      width: 160,
      render: (_, row) => [
        <a
          key="edit"
          onClick={() => {
            setEditing(row);
            setModalOpen(true);
          }}
        >
          编辑
        </a>,
        <Popconfirm
          key="delete"
          title="确认删除该租户吗？"
          onConfirm={async () => {
            try {
              await deleteTenant(row.id);
              message.success('删除成功');
              await loadRows();
            } catch (error) {
              message.error(toErrorMessage(error));
            }
          }}
        >
          <a style={{ color: 'red' }}>
            删除
          </a>
        </Popconfirm>,
      ],
    },
  ];

  return (
    <PageContainer
      title="租户管理"
      subTitle="管理系统中的所有租户"
    >
      <ProTable<Tenant>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        scroll={{ x: 800 }}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadRows }}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            新建租户
          </Button>,
        ]}
      />

      <ModalForm<TenantPayload>
        title={editing ? '编辑租户' : '新建租户'}
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
                mqtt_server: editing.mqtt_server,
                api_server: editing.api_server,
                region_id: (() => {
                  for (const prov of regionTree) {
                    if (prov.children) {
                      for (const city of prov.children) {
                        if (city.value === editing.region_id) {
                          return [prov.value, city.value];
                        }
                      }
                    }
                    if (prov.value === editing.region_id) return [prov.value];
                  }
                  return [editing.region_id];
                })(),
                active: editing.active,
                email: editing.email,
                status: editing.status,
                industry: editing.industry,
                remark: editing.remark,
              }
            : { active: true, mqtt_server: 'mqtt.api-server.icu', api_server: 'api.api-server.icu', status: 1 }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: TenantPayload = {
              code: values.code.trim(),
              name: values.name.trim(),
              mqtt_server: values.mqtt_server.trim(),
              api_server: values.api_server.trim(),
              region_id: Array.isArray(values.region_id) ? values.region_id[values.region_id.length - 1] : values.region_id,
              active: values.active,
              email: values.email?.trim(),
              status: values.status,
              industry: values.industry ? Number(values.industry) : undefined,
              remark: values.remark?.trim(),
            };

            if (editing) {
              await updateTenant(editing.id, payload);
              message.success('更新成功');
            } else {
              await createTenant(payload);
              message.success('创建成功');
            }
            setModalOpen(false);
            setEditing(null);
            await loadRows();
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
            { required: true, message: '请输入租户编码' },
            { max: 12, message: '编码最多12个字符' },
          ]}
        />
        <ProFormText
          name="name"
          label="名称"
          rules={[
            { required: true, message: '请输入租户名称' },
            { max: 64, message: '名称最多64个字符' },
          ]}
        />
        <ProFormText
          name="mqtt_server"
          label="MQTT 服务器"
          rules={[
            { required: true, message: '请输入 MQTT 服务器地址' },
            { max: 255, message: '地址最多255个字符' },
          ]}
        />
        <ProFormText
          name="api_server"
          label="API 服务器"
          rules={[
            { required: true, message: '请输入 API 服务器地址' },
            { max: 255, message: '地址最多255个字符' },
          ]}
        />
        <ProFormCascader
          name="region_id"
          label="省市"
          rules={[{ required: true, message: '请选择省市' }]}
          fieldProps={{
            options: regionTree,
            changeOnSelect: true,
          }}
        />
        <ProFormText
          name="email"
          label="联系邮箱"
          rules={[{ type: 'email', message: '请输入有效的邮箱地址' }]}
        />
        <ProFormSelect
          name="status"
          label="业务状态"
          options={[
            { label: '正常', value: 1 },
            { label: '停用', value: 0 },
          ]}
        />
        <ProFormText
          name="industry"
          label="行业代码"
        />
        <ProFormText
          name="remark"
          label="业务场景"
        />
        <ProFormSwitch name="active" label="系统状态" />
      </ModalForm>
    </PageContainer>
  );
};

export default TenantPage;

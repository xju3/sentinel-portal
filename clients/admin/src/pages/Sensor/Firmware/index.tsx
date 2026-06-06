import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDatePicker,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Tag, Upload, message } from 'antd';
import { UploadOutlined } from '@ant-design/icons';

import {
  SensorFirmware,
  SensorFirmwarePayload,
  createSensorFirmware,
  deleteSensorFirmware,
  querySensorFirmwareList,
  updateSensorFirmware,
  getPresignedUploadUrl,
  PresignedUploadResponse,
  releaseSensorFirmware,
} from '@/services/sensorFirmware';
import { listSensorTypes, SensorType } from '@/services/sensorType';
import { listTenants, Tenant } from '@/services/tenant';

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const SensorFirmwarePage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<SensorFirmware[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<SensorFirmware | null>(null);

  const [sensorTypes, setSensorTypes] = useState<SensorType[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<PresignedUploadResponse | null>(null);
  const [formVersion, setFormVersion] = useState('');

  const sensorTypeMap = useMemo(() => {
    const map = new Map<string, string>();
    sensorTypes.forEach((t) => map.set(t.id, t.name));
    return map;
  }, [sensorTypes]);

  const tenantMap = useMemo(() => {
    const map = new Map<string, string>();
    tenants.forEach((t) => map.set(t.id, t.name));
    return map;
  }, [tenants]);

  const sensorTypeOptions = useMemo(
    () => sensorTypes.map((t) => ({ label: t.name, value: t.id })),
    [sensorTypes],
  );

  const tenantOptions = useMemo(
    () => tenants.map((t) => ({ label: t.name, value: t.id })),
    [tenants],
  );

  const loadRows = async () => {
    setLoading(true);
    try {
      const res = await querySensorFirmwareList();
      const data = (res as any)?.data ?? res;
      setRows(Array.isArray(data) ? data : []);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const loadOptions = async () => {
    try {
      const [typesRes, tenantRes] = await Promise.all([
        listSensorTypes(),
        listTenants(),
      ]);
      const types = (typesRes as any)?.data ?? typesRes;
      const tenantList = (tenantRes as any)?.data ?? tenantRes;
      setSensorTypes(Array.isArray(types) ? types : []);
      setTenants(Array.isArray(tenantList) ? tenantList : []);
    } catch (error) {
      message.error(toErrorMessage(error));
    }
  };

  useEffect(() => {
    loadRows();
    loadOptions();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.version && !norm(row.version).includes(norm(query.version))) {
        return false;
      }
      if (query.status !== undefined && query.status !== '' && row.status !== Number(query.status)) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const doUploadFile = async (version: string, file: File): Promise<PresignedUploadResponse | null> => {
    setUploading(true);
    try {
      // 1. Get presigned upload URL from backend
      const res = await getPresignedUploadUrl(version, file.name);
      const uploadInfo = (res as any)?.data ?? res;

      // 2. Upload file directly to MinIO using the presigned URL
      const uploadRes = await fetch(uploadInfo.presigned_url, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
      });

      if (!uploadRes.ok) {
        throw new Error(`Upload failed with status ${uploadRes.status}`);
      }

      message.success('文件上传成功');
      return uploadInfo;
    } catch (error) {
      message.error(toErrorMessage(error));
      return null;
    } finally {
      setUploading(false);
    }
  };

  const handleModalOpen = (record: SensorFirmware | null) => {
    setEditing(record);
    setUploadFile(null);
    setUploadResult(null);
    setFormVersion(record?.version || '');
    setModalOpen(true);
  };

  const handleModalCancel = () => {
    setModalOpen(false);
    setEditing(null);
    setUploadFile(null);
    setUploadResult(null);
    setFormVersion('');
  };

  const columns: ProColumns<SensorFirmware>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '版本号',
      dataIndex: 'version',
      width: 160,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '发布日期',
      dataIndex: 'release_date',
      width: 120,
      hideInSearch: true,
      render: (_, row) => (row.release_date ? row.release_date.split('T')[0] : '-'),
    },
    {
      title: '文件地址',
      dataIndex: 'file_url',
      width: 200,
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => (
        <a href={row.file_url} target="_blank" rel="noopener noreferrer">
          {row.file_url}
        </a>
      ),
    },
    {
      title: '传感器类型',
      dataIndex: 'sensor_type_id',
      width: 160,
      hideInSearch: true,
      render: (_, row) => sensorTypeMap.get(row.sensor_type_id) || row.sensor_type_id || '-',
    },
    {
      title: '租户',
      dataIndex: 'tenant_id',
      width: 160,
      hideInSearch: true,
      render: (_, row) =>
        row.tenant_id ? tenantMap.get(row.tenant_id) || row.tenant_id : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      valueEnum: {
        0: { text: '禁用', status: 'Default' },
        1: { text: '启用', status: 'Success' },
      },
      render: (_, row) =>
        row.status === 1 ? (
          <Tag color="green">启用</Tag>
        ) : (
          <Tag color="default">禁用</Tag>
        ),
    },
    {
      title: '操作',
      valueType: 'option',
      width: 220,
      render: (_, row) => [
        <Button
          key="edit"
          type="link"
          disabled={row.status === 1}
          onClick={() => handleModalOpen(row)}
        >
          编辑
        </Button>,
        row.status === 0 ? (
          <Popconfirm
            key="release"
            title="确认发布该固件吗？发布后将不可修改"
            onConfirm={async () => {
              try {
                await releaseSensorFirmware(row.id);
                message.success('发布成功');
                await loadRows();
              } catch (error) {
                message.error(toErrorMessage(error));
              }
            }}
          >
            <Button type="link">发布</Button>
          </Popconfirm>
        ) : null,
        <Popconfirm
          key="delete"
          title="确认删除该固件记录吗？"
          onConfirm={async () => {
            try {
              await deleteSensorFirmware(row.id);
              message.success('删除成功');
              await loadRows();
            } catch (error) {
              message.error(toErrorMessage(error));
            }
          }}
        >
          <Button danger type="link" disabled={row.status === 1}>
            删除
          </Button>
        </Popconfirm>,
      ],
    },
  ];

  return (
    <PageContainer
      title="传感器固件管理"
      subTitle="管理所有传感器固件版本"
    >
      <ProTable<SensorFirmware>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        scroll={{ x: 1200 }}
        search={{
          labelWidth: 'auto',
          defaultCollapsed: false,
        }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadRows }}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => handleModalOpen(null)}
          >
            新建固件
          </Button>,
        ]}
      />

      <ModalForm<SensorFirmwarePayload>
        title={editing ? '编辑传感器固件' : '新建传感器固件'}
        open={modalOpen}
        modalProps={{
          destroyOnHidden: true,
          onCancel: handleModalCancel,
          width: 640,
        }}
        submitter={{
          submitButtonProps: {
            loading: saving,
            disabled: editing ? false : !uploadResult,
          },
          searchConfig: { submitText: '保存' },
        }}
        initialValues={
          editing
            ? {
                version: editing.version,
                description: editing.description,
                release_date: editing.release_date,
                file_url: editing.file_url,
                sensor_type_id: editing.sensor_type_id,
                tenant_id: editing.tenant_id,
                status: editing.status,
              }
            : {
                status: 1,
              }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload: SensorFirmwarePayload = {
              version: values.version?.trim(),
              description: values.description?.trim(),
              release_date: values.release_date,
              file_url: editing ? editing.file_url : uploadResult?.file_url || values.file_url,
              sensor_type_id: values.sensor_type_id,
              tenant_id: values.tenant_id,
              status: Number(values.status ?? 1),
            };

            if (editing) {
              await updateSensorFirmware(editing.id, payload);
              message.success('更新成功');
            } else {
              await createSensorFirmware(payload);
              message.success('创建成功');
            }
            handleModalCancel();
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
          name="version"
          label="版本号"
          rules={[
            { required: true, message: '请输入固件版本号' },
            { max: 64, message: '版本号最多64个字符' },
          ]}
          fieldProps={{
            onChange: (e) => setFormVersion(e.target.value),
            disabled: !!editing,
          }}
        />
        <ProFormTextArea
          name="description"
          label="描述"
        />
        <ProFormDatePicker
          name="release_date"
          label="发布日期"
        />
        <ProFormSelect
          name="sensor_type_id"
          label="传感器类型"
          options={sensorTypeOptions}
          rules={[{ required: true, message: '请选择传感器类型' }]}
          showSearch
          placeholder="请搜索或选择传感器类型"
        />
        <ProFormSelect
          name="tenant_id"
          label="租户"
          options={tenantOptions}
          placeholder="请选择租户（可选）"
          allowClear
          showSearch
        />
        <ProFormSelect
          name="status"
          label="状态"
          options={[
            { label: '启用', value: 1 },
            { label: '禁用', value: 0 },
          ]}
          rules={[{ required: true, message: '请选择状态' }]}
        />
        {/* File upload section */}
        {editing ? (
          <ProFormText
            name="file_url"
            label="文件地址"
            rules={[{ max: 255, message: '文件地址最多255个字符' }]}
          />
        ) : (
          <>
            {/* Hidden field to store file_url value */}
            <ProFormText
              name="file_url"
              label="文件地址"
              hidden
            />
            <div style={{ marginBottom: 24 }}>
              <div style={{ marginBottom: 8, fontWeight: 500, color: 'rgba(0,0,0,0.88)' }}>固件文件</div>
              <Upload.Dragger
                accept=".bin,.hex,.zip,.tar.gz"
                showUploadList={true}
                beforeUpload={(file) => {
                  setUploadFile(file);
                  return false;
                }}
                fileList={uploadFile ? ([uploadFile] as any) : []}
                onRemove={() => {
                  setUploadFile(null);
                  setUploadResult(null);
                }}
                disabled={!formVersion}
              >
                <p className="ant-upload-drag-icon">
                  <UploadOutlined />
                </p>
                <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
                <p className="ant-upload-hint">
                  {formVersion
                    ? `文件将上传至 oat/${formVersion}/ 目录`
                    : '请先填写版本号'}
                </p>
              </Upload.Dragger>
            </div>
            {uploadFile && formVersion && (
              <div style={{ marginBottom: 24 }}>
                <Button
                  type="primary"
                  loading={uploading}
                  icon={<UploadOutlined />}
                  onClick={async () => {
                    const result = await doUploadFile(formVersion, uploadFile!);
                    if (result) {
                      setUploadResult(result);
                    }
                  }}
                  disabled={!!uploadResult}
                >
                  {uploadResult ? '已上传' : '上传到 MinIO'}
                </Button>
                {uploadResult && (
                  <Tag color="green" style={{ marginLeft: 8 }}>
                    上传完成: {uploadResult.file_url}
                  </Tag>
                )}
              </div>
            )}
          </>
        )}
      </ModalForm>
    </PageContainer>
  );
};

export default SensorFirmwarePage;

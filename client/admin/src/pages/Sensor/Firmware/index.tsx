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
import { Button, Popconfirm, Row, Col, Tag, Upload, message, Space, Typography, Form } from 'antd';
import { UploadOutlined, InboxOutlined, LinkOutlined } from '@ant-design/icons';

import {
  SensorFirmware,
  SensorFirmwarePayload,
  createSensorFirmware,
  deleteSensorFirmware,
  querySensorFirmwareList,
  updateSensorFirmware,
  getPresignedUploadUrl,
  uploadFirmwareDirect,
  PresignedUploadResponse,
  releaseSensorFirmware,
} from '@/services/sensorFirmware';
import { listSensorTypes, SensorType } from '@/services/sensorType';
import { listTenants, Tenant } from '@/services/tenant';
import EntityPicker from '@/components/EntityPicker';

const { Text, Paragraph } = Typography;

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

const SensorFirmwarePage = () => {
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<SensorFirmware[]>([]);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [editing, setEditing] = useState<SensorFirmware | null>(null);

  const [sensorTypes, setSensorTypes] = useState<SensorType[]>([]);

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<PresignedUploadResponse | null>(null);
  const [formVersion, setFormVersion] = useState('');
  const [replaceFile, setReplaceFile] = useState(false);

  const sensorTypeMap = useMemo(() => {
    const map = new Map<string, string>();
    sensorTypes.forEach((t) => map.set(t.id, t.name));
    return map;
  }, [sensorTypes]);

  const sensorTypeOptions = useMemo(
    () => sensorTypes.map((t) => ({ label: t.name, value: t.id })),
    [sensorTypes],
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
      const [typesRes] = await Promise.all([
        listSensorTypes(),
      ]);
      const types = (typesRes as any)?.data ?? typesRes;
      setSensorTypes(Array.isArray(types) ? types : []);
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
      // Upload file directly to backend proxy to avoid CORS and mixed-content issues
      const res = await uploadFirmwareDirect(version, file);
      const uploadInfo = (res as any)?.data ?? res;

      message.success('文件上传成功');
      return {
        presigned_url: '', // No longer used but kept for type compatibility
        file_url: uploadInfo.file_url,
        object_name: uploadInfo.object_name,
      };
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
    setReplaceFile(false);
    setModalOpen(true);
  };

  const handleModalCancel = () => {
    setModalOpen(false);
    setEditing(null);
    setUploadFile(null);
    setUploadResult(null);
    setFormVersion('');
    setReplaceFile(false);
  };

  const getEffectiveFileUrl = () => {
    if (!editing) {
      return uploadResult?.file_url || '';
    }
    // Editing mode: use new upload result if available, otherwise keep original
    return uploadResult?.file_url || editing.file_url;
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
      width: 80,
    },
    {
      title: '文件',
      dataIndex: 'file_url',
      width: 100,
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => (
        <a href={row.file_url} target="_blank" rel="noopener noreferrer">
          <LinkOutlined style={{ marginRight: 4 }} />
          {row.file_url.split('/').pop() || row.file_url}
        </a>
      ),
    },
    {
      title: '传感器类型',
      dataIndex: 'sensor_type_id',
      width: 120,
      hideInSearch: true,
      render: (_, row) => sensorTypeMap.get(row.sensor_type_id) || row.sensor_type_id || '-',
    },
    {
      title: '租户',
      dataIndex: 'tenant_id',
      width: 200,
      hideInSearch: true,
      render: (_, row) =>
        row.tenant?.name || (row.tenant_id ? row.tenant_id.replace(/-/g, '') : '-'),
    },
    {
      title: '发布日期',
      dataIndex: 'release_date',
      width: 100,
      hideInSearch: true,
      render: (_, row) => (row.release_date ? row.release_date.split('T')[0] : '-'),
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
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '操作',
      valueType: 'option',
      fixed: 'right',
      width: 120,
      render: (_, row) => [
        <a
          key="edit"
          style={row.status === 1 ? { color: 'rgba(0,0,0,0.25)', pointerEvents: 'none' } : {}}
          onClick={() => handleModalOpen(row)}
        >
          编辑
        </a>,
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
            <a style={{ color: '#1677ff' }}>发布</a>
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
          <a style={row.status === 1 ? { color: 'rgba(0,0,0,0.25)', pointerEvents: 'none' } : { color: 'red' }}>
            删除
          </a>
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
          width: 720,
        }}
        layout="horizontal"
        labelCol={{ span: 7 }}
        wrapperCol={{ span: 17 }}
        submitter={{
          submitButtonProps: {
            loading: saving,
            disabled: editing ? (replaceFile && !uploadResult ? true : false) : !uploadResult,
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
              file_url: getEffectiveFileUrl(),
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
          tooltip={editing ? '创建后版本号不可修改' : undefined}
          rules={[
            { required: true, message: '请输入固件版本号' },
            { max: 64, message: '版本号最多64个字符' },
          ]}
          fieldProps={{
            onChange: (e) => setFormVersion(e.target.value),
            disabled: !!editing,
            addonAfter: editing ? (
              <Tag color="default" style={{ marginRight: 0, border: 'none', background: 'transparent' }}>
                不可修改
              </Tag>
            ) : undefined,
          }}
        />

        {/* ===== File Section ===== */}
        <ProFormText
          name="file_url"
          label="文件地址"
          hidden
        />

        {editing && !replaceFile ? (
          // === EDIT MODE: Show current file with option to replace ===
          <Row style={{ marginBottom: 24 }}>
            <Col span={7} style={{ textAlign: 'right', paddingRight: 8 }}>
              <div style={{ fontWeight: 500, padding: '5px 0', color: 'rgba(0,0,0,0.88)' }}>当前文件</div>
            </Col>
            <Col span={17}>
              <div
                style={{
                  padding: '12px 16px',
                  background: '#fafafa',
                  borderRadius: 6,
                  border: '1px solid #d9d9d9',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <Space>
                  <LinkOutlined style={{ color: '#1677ff' }} />
                  <a href={editing.file_url} target="_blank" rel="noopener noreferrer">
                    {editing.file_url.split('/').pop() || editing.file_url}
                  </a>
                </Space>
                <Button
                  size="small"
                  icon={<UploadOutlined />}
                  onClick={() => setReplaceFile(true)}
                >
                  替换文件
                </Button>
              </div>
            </Col>
          </Row>
        ) : (
          // === CREATE MODE / REPLACE MODE: Upload dragger + upload button ===
          <>
            <Row style={{ marginBottom: 24 }}>
              <Col span={7} style={{ textAlign: 'right', paddingRight: 8 }}>
                <div style={{ fontWeight: 500, padding: '5px 0', color: 'rgba(0,0,0,0.88)' }}>
                  固件文件
                  {editing && (
                    <Tag
                      color="blue"
                      style={{ marginLeft: 8, cursor: 'pointer' }}
                      onClick={() => {
                        setReplaceFile(false);
                        setUploadFile(null);
                        setUploadResult(null);
                      }}
                    >
                      取消替换
                    </Tag>
                  )}
                </div>
              </Col>
              <Col span={17}>
                <Upload
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
                  <Button
                    icon={<UploadOutlined />}
                    disabled={!formVersion}
                  >
                    选择固件文件
                  </Button>
                </Upload>
                {!formVersion && (
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                    请先填写版本号
                  </Text>
                )}
              </Col>
            </Row>

            {uploadFile && (
              <Row style={{ marginBottom: 24 }}>
                <Col span={7}></Col>
                <Col span={17}>
                  <div
                    style={{
                      padding: '8px 12px',
                      background: '#f6ffed',
                      borderRadius: 6,
                      border: '1px solid #b7eb8f',
                    }}
                  >
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Space>
                        <Text strong>已选择文件：</Text>
                        <Text>{uploadFile.name}</Text>
                        <Text type="secondary">({formatFileSize(uploadFile.size)})</Text>
                      </Space>
                      <Space>
                        <Button
                          type="primary"
                          loading={uploading}
                          icon={<UploadOutlined />}
                          disabled={!!uploadResult}
                          onClick={async () => {
                            const result = await doUploadFile(formVersion, uploadFile);
                            if (result) {
                              setUploadResult(result);
                            }
                          }}
                        >
                          {uploading ? '上传中...' : uploadResult ? '已上传' : '上传到 MinIO'}
                        </Button>
                        {uploadResult && (
                          <Tag color="success" style={{ marginLeft: 4 }}>
                            上传完成
                          </Tag>
                        )}
                      </Space>
                      {uploadResult && (
                        <div>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            存储路径: {uploadResult.object_name}
                          </Text>
                        </div>
                      )}
                    </Space>
                  </div>
                </Col>
              </Row>
            )}
          </>
        )}

        <ProFormSelect
          name="sensor_type_id"
          label="传感器类型"
          options={sensorTypeOptions}
          rules={[{ required: true, message: '请选择传感器类型' }]}
          showSearch
          placeholder="请搜索或选择传感器类型"
        />
        <Form.Item name="tenant_id" label="租户">
          <EntityPicker<Tenant>
            modalTitle="选择租户"
            fetcher={async (query) => {
              const res = await listTenants(0, 1000, true);
              let items = (res as any)?.data ?? res ?? [];
              if (query.keyword) {
                items = items.filter((t: any) => t.name.includes(query.keyword) || t.code.includes(query.keyword));
              }
              const total = items.length;
              items = items.slice((query.current - 1) * query.pageSize, query.current * query.pageSize);
              return { items, total };
            }}
            columns={[
              { title: '租户名称', dataIndex: 'name' },
              { title: '租户编码', dataIndex: 'code' },
            ]}
            getRecordLabel={(t) => t.name}
            valueLabel={editing?.tenant?.name}
            placeholder="请选择租户（可选）"
          />
        </Form.Item>
        <ProFormDatePicker
          name="release_date"
          label="发布日期"
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
        <ProFormTextArea
          name="description"
          label="描述"
          fieldProps={{ rows: 3 }}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default SensorFirmwarePage;

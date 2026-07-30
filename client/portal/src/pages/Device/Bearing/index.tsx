import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormDigit,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Popconfirm, Space, Tag, message } from 'antd';

import {
  BearingModel,
  BearingModelPayload,
  BEARING_TYPE_OPTIONS,
  createBearing,
  deleteBearing,
  getBearingTypeLabel,
  listAllBearings,
  updateBearing,
} from '@/services/bearing';
import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

type BearingFormValues = BearingModelPayload;

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | {
      data?: { detail?: string };
      info?: { errorMessage?: string };
      message?: string;
    }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const BearingPage = () => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<BearingModel | null>(null);
  const [rows, setRows] = useState<BearingModel[]>([]);
  const [query, setQuery] = useState<Record<string, unknown>>({});

  const loadRows = async () => {
    setLoading(true);
    try {
      setRows(await listAllBearings());
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRows();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (value: unknown) => String(value ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      if (query.brand && !norm(row.brand).includes(norm(query.brand))) {
        return false;
      }
      if (query.model && !norm(row.model).includes(norm(query.model))) {
        return false;
      }
      if (
        query.bearing_type &&
        !norm(row.bearing_type).includes(norm(query.bearing_type))
      ) {
        return false;
      }
      if (
        query.active !== undefined &&
        query.active !== null &&
        row.active !== query.active
      ) {
        return false;
      }
      return true;
    });
  }, [query, rows]);

  const columns: ProColumns<BearingModel>[] = [
    {
      title: '序号',
      valueType: 'indexBorder',
      width: 68,
      hideInSearch: true,
      fixed: 'left',
    },
    {
      title: '轴承类型',
      dataIndex: 'bearing_type',
      width: 140,
      valueEnum: Object.fromEntries(
        BEARING_TYPE_OPTIONS.map((option) => [
          option.value,
          { text: option.label },
        ]),
      ),
      render: (_, row) => getBearingTypeLabel(row.bearing_type),
    },
    {
      title: '品牌',
      dataIndex: 'brand',
      width: 140,
      sorter: (a, b) => a.brand.localeCompare(b.brand, 'zh-CN'),
    },
    {
      title: '型号',
      dataIndex: 'model',
      width: 160,
      sorter: (a, b) => a.model.localeCompare(b.model, 'zh-CN'),
    },

    {
      title: '滚动体数量',
      dataIndex: 'rolling_element_count',
      width: 110,
      hideInSearch: true,
      sorter: (a, b) => a.rolling_element_count - b.rolling_element_count,
    },
    {
      title: '滚动体直径(mm)',
      dataIndex: 'rolling_element_diameter_mm',
      width: 140,
      hideInSearch: true,
      sorter: (a, b) =>
        a.rolling_element_diameter_mm - b.rolling_element_diameter_mm,
    },
    {
      title: '节圆直径(mm)',
      dataIndex: 'pitch_diameter_mm',
      width: 130,
      hideInSearch: true,
      sorter: (a, b) => a.pitch_diameter_mm - b.pitch_diameter_mm,
    },
    {
      title: '接触角(°)',
      dataIndex: 'contact_angle_deg',
      width: 100,
      hideInSearch: true,
      sorter: (a, b) => a.contact_angle_deg - b.contact_angle_deg,
    },
    {
      title: '状态',
      dataIndex: 'active',
      width: 90,
      valueEnum: {
        true: { text: '启用' },
        false: { text: '停用' },
      },
      render: (_, row) =>
        row.active ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '备注',
      dataIndex: 'description',
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '操作',
      valueType: 'option',
      width: OPERATION_COL_WIDTH,
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="middle">
          <a
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            title="确认删除该轴承型号吗？"
            description="已被设备规格引用的轴承型号不能删除。"
            onConfirm={async () => {
              try {
                await deleteBearing(row.id);
                message.success('删除成功');
                await loadRows();
              } catch (error) {
                message.error(toErrorMessage(error));
              }
            }}
          >
            <a style={{ color: '#ff4d4f' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageContainer title="轴承型号">
      <ProTable<BearingModel>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={filteredRows}
        scroll={{ x: 'max-content' }}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadRows }}
        optionsRender={renderRefSafeTableOptions}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            新建轴承型号
          </Button>,
        ]}
      />

      <ModalForm<BearingFormValues>
        title={editing ? '编辑轴承型号' : '新建轴承型号'}
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
              brand: editing.brand,
              model: editing.model,
              bearing_type: editing.bearing_type,
              rolling_element_count: editing.rolling_element_count,
              rolling_element_diameter_mm: editing.rolling_element_diameter_mm,
              pitch_diameter_mm: editing.pitch_diameter_mm,
              contact_angle_deg: editing.contact_angle_deg,
              description: editing.description,
              active: editing.active,
            }
            : {
              contact_angle_deg: 0,
              active: true,
            }
        }
        onFinish={async (values) => {
          if (values.rolling_element_diameter_mm >= values.pitch_diameter_mm) {
            message.error('滚动体直径必须小于节圆直径');
            return false;
          }
          const payload: BearingModelPayload = {
            brand: values.brand.trim(),
            model: values.model.trim(),
            bearing_type: values.bearing_type || null,
            rolling_element_count: values.rolling_element_count,
            rolling_element_diameter_mm: values.rolling_element_diameter_mm,
            pitch_diameter_mm: values.pitch_diameter_mm,
            contact_angle_deg: values.contact_angle_deg,
            description: values.description?.trim() || undefined,
            active: values.active ?? true,
          };
          setSaving(true);
          try {
            if (editing) {
              await updateBearing(editing.id, payload);
            } else {
              await createBearing(payload);
            }
            message.success('保存成功');
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
        <ProFormSelect
          name="bearing_type"
          label="轴承类型"
          placeholder="请选择轴承类型"
          options={[...BEARING_TYPE_OPTIONS]}
          rules={[{ required: true, message: '请选择轴承类型' }]}
          allowClear
        />

        <ProFormText
          name="model"
          label="型号"
          rules={[{ required: true, message: '请输入轴承型号' }]}
        />

        <ProFormDigit
          name="rolling_element_count"
          label="滚动体数量"
          min={3}
          fieldProps={{ precision: 0 }}
          rules={[{ required: true, message: '请输入滚动体数量' }]}
        />
        <ProFormDigit
          name="rolling_element_diameter_mm"
          label="滚动体直径(mm)"
          min={0.001}
          fieldProps={{ precision: 3 }}
          rules={[{ required: true, message: '请输入滚动体直径' }]}
        />
        <ProFormDigit
          name="pitch_diameter_mm"
          label="节圆直径(mm)"
          min={0.001}
          fieldProps={{ precision: 3 }}
          rules={[{ required: true, message: '请输入节圆直径' }]}
        />
        <ProFormDigit
          name="contact_angle_deg"
          label="接触角(°)"
          min={0}
          max={89.99}
          fieldProps={{ precision: 2 }}
          rules={[{ required: true, message: '请输入接触角' }]}
        />
        <ProFormText
          name="brand"
          label="品牌"
          rules={[{ required: true, message: '请输入轴承品牌' }]}
        />
        <ProFormText name="description" label="备注" />
        <ProFormSwitch name="active" label="启用状态" />
      </ModalForm>
    </PageContainer>
  );
};

export default BearingPage;

import { useRef, useState } from 'react';
import {
  ActionType,
  ModalForm,
  PageContainer,
  ProColumns,
  ProForm,
  ProFormCheckbox,
  ProFormDependency,
  ProFormRadio,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
} from '@ant-design/pro-components';
import { Alert, Button, Modal, Popconfirm, Space, Table, Tag, TimePicker, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { type Dayjs } from 'dayjs';
import {
  DeviceOperationSchedule,
  DeviceOperationScheduleItem,
  DeviceOperationSchedulePayload,
  ScheduleCycleType,
  buildCronFromVisualSlot,
  calculateDurationFromTimeRange,
  createOperationSchedule,
  deleteOperationSchedule,
  formatDurationMinutes,
  getOperationScheduleItems,
  parseCronScheduleItem,
  parseHourMinute,
  queryOperationSchedules,
  updateOperationSchedule,
  updateOperationScheduleItems,
} from '@/services/operationSchedule';
import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';

type ScheduleFormValues = {
  code: string;
  name: string;
  description?: string;
  status: number;
};

type ScheduleItemDraft = DeviceOperationScheduleItem & {
  draftKey: string;
};

type VisualSlotFormValues = {
  cycleType: ScheduleCycleType;
  weekdays?: number[];
  monthDays?: number[];
  startTime: Dayjs | string;
  endTime: Dayjs | string;
  remark?: string;
};

const WEEKDAY_OPTIONS = [
  { label: '周一', value: 1 },
  { label: '周二', value: 2 },
  { label: '周三', value: 3 },
  { label: '周四', value: 4 },
  { label: '周五', value: 5 },
  { label: '周六', value: 6 },
  { label: '周日', value: 7 },
];

const MONTH_DAY_OPTIONS = Array.from({ length: 31 }, (_, idx) => ({
  label: `${idx + 1}日`,
  value: idx + 1,
}));

const timeStrToDayjs = (timeStr: string, defaultHour: number, defaultMin = 0): Dayjs => {
  const [h, m] = parseHourMinute(timeStr, defaultHour, defaultMin);
  return dayjs().hour(h).minute(m).second(0).millisecond(0);
};

const toTimeStr = (val: Dayjs | string | undefined, fallback: string): string => {
  if (!val) return fallback;
  if (typeof val !== 'string' && typeof val.isValid === 'function') {
    return val.isValid() ? val.format('HH:mm') : fallback;
  }
  if (typeof val === 'string') {
    const match = val.match(/(\d{1,2}):(\d{1,2})/);
    if (match) {
      const h = Math.min(23, Math.max(0, Number(match[1])));
      const m = Math.min(59, Math.max(0, Number(match[2])));
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    }
    const parsed = dayjs(val);
    return parsed.isValid() ? parsed.format('HH:mm') : fallback;
  }
  return fallback;
};

const toErrorMessage = (error: unknown): string => {
  const e = error as
    | { data?: { detail?: string }; info?: { errorMessage?: string }; message?: string }
    | undefined;
  return e?.data?.detail || e?.info?.errorMessage || e?.message || '请求失败，请稍后重试';
};

const OperationSchedulePage = () => {
  const actionRef = useRef<ActionType>();
  const slotFormRef = useRef<any>();
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<DeviceOperationSchedule | null>(null);

  const [itemsModalOpen, setItemsModalOpen] = useState(false);
  const [currentSchedule, setCurrentSchedule] = useState<DeviceOperationSchedule | null>(null);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsSaving, setItemsSaving] = useState(false);
  const [scheduleItems, setScheduleItems] = useState<ScheduleItemDraft[]>([]);

  const [slotEditorOpen, setSlotEditorOpen] = useState(false);
  const [editingSlotIndex, setEditingSlotIndex] = useState<number | null>(null);

  const openItemsModal = async (schedule: DeviceOperationSchedule) => {
    setCurrentSchedule(schedule);
    setItemsModalOpen(true);
    setItemsLoading(true);
    try {
      const rows = await getOperationScheduleItems(schedule.id);
      setScheduleItems(
        rows.map((item, idx) => ({
          ...item,
          seq: item.seq ?? idx,
          draftKey: item.id || `${item.cron_expr}-${item.duration_minutes}-${idx}`,
        })),
      );
    } catch (error) {
      message.error(toErrorMessage(error));
      setItemsModalOpen(false);
      setCurrentSchedule(null);
    } finally {
      setItemsLoading(false);
    }
  };

  const columns: ProColumns<DeviceOperationSchedule>[] = [
    { title: '序号', valueType: 'indexBorder', width: 68, hideInSearch: true, fixed: 'left' },
    { title: '编码', dataIndex: 'code', width: 140, ellipsis: true, sorter: true },
    { title: '名称', dataIndex: 'name', width: 180, ellipsis: true, sorter: true },
    {
      title: '运行时段',
      dataIndex: 'items',
      width: 380,
      hideInSearch: true,
      render: (_, row) => {
        const items = row.items || [];
        if (items.length === 0) {
          return <span style={{ color: '#999' }}>未配置时段</span>;
        }
        return (
          <Space size={[4, 4]} wrap>
            {items.map((item, idx) => {
              const parsed = parseCronScheduleItem(item.cron_expr, item.duration_minutes);
              return (
                <Tag color="processing" key={item.id || idx}>
                  {parsed.summaryLabel}
                  {item.remark ? ` · ${item.remark}` : ''}
                </Tag>
              );
            })}
          </Space>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      valueType: 'select',
      valueEnum: {
        1: { text: '启用' },
        0: { text: '停用' },
      },
      render: (_, row) =>
        Number(row.status) === 1 ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
      sorter: true,
    },
    {
      title: '备注',
      dataIndex: 'description',
      width: 180,
      ellipsis: true,
      hideInSearch: true,
      render: (_, row) => row.description || '-',
    },
    {
      title: '操作',
      valueType: 'option',
      width: OPERATION_COL_WIDTH + 40,
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="small">
          <a onClick={() => void openItemsModal(row)}>时段</a>
          <a
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            title="确认删除该运行模式吗？"
            onConfirm={async () => {
              try {
                await deleteOperationSchedule(row.id);
                message.success('删除成功');
                actionRef.current?.reload();
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

  const itemColumns: ColumnsType<ScheduleItemDraft> = [
    {
      title: '序号',
      width: 68,
      render: (_, __, index) => index + 1,
    },
    {
      title: '执行周期',
      width: 180,
      render: (_, row) => {
        const parsed = parseCronScheduleItem(row.cron_expr, row.duration_minutes);
        return <Tag color="geekblue">{parsed.cycleLabel}</Tag>;
      },
    },
    {
      title: '运行时间段',
      width: 180,
      render: (_, row) => {
        const parsed = parseCronScheduleItem(row.cron_expr, row.duration_minutes);
        return <strong>{parsed.timeRangeLabel}</strong>;
      },
    },
    {
      title: '持续时长',
      width: 140,
      render: (_, row) => {
        const parsed = parseCronScheduleItem(row.cron_expr, row.duration_minutes);
        return `${parsed.durationLabel} (${row.duration_minutes}分钟)`;
      },
    },
    {
      title: '时段说明',
      dataIndex: 'remark',
      render: (val) => val || '-',
    },
    {
      title: '操作',
      width: 130,
      render: (_, row, index) => (
        <Space>
          <a
            onClick={() => {
              setEditingSlotIndex(index);
              setSlotEditorOpen(true);
            }}
          >
            编辑
          </a>
          <Popconfirm
            title="确认移除该运行时段吗？"
            onConfirm={() =>
              setScheduleItems((current) =>
                current.filter((item) => item.draftKey !== row.draftKey),
              )
            }
          >
            <a style={{ color: '#ff4d4f' }}>移除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const getSlotEditorInitialValues = (): VisualSlotFormValues => {
    if (editingSlotIndex === null || !scheduleItems[editingSlotIndex]) {
      return {
        cycleType: 'DAILY',
        weekdays: [1, 2, 3, 4, 5],
        monthDays: [1],
        startTime: timeStrToDayjs('08:00', 8, 0),
        endTime: timeStrToDayjs('12:00', 12, 0),
        remark: undefined,
      };
    }
    const target = scheduleItems[editingSlotIndex];
    const parsed = parseCronScheduleItem(target.cron_expr, target.duration_minutes);
    return {
      cycleType: parsed.cycleType,
      weekdays: parsed.weekdays.length > 0 ? parsed.weekdays : [1, 2, 3, 4, 5],
      monthDays: parsed.monthDays.length > 0 ? parsed.monthDays : [1],
      startTime: timeStrToDayjs(parsed.startTime, 8, 0),
      endTime: timeStrToDayjs(parsed.endTime, 12, 0),
      remark: target.remark,
    };
  };

  return (
    <PageContainer title="运行模式">
      <ProTable<DeviceOperationSchedule>
        rowKey="id"
        actionRef={actionRef}
        columns={columns}
        request={queryOperationSchedules}
        scroll={{ x: 'max-content' }}
        search={{ labelWidth: 'auto' }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
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
            新建运行模式
          </Button>,
        ]}
      />

      <ModalForm<ScheduleFormValues>
        title={editing ? '编辑运行模式' : '新建运行模式'}
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
                description: editing.description,
                status: Number(editing.status),
              }
            : { status: 1 }
        }
        onFinish={async (values) => {
          const payload: DeviceOperationSchedulePayload = {
            code: values.code.trim(),
            name: values.name.trim(),
            description: values.description?.trim() || undefined,
            status: Number(values.status ?? 1),
          };
          setSaving(true);
          try {
            if (editing) {
              await updateOperationSchedule(editing.id, payload);
            } else {
              await createOperationSchedule(payload);
            }
            message.success('保存成功');
            setModalOpen(false);
            setEditing(null);
            actionRef.current?.reload();
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
            { required: true, message: '请输入运行模式编码' },
            { max: 16, message: '编码最多16个字符' },
          ]}
        />
        <ProFormText
          name="name"
          label="名称"
          rules={[
            { required: true, message: '请输入运行模式名称' },
            { max: 64, message: '名称最多64个字符' },
          ]}
        />
        <ProFormSelect
          name="status"
          label="状态"
          options={[
            { label: '启用', value: 1 },
            { label: '停用', value: 0 },
          ]}
          rules={[{ required: true, message: '请选择状态' }]}
        />
        <ProFormTextArea
          name="description"
          label="备注"
          fieldProps={{ rows: 3, maxLength: 255 }}
        />
      </ModalForm>

      <Modal
        title={currentSchedule ? `${currentSchedule.name} - 运行时段配置` : '运行时段配置'}
        open={itemsModalOpen}
        width={880}
        destroyOnClose
        confirmLoading={itemsSaving}
        okText="保存配置"
        onCancel={() => {
          setItemsModalOpen(false);
          setCurrentSchedule(null);
          setScheduleItems([]);
        }}
        onOk={async () => {
          if (!currentSchedule) return;
          setItemsSaving(true);
          try {
            await updateOperationScheduleItems(
              currentSchedule.id,
              scheduleItems.map((item, idx) => ({
                cron_expr: item.cron_expr,
                duration_minutes: item.duration_minutes,
                remark: item.remark,
                seq: idx,
              })),
            );
            message.success('运行时段保存成功');
            setItemsModalOpen(false);
            setCurrentSchedule(null);
            setScheduleItems([]);
            actionRef.current?.reload();
          } catch (error) {
            message.error(toErrorMessage(error));
          } finally {
            setItemsSaving(false);
          }
        }}
      >
        <Space style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            onClick={() => {
              setEditingSlotIndex(null);
              setSlotEditorOpen(true);
            }}
          >
            添加运行时段
          </Button>
          <span style={{ color: '#8c8c8c' }}>
            支持一天配置多个运行时间段；若结束时间早于或等于开始时间，将自动按跨零点（次日结束）计算。
          </span>
        </Space>
        <Table<ScheduleItemDraft>
          rowKey="draftKey"
          loading={itemsLoading}
          columns={itemColumns}
          dataSource={scheduleItems}
          pagination={false}
          size="small"
        />
      </Modal>

      <ModalForm<VisualSlotFormValues>
        key={editingSlotIndex === null ? 'new-schedule-slot' : `edit-schedule-slot-${editingSlotIndex}`}
        formRef={slotFormRef}
        title={editingSlotIndex === null ? '构建运行时段' : '编辑运行时段'}
        open={slotEditorOpen}
        width={560}
        dateFormatter={false}
        modalProps={{
          destroyOnHidden: true,
          onCancel: () => {
            setSlotEditorOpen(false);
            setEditingSlotIndex(null);
          },
        }}
        initialValues={getSlotEditorInitialValues()}
        onFinish={async (values) => {
          const startTimeStr = toTimeStr(values.startTime, '08:00');
          const endTimeStr = toTimeStr(values.endTime, '12:00');
          const built = buildCronFromVisualSlot({
            cycleType: values.cycleType,
            weekdays: values.weekdays,
            monthDays: values.monthDays,
            startTime: startTimeStr,
            endTime: endTimeStr,
          });
          const previous =
            editingSlotIndex === null ? undefined : scheduleItems[editingSlotIndex];
          const nextItem: ScheduleItemDraft = {
            id: previous?.id,
            schedule_id: currentSchedule?.id,
            cron_expr: built.cron_expr,
            duration_minutes: built.duration_minutes,
            remark: values.remark?.trim() || undefined,
            seq: editingSlotIndex ?? scheduleItems.length,
            draftKey:
              previous?.draftKey ||
              `${built.cron_expr}-${built.duration_minutes}-${Date.now().toString(36)}`,
          };
          setScheduleItems((current) =>
            editingSlotIndex === null
              ? [...current, nextItem]
              : current.map((item, idx) => (idx === editingSlotIndex ? nextItem : item)),
          );
          setSlotEditorOpen(false);
          setEditingSlotIndex(null);
          return true;
        }}
      >
        <ProFormRadio.Group
          name="cycleType"
          label="执行周期"
          options={[
            { label: '每天运行', value: 'DAILY' },
            { label: '按星期运行', value: 'WEEKLY' },
            { label: '按每月日期运行', value: 'MONTHLY' },
          ]}
          rules={[{ required: true, message: '请选择执行周期' }]}
        />

        <ProFormDependency name={['cycleType']}>
          {({ cycleType }) => {
            if (cycleType === 'WEEKLY') {
              return (
                <>
                  <Space size="small" style={{ marginBottom: 8 }}>
                    <Button
                      size="small"
                      onClick={() => slotFormRef.current?.setFieldsValue({ weekdays: [1, 2, 3, 4, 5] })}
                    >
                      选工作日 (周一至周五)
                    </Button>
                    <Button
                      size="small"
                      onClick={() => slotFormRef.current?.setFieldsValue({ weekdays: [6, 7] })}
                    >
                      选周末 (周六、周日)
                    </Button>
                  </Space>
                  <ProFormCheckbox.Group
                    name="weekdays"
                    label="运行星期"
                    options={WEEKDAY_OPTIONS}
                    rules={[{ required: true, message: '请至少选择一天' }]}
                  />
                </>
              );
            }
            if (cycleType === 'MONTHLY') {
              return (
                <ProFormSelect
                  name="monthDays"
                  label="每月运行日期"
                  mode="multiple"
                  options={MONTH_DAY_OPTIONS}
                  placeholder="请选择每月运行的日期"
                  rules={[{ required: true, message: '请至少选择一个日期' }]}
                />
              );
            }
            return null;
          }}
        </ProFormDependency>

        <Space size="large" align="start" style={{ display: 'flex' }}>
          <ProForm.Item
            name="startTime"
            label="开始时间"
            rules={[{ required: true, message: '请选择开始时间' }]}
          >
            <TimePicker format="HH:mm" minuteStep={5} needConfirm={false} allowClear={false} />
          </ProForm.Item>

          <ProForm.Item
            name="endTime"
            label="结束时间"
            rules={[{ required: true, message: '请选择结束时间' }]}
          >
            <TimePicker format="HH:mm" minuteStep={5} needConfirm={false} allowClear={false} />
          </ProForm.Item>
        </Space>

        <ProFormDependency name={['cycleType', 'weekdays', 'monthDays', 'startTime', 'endTime']}>
          {({ cycleType, weekdays, monthDays, startTime, endTime }) => {
            const sStr = toTimeStr(startTime, '08:00');
            const eStr = toTimeStr(endTime, '12:00');
            const built = buildCronFromVisualSlot({
              cycleType: cycleType || 'DAILY',
              weekdays,
              monthDays,
              startTime: sStr,
              endTime: eStr,
            });
            const parsed = parseCronScheduleItem(built.cron_expr, built.duration_minutes);
            const rangeInfo = calculateDurationFromTimeRange(sStr, eStr);
            return (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message={`时段预览：${parsed.cycleLabel} ${rangeInfo.timeRangeLabel}`}
                description={`单次持续运行时长：${formatDurationMinutes(
                  rangeInfo.durationMinutes,
                )}（共 ${rangeInfo.durationMinutes} 分钟）`}
              />
            );
          }}
        </ProFormDependency>

        <ProFormText
          name="remark"
          label="时段说明"
          placeholder="选填，如：早班、下午班"
          fieldProps={{ maxLength: 128 }}
        />
      </ModalForm>
    </PageContainer>
  );
};

export default OperationSchedulePage;

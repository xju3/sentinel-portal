import { useEffect, useMemo, useState } from 'react';
import {
  ModalForm,
  PageContainer,
  ProColumns,
  ProFormSelect,
  ProFormText,
  ProTable,
} from '@ant-design/pro-components';
import { Button, Modal, Popconfirm, Select, Space, Tag, message } from 'antd';

import { Area, listAllAreas } from '@/services/area';
import { DeviceInst, listAllDeviceInsts } from '@/services/deviceInst';
import { DeviceSpec, listAllDeviceSpecs } from '@/services/deviceSpec';
import {
  createProcessDevice,
  createProcessDeviceItem,
  deleteProcessDevice,
  deleteProcessDeviceItem,
  listAllProcessDeviceItems,
  listAllProcessDevices,
  listAllProcessItems,
  listAllProcesses,
  Process,
  ProcessDevice,
  ProcessDeviceItem,
  ProcessItem,
  updateProcessDevice,
} from '@/services/process';

import { OPERATION_COL_WIDTH, renderRefSafeTableOptions } from '@/utils/proTableOptions';
type ProcessDeviceFormValues = {
  code: string;
  sn: string;
  process_id: string;
  area_id?: string;
  status: number;
};

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

const makeItemCode = (instanceCode: string, seq: number): string => {
  const prefix = instanceCode.replace(/[^a-zA-Z0-9]/g, '').slice(0, 4).toUpperCase() || 'PROC';
  const stamp = Date.now().toString(36).slice(-5).toUpperCase();
  const index = seq.toString(36).padStart(2, '0').toUpperCase();
  return `${prefix}${stamp}${index}`.slice(0, 16);
};

const clampSelections = (values: string[], max: number): string[] => {
  if (values.length <= max) {
    return values;
  }
  return values.slice(0, max);
};

const ProcessManagePage = () => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ProcessDevice | null>(null);
  const [query, setQuery] = useState<Record<string, any>>({});
  const [rows, setRows] = useState<ProcessDevice[]>([]);

  const [processes, setProcesses] = useState<Process[]>([]);
  const [processItems, setProcessItems] = useState<ProcessItem[]>([]);
  const [deviceSpecs, setDeviceSpecs] = useState<DeviceSpec[]>([]);
  const [deviceInsts, setDeviceInsts] = useState<DeviceInst[]>([]);
  const [processDeviceItems, setProcessDeviceItems] = useState<ProcessDeviceItem[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);

  const [configOpen, setConfigOpen] = useState(false);
  const [currentInstance, setCurrentInstance] = useState<ProcessDevice | null>(null);
  const [configSelections, setConfigSelections] = useState<Record<string, string[]>>({});
  const [configSaving, setConfigSaving] = useState(false);

  const processMap = useMemo(() => new Map(processes.map((item) => [item.id, item])), [processes]);
  const specMap = useMemo(() => new Map(deviceSpecs.map((item) => [item.id, item])), [deviceSpecs]);
  const instMap = useMemo(() => new Map(deviceInsts.map((item) => [item.id, item])), [deviceInsts]);
  const areaMap = useMemo(() => new Map(areas.map((item) => [item.id, item.name])), [areas]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [instances, templates, templateItems, specs, insts, instanceItems, areaRows] = await Promise.all([
        listAllProcessDevices(),
        listAllProcesses(),
        listAllProcessItems(),
        listAllDeviceSpecs(),
        listAllDeviceInsts(),
        listAllProcessDeviceItems(),
        listAllAreas(),
      ]);
      setRows(instances);
      setProcesses(templates);
      setProcessItems(templateItems);
      setDeviceSpecs(specs);
      setDeviceInsts(insts);
      setProcessDeviceItems(instanceItems);
      setAreas(areaRows);
    } catch (error) {
      message.error(toErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const filteredRows = useMemo(() => {
    const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();
    return rows.filter((row) => {
      const processName = processMap.get(row.process_id)?.name || '';
      if (query.code && !norm(row.code).includes(norm(query.code))) {
        return false;
      }
      if (query.sn && !norm(row.sn).includes(norm(query.sn))) {
        return false;
      }
      if (query.process_id) {
        const hit =
          norm(processName).includes(norm(query.process_id)) ||
          norm(row.process_id).includes(norm(query.process_id));
        if (!hit) {
          return false;
        }
      }
      if (query.area_id) {
        const areaName = row.area_id ? areaMap.get(row.area_id) || '' : '';
        const hit =
          norm(areaName).includes(norm(query.area_id)) ||
          norm(row.area_id).includes(norm(query.area_id));
        if (!hit) {
          return false;
        }
      }
      if (
        query.status !== undefined &&
        query.status !== null &&
        String(row.status) !== String(query.status)
      ) {
        return false;
      }
      return true;
    });
  }, [areaMap, processMap, query, rows]);

  const currentTemplateItems = useMemo(() => {
    if (!currentInstance?.process_id) {
      return [];
    }
    return processItems.filter((item) => item.process_id === currentInstance.process_id);
  }, [currentInstance?.process_id, processItems]);

  const currentInstanceItems = useMemo(() => {
    if (!currentInstance?.id) {
      return [];
    }
    return processDeviceItems.filter((item) => item.process_device_id === currentInstance.id);
  }, [currentInstance?.id, processDeviceItems]);

  const initializeConfigSelections = (instance: ProcessDevice) => {
    const templateRows = processItems.filter((item) => item.process_id === instance.process_id);
    const itemRows = processDeviceItems.filter((item) => item.process_device_id === instance.id);

    const grouped = new Map<string, string[]>();
    itemRows.forEach((item) => {
      const inst = instMap.get(item.device_inst_id);
      if (!inst) {
        return;
      }
      const list = grouped.get(inst.device_spec_id) || [];
      list.push(inst.id);
      grouped.set(inst.device_spec_id, list);
    });

    const selections: Record<string, string[]> = {};
    templateRows.forEach((row) => {
      const all = grouped.get(row.device_spec_id) || [];
      selections[row.id] = all.slice(0, row.qty);
      grouped.set(row.device_spec_id, all.slice(row.qty));
    });
    setConfigSelections(selections);
  };

  const columns: ProColumns<ProcessDevice>[] = [
    { title: '序号', valueType: 'indexBorder', width: 68, hideInSearch: true, fixed: 'left' },
    { title: '实例编码', dataIndex: 'code'},
    { title: '实例SN', dataIndex: 'sn' },
    {
      title: '工段模板',
      dataIndex: 'process_id',
      render: (_, row) => processMap.get(row.process_id)?.name || row.process_id,
    },
    {
      title: '工作区域',
      dataIndex: 'area_id',
      render: (_, row) => (row.area_id ? areaMap.get(row.area_id) || row.area_id : '-'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      valueType: 'select',
      valueEnum: { 1: { text: '启用' }, 0: { text: '停用' } },
      render: (_, row) => (Number(row.status) === 1 ? '启用' : '停用'),
    },
    {
      title: '操作',
      valueType: 'option',
      width: OPERATION_COL_WIDTH,
      fixed: 'right',
      align: 'center',
      render: (_, row) => (
        <Space size="middle">
          <Button
            key="config"
            type="link"
            onClick={() => {
              setCurrentInstance(row);
              initializeConfigSelections(row);
              setConfigOpen(true);
            }}
          >
            配置
          </Button>
          <Button
            key="edit"
            type="link"
            onClick={() => {
              setEditing(row);
              setModalOpen(true);
            }}
          >
            编辑
          </Button>
          <Popconfirm
            key="delete"
            title="确认删除该工段实例吗？"
            onConfirm={async () => {
              try {
                await deleteProcessDevice(row.id);
                message.success('删除成功');
                await loadAll();
              } catch (error) {
                message.error(toErrorMessage(error));
              }
            }}
          >
            <Button danger type="link">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const processOptions = useMemo(
    () => processes.map((item) => ({ label: `${item.code} - ${item.name}`, value: item.id })),
    [processes],
  );
  const areaOptions = useMemo(
    () => areas.map((item) => ({ label: item.name, value: item.id })),
    [areas],
  );

  return (
    <PageContainer title="工段管理">
      <ProTable<ProcessDevice>
        rowKey="id"
        loading={loading}
        columns={columns}
        scroll={{ x: 'max-content' }}
        dataSource={filteredRows}
        search={{ labelWidth: 'auto' }}
        onSubmit={(values) => setQuery(values)}
        onReset={() => setQuery({})}
        options={{ reload: loadAll }}
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
            新建工段实例
          </Button>,
        ]}
      />

      <ModalForm<ProcessDeviceFormValues>
        title={editing ? '编辑工段实例' : '新建工段实例'}
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
              sn: editing.sn,
              process_id: editing.process_id,
              area_id: editing.area_id || undefined,
              status: Number(editing.status),
            }
            : { status: 1 }
        }
        onFinish={async (values) => {
          setSaving(true);
          try {
            const payload = {
              code: values.code.trim(),
              sn: values.sn.trim(),
              process_id: values.process_id,
              area_id: values.area_id || null,
              status: Number(values.status ?? 1),
            };
            if (editing) {
              await updateProcessDevice(editing.id, payload);
              message.success('更新成功');
            } else {
              await createProcessDevice(payload);
              message.success('创建成功');
            }
            setModalOpen(false);
            setEditing(null);
            await loadAll();
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
          label="实例编码"
          rules={[{ required: true, message: '请输入实例编码' }, { max: 8, message: '实例编码最多8个字符' }]}
        />
        <ProFormText
          name="sn"
          label="实例SN"
          rules={[{ required: true, message: '请输入实例SN' }, { max: 64, message: '实例SN最多64个字符' }]}
        />
        <ProFormSelect
          name="process_id"
          label="工段模板"
          options={processOptions}
          rules={[{ required: true, message: '请选择工段模板' }]}
        />
        <ProFormSelect name="area_id" label="工作区域" options={areaOptions} allowClear />
        <ProFormSelect
          name="status"
          label="状态"
          options={[
            { label: '启用', value: 1 },
            { label: '停用', value: 0 },
          ]}
          rules={[{ required: true, message: '请选择状态' }]}
        />
      </ModalForm>

      <Modal
        title={`实例配置 - ${currentInstance?.code || ''}`}
        open={configOpen}
        width={980}
        onCancel={() => {
          setConfigOpen(false);
          setCurrentInstance(null);
          setConfigSelections({});
        }}
        onOk={async () => {
          if (!currentInstance) {
            return;
          }
          const allSelected = new Set<string>();
          for (const row of currentTemplateItems) {
            const selected = configSelections[row.id] || [];
            if (selected.length !== row.qty) {
              message.error(`规格 ${specMap.get(row.device_spec_id)?.name || row.device_spec_id} 需要 ${row.qty} 台`);
              return;
            }
            for (const instId of selected) {
              const inst = instMap.get(instId);
              if (!inst || inst.device_spec_id !== row.device_spec_id) {
                message.error('存在设备规格与模板子项不匹配的选择');
                return;
              }
              if (allSelected.has(instId)) {
                message.error('同一设备不能重复分配到多个模板子项');
                return;
              }
              allSelected.add(instId);
            }
          }

          setConfigSaving(true);
          try {
            await Promise.all(currentInstanceItems.map((item) => deleteProcessDeviceItem(item.id)));
            const createTasks: Promise<any>[] = [];
            let seq = 1;
            for (const row of currentTemplateItems) {
              const selected = configSelections[row.id] || [];
              for (const instId of selected) {
                const specName = specMap.get(row.device_spec_id)?.name || row.device_spec_id;
                createTasks.push(
                  createProcessDeviceItem({
                    code: makeItemCode(currentInstance.code, seq++),
                    desc: `${currentInstance.code}-${specName}`,
                    device_inst_id: instId,
                    process_device_id: currentInstance.id,
                  }),
                );
              }
            }
            await Promise.all(createTasks);
            message.success('配置保存成功');
            await loadAll();
            setConfigOpen(false);
            setCurrentInstance(null);
            setConfigSelections({});
          } catch (error) {
            message.error(toErrorMessage(error));
          } finally {
            setConfigSaving(false);
          }
        }}
        confirmLoading={configSaving}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {currentTemplateItems.length === 0 ? (
            <Tag color="warning">当前工段模板没有子项，请先在工段模板中配置 ProcessItem</Tag>
          ) : null}
          {currentTemplateItems.map((row) => {
            const spec = specMap.get(row.device_spec_id);
            const selectedInOthers = new Set<string>();
            currentTemplateItems.forEach((other) => {
              if (other.id === row.id) {
                return;
              }
              (configSelections[other.id] || []).forEach((instId) => selectedInOthers.add(instId));
            });
            const options = deviceInsts
              .filter((item) => item.device_spec_id === row.device_spec_id)
              .map((item) => ({
                label: `${item.code} / ${item.sn}`,
                value: item.id,
                disabled: selectedInOthers.has(item.id),
              }));
            const selected = configSelections[row.id] || [];
            return (
              <div key={row.id} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 12 }}>
                <div style={{ marginBottom: 8 }}>
                  <b>{spec ? `${spec.name} / ${spec.model}` : row.device_spec_id}</b>
                  <span style={{ marginLeft: 8, color: '#999' }}>模板数量: {row.qty}</span>
                  <span style={{ marginLeft: 8, color: selected.length === row.qty ? '#389e0d' : '#cf1322' }}>
                    已选: {selected.length}
                  </span>
                </div>
                <Select
                  mode="multiple"
                  style={{ width: '100%' }}
                  placeholder="请选择设备实例"
                  options={options}
                  value={selected}
                  onChange={(vals) => {
                    const next = clampSelections(vals, row.qty);
                    if (vals.length > row.qty) {
                      message.warning(`该规格最多只能选择 ${row.qty} 台设备`);
                    }
                    setConfigSelections((prev) => ({ ...prev, [row.id]: next }));
                  }}
                  maxCount={row.qty}
                  maxTagCount="responsive"
                />
              </div>
            );
          })}
        </Space>
      </Modal>
    </PageContainer>
  );
};

export default ProcessManagePage;

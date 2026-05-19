import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Key } from 'react';
import { Button, Input, Modal, Space, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';

type EntityRow = {
  id: string;
};

type PickerQuery = {
  current: number;
  pageSize: number;
  keyword: string;
};

type PickerResult<T> = {
  items: T[];
  total: number;
};

type EntityPickerProps<T extends EntityRow> = {
  value?: string;
  onChange?: (value?: string) => void;
  valueLabel?: string;
  placeholder?: string;
  modalTitle: string;
  triggerText?: string;
  fetcher: (query: PickerQuery) => Promise<PickerResult<T>>;
  columns: ColumnsType<T>;
  getRecordLabel: (record: T) => string;
  disabled?: boolean;
};

function EntityPicker<T extends EntityRow>({
  value,
  onChange,
  valueLabel,
  placeholder = '请选择',
  modalTitle,
  triggerText = '选择',
  fetcher,
  columns,
  getRecordLabel,
  disabled,
}: EntityPickerProps<T>) {
  const requestSeqRef = useRef(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [current, setCurrent] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [rows, setRows] = useState<T[]>([]);
  const [selectedId, setSelectedId] = useState<string | undefined>(value);
  const [selectedLabel, setSelectedLabel] = useState('');

  useEffect(() => {
    setSelectedId(value);
  }, [value]);

  const runQuery = useCallback(
    async (nextCurrent: number, nextPageSize: number, nextKeyword: string) => {
      const seq = ++requestSeqRef.current;
      setLoading(true);
      try {
        const result = await fetcher({
          current: nextCurrent,
          pageSize: nextPageSize,
          keyword: nextKeyword,
        });
        if (seq !== requestSeqRef.current) {
          return;
        }
        setRows(result.items || []);
        setTotal(result.total || 0);
        const matched = (result.items || []).find((item) => item.id === selectedId);
        if (matched) {
          setSelectedLabel(getRecordLabel(matched));
        }
      } catch {
        if (seq === requestSeqRef.current) {
          setRows([]);
          setTotal(0);
        }
      } finally {
        if (seq === requestSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [fetcher, getRecordLabel, selectedId],
  );

  const openModal = async () => {
    setOpen(true);
    setCurrent(1);
    await runQuery(1, pageSize, keyword);
  };

  const handleKeywordSearch = async (nextKeyword: string) => {
    setKeyword(nextKeyword);
    setCurrent(1);
    await runQuery(1, pageSize, nextKeyword);
  };

  const displayValue = useMemo(() => {
    if (valueLabel) {
      return valueLabel;
    }
    if (selectedLabel) {
      return selectedLabel;
    }
    return value || '';
  }, [selectedLabel, value, valueLabel]);

  const selectedKeys = useMemo<Key[]>(() => (selectedId ? [selectedId] : []), [selectedId]);

  return (
    <>
      <Space.Compact style={{ width: '100%' }}>
        <Input readOnly value={displayValue} placeholder={placeholder} />
        <Button onClick={openModal} disabled={disabled}>
          {triggerText}
        </Button>
        <Button
          onClick={() => {
            setSelectedId(undefined);
            setSelectedLabel('');
            onChange?.(undefined);
          }}
          disabled={disabled || !value}
        >
          清空
        </Button>
      </Space.Compact>

      <Modal
        title={modalTitle}
        open={open}
        width={860}
        onCancel={() => setOpen(false)}
        onOk={() => {
          if (!selectedId) {
            return;
          }
          const selectedRow = rows.find((item) => item.id === selectedId);
          if (selectedRow) {
            setSelectedLabel(getRecordLabel(selectedRow));
          }
          onChange?.(selectedId);
          setOpen(false);
        }}
        okButtonProps={{ disabled: !selectedId }}
        destroyOnClose
      >
        <Input.Search
          placeholder="输入关键字查询"
          allowClear
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onSearch={handleKeywordSearch}
          style={{ marginBottom: 12 }}
        />
        <Table<T>
          rowKey="id"
          loading={loading}
          dataSource={rows}
          columns={columns}
          size="small"
          pagination={{
            current,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (count) => `共 ${count} 条`,
            onChange: async (nextCurrent, nextPageSize) => {
              const realPageSize = nextPageSize || pageSize;
              setCurrent(nextCurrent);
              setPageSize(realPageSize);
              await runQuery(nextCurrent, realPageSize, keyword);
            },
          }}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedKeys,
            onChange: (keys, selectedRows) => {
              const key = keys[0];
              const row = selectedRows[0];
              if (!key) {
                setSelectedId(undefined);
                return;
              }
              setSelectedId(String(key));
              if (row) {
                setSelectedLabel(getRecordLabel(row));
              }
            },
          }}
          onRow={(record) => ({
            onClick: () => {
              setSelectedId(record.id);
              setSelectedLabel(getRecordLabel(record));
            },
          })}
        />
      </Modal>
    </>
  );
}

export type { PickerQuery, PickerResult };
export default EntityPicker;

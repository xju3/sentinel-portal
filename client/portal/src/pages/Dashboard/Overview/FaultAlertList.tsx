import { Badge, List, Tag } from 'antd';

// 异常状态映射
const ANOMALY_MAP: Record<number, { text: string; color: string }> = {
  1: { text: '振动异常', color: 'warning' },
  2: { text: '温度异常', color: 'error' },
  3: { text: '振动+温度异常', color: 'magenta' },
};

interface AnomalyItem {
  id: string;
  device_code: string;
  device_sn: string;
  anomaly: number;
  ts: number;
}

interface FaultAlertListProps {
  dataSource: AnomalyItem[];
  loading?: boolean;
}

const FaultAlertList = ({ dataSource, loading }: FaultAlertListProps) => {
  return (
    <List
      loading={loading}
      itemLayout="horizontal"
      dataSource={dataSource}
      renderItem={(item) => (
        <List.Item>
          <List.Item.Meta
            title={
              <span>
                <Badge status="error" style={{ marginRight: 8 }} />
                {item.device_code}
              </span>
            }
            description={`SN: ${item.device_sn} | 时间: ${new Date(item.ts).toLocaleString()}`}
          />
          <Tag color={ANOMALY_MAP[item.anomaly]?.color || 'default'}>
            {ANOMALY_MAP[item.anomaly]?.text || '未知异常'}
          </Tag>
        </List.Item>
      )}
    />
  );
};

export default FaultAlertList;

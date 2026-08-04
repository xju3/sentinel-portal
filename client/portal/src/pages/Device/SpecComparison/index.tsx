import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeftOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
} from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-components';
import { useNavigate, useParams, useSearchParams } from '@umijs/max';
import { Button, Card, Empty, Select, Space, Spin, Typography, message } from 'antd';

import SpecComparisonContent from '@/pages/Device/Spec/SpecComparisonModal';
import {
  DeviceCategory,
  listAllDeviceCategories,
} from '@/services/deviceCategory';
import { DeviceSpec, listAllDeviceSpecs } from '@/services/deviceSpec';

import styles from './index.less';

const SpecComparisonPage = () => {
  const { deviceSpecId = '' } = useParams<{ deviceSpecId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const fullscreenRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState<DeviceCategory[]>([]);
  const [specs, setSpecs] = useState<DeviceSpec[]>([]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setFullscreen(document.fullscreenElement === fullscreenRef.current);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (fullscreenRef.current) {
        await fullscreenRef.current.requestFullscreen();
      }
    } catch (error: any) {
      message.error(error?.message || '无法切换全屏显示');
    }
  };

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([listAllDeviceCategories(), listAllDeviceSpecs()])
      .then(([categoryRows, specRows]) => {
        if (!active) return;
        setCategories(categoryRows);
        setSpecs(specRows);
        if (specRows.length > 0 && !specRows.some((item) => item.id === deviceSpecId)) {
          navigate(`/device/specs/${specRows[0].id}/comparison`, { replace: true });
        }
      })
      .catch((error: any) => {
        if (active) {
          message.error(error?.data?.detail || error?.message || '设备规格加载失败');
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedSpec = useMemo(
    () => specs.find((item) => item.id === deviceSpecId) || null,
    [deviceSpecId, specs],
  );
  const specsByCategory = useMemo(() => {
    const grouped = new Map<string, DeviceSpec[]>();
    specs.forEach((item) => {
      const items = grouped.get(item.device_category_id) || [];
      items.push(item);
      grouped.set(item.device_category_id, items);
    });
    grouped.forEach((items) =>
      items.sort((left, right) =>
        `${left.name}-${left.model}`.localeCompare(`${right.name}-${right.model}`, 'zh-CN'),
      ),
    );
    return grouped;
  }, [specs]);
  const categorySpecs = selectedSpec
    ? specsByCategory.get(selectedSpec.device_category_id) || []
    : [];

  const navigateToSpec = (specId: string) => {
    navigate(`/device/specs/${specId}/comparison`);
  };

  return (
    <div ref={fullscreenRef} className={styles.fullscreenHost}>
      <PageContainer
      title="同规格设备对比"
      subTitle={selectedSpec ? `${selectedSpec.name} / ${selectedSpec.model}` : undefined}
      extra={[
        <Button
          key="fullscreen"
          icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
          onClick={() => void toggleFullscreen()}
        >
          {fullscreen ? '退出全屏' : '全屏'}
        </Button>,
        <Button key="back" icon={<ArrowLeftOutlined />} onClick={() => navigate('/device/specs')}>
          返回设备规格
        </Button>,
      ]}
    >
      <Card style={{ marginBottom: 16 }}>
        <Space size="large" wrap>
          <Space>
            <Typography.Text type="secondary">设备分类</Typography.Text>
            <Select
              value={selectedSpec?.device_category_id}
              loading={loading}
              showSearch
              optionFilterProp="label"
              getPopupContainer={(trigger) => trigger.parentElement || document.body}
              placeholder="请选择设备分类"
              style={{ width: 220 }}
              options={categories.map((item) => ({
                value: item.id,
                label: item.name,
                disabled: !specsByCategory.get(item.id)?.length,
              }))}
              onChange={(categoryId) => {
                const firstSpec = specsByCategory.get(categoryId)?.[0];
                if (firstSpec) navigateToSpec(firstSpec.id);
              }}
            />
          </Space>
          <Space>
            <Typography.Text type="secondary">设备规格</Typography.Text>
            <Select
              value={selectedSpec?.id}
              loading={loading}
              showSearch
              optionFilterProp="label"
              getPopupContainer={(trigger) => trigger.parentElement || document.body}
              placeholder="请选择设备规格"
              style={{ width: 280 }}
              options={categorySpecs.map((item) => ({
                value: item.id,
                label: `${item.name} / ${item.model}`,
              }))}
              onChange={navigateToSpec}
            />
          </Space>
        </Space>
      </Card>

      <Spin spinning={loading}>
        {selectedSpec ? (
          <SpecComparisonContent
            spec={selectedSpec}
            defaultGroupId={searchParams.get('group') || undefined}
          />
        ) : (
          !loading && <Empty description="没有可用于对比的设备规格" />
        )}
      </Spin>
      </PageContainer>
    </div>
  );
};

export default SpecComparisonPage;

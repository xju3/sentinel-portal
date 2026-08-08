import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeftOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-components';
import { useNavigate, useParams, useSearchParams } from '@umijs/max';
import { Button, Card, Empty, Space, Spin, Typography, message, TreeSelect, Radio } from 'antd';

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
  const [refreshKey, setRefreshKey] = useState(0);
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

  const categoryTreeData = useMemo(() => {
    const map = new Map();
    categories.forEach((item) => {
      map.set(item.id, {
        value: item.id,
        title: item.name,
        disabled: !specsByCategory.get(item.id)?.length,
        children: [],
      });
    });

    const tree: any[] = [];
    categories.forEach((item) => {
      const node = map.get(item.id);
      if (item.parent_id && map.has(item.parent_id)) {
        map.get(item.parent_id).children.push(node);
      } else {
        tree.push(node);
      }
    });

    const cleanEmptyChildren = (nodes: any[]) => {
      nodes.forEach((node) => {
        if (node.children.length === 0) {
          delete node.children;
        } else {
          cleanEmptyChildren(node.children);
        }
      });
    };
    cleanEmptyChildren(tree);

    return tree;
  }, [categories, specsByCategory]);

  const navigateToSpec = (specId: string) => {
    navigate(`/device/specs/${specId}/comparison`);
  };

  return (
    <div ref={fullscreenRef} className={styles.fullscreenHost}>
      <PageContainer
      title="同规格设备对比"
      subTitle={selectedSpec ? `${selectedSpec.name} / ${selectedSpec.model}` : undefined}
      extra={[
        <Space key="category" style={{ marginRight: 24 }}>
          <Typography.Text type="secondary">设备分类</Typography.Text>
          <TreeSelect
            value={selectedSpec?.device_category_id}
            loading={loading}
            showSearch
            treeNodeFilterProp="title"
            treeDefaultExpandAll
            getPopupContainer={(trigger) => trigger.parentElement || document.body}
            placeholder="请选择设备分类"
            style={{ width: 220 }}
            treeData={categoryTreeData}
            onChange={(categoryId) => {
              const firstSpec = specsByCategory.get(categoryId)?.[0];
              if (firstSpec) navigateToSpec(firstSpec.id);
            }}
          />
        </Space>,
        <Button
          key="refresh"
          icon={<ReloadOutlined />}
          onClick={() => setRefreshKey((k) => k + 1)}
        >
          刷新
        </Button>,
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
      <Spin spinning={loading}>
        {selectedSpec ? (
          <SpecComparisonContent
            spec={selectedSpec}
            defaultGroupId={searchParams.get('group') || undefined}
            refreshKey={refreshKey}
            specSelector={
              <>
                <Typography.Text type="secondary">设备规格</Typography.Text>
                <Radio.Group
                  value={selectedSpec?.id}
                  onChange={(e) => navigateToSpec(e.target.value)}
                  optionType="button"
                  buttonStyle="solid"
                >
                  {categorySpecs.map((item) => (
                    <Radio.Button key={item.id} value={item.id}>
                      {item.name} / {item.model}
                    </Radio.Button>
                  ))}
                </Radio.Group>
              </>
            }
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

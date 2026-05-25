import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

// 异常层级渐进色阶：从浅红到深红，按层级深度递增
const ANOMALY_COLORS = [
  '#ffebee', // 第1层（最内层父分类）- 极浅红
  '#ffcdd2', // 第2层 - 浅红
  '#ef9a9a', // 第3层 - 中浅红
  '#e57373', // 第4层 - 中红
  '#ef5350', // 第5层 - 中深红
  '#e53935', // 第6层（最外层异常子节点）- 深红
];

// 递归生成旭日图数据格式
const convertToSunburst = (nodes: any[], anomalyDepth: number = 0): any[] => {
  return nodes.map(n => {
    const hasAnomaly = n.anomaly > 0;
    let children = n.children ? convertToSunburst(n.children, hasAnomaly ? anomalyDepth + 1 : anomalyDepth) : [];

    // 如果该底层分类有异常，则在外部再增加一圈（子节点）专门显示健康状态
    if (children.length === 0 && hasAnomaly) {
      const normalCount = Math.max(0, n.total - n.anomaly);
      if (normalCount > 0) {
        children.push({
          name: '正常',
          realTotal: normalCount,
          anomaly: 0,
          value: normalCount,
          itemStyle: { color: '#e8f5e9' },
          label: { show: true, formatter: '{c}', color: '#81c784', fontSize: 10, textBorderWidth: 0 },
          tooltip: { show: true },
        });
      }
      const outerColorIndex = Math.min(anomalyDepth + 1, ANOMALY_COLORS.length - 1);
      children.push({
        name: '异常',
        realTotal: n.anomaly,
        anomaly: n.anomaly,
        value: n.anomaly,
        itemStyle: { color: ANOMALY_COLORS[outerColorIndex] },
        label: { show: true, formatter: '{c}', color: '#fff', textBorderWidth: 0 },
      });
    }

    let color = undefined;
    if (n.total === 0) {
      color = '#e8e8e8';
    } else if (n.anomaly === 0) {
      color = '#e0e0e0';
    } else {
      const colorIndex = Math.min(anomalyDepth, ANOMALY_COLORS.length - 1);
      color = ANOMALY_COLORS[colorIndex];
    }

    return {
      name: n.name,
      realTotal: n.total,
      anomaly: n.anomaly,
      value: children.length > 0 ? undefined : Math.max(n.total, 1),
      itemStyle: { color },
      label: {
        color: n.total === 0 ? '#999' : (n.anomaly > 0 ? '#c62828' : '#666'),
        textBorderColor: n.total === 0 ? 'transparent' : 'rgba(255,255,255,0.8)',
        textBorderWidth: n.total === 0 ? 0 : 1,
      },
      children: children.length > 0 ? children : undefined,
    };
  });
};

// 计算最大层级
const getMaxDepth = (nodes: any[]): number => {
  if (!nodes || nodes.length === 0) return 0;
  let max = 0;
  for (const node of nodes) {
    max = Math.max(max, node.children ? getMaxDepth(node.children) : 0);
  }
  return max + 1;
};

interface SunburstChartProps {
  treeData: any[];
  anomalyColor?: string;
  onViewModeToggle?: () => void;
}

const SunburstChart = ({
  treeData,
  anomalyColor = '#9b2e2e',
  onViewModeToggle,
}: SunburstChartProps) => {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let treeChart: echarts.ECharts | undefined;

    if (chartRef.current) {
      const sunburstData = convertToSunburst(treeData || []);

      const depth = getMaxDepth(sunburstData);
      const sunburstLevels: any[] = [{}];
      if (depth > 0) {
        const innerRadius = 0;
        const outerRadius = 95;
        const thicknessUnit = (outerRadius - innerRadius) / (depth - 0.5);
        let currentRadius = innerRadius;
        for (let i = 1; i <= depth; i++) {
          const thickness = i === depth ? thicknessUnit / 2 : thicknessUnit;
          sunburstLevels.push({
            r0: `${currentRadius}%`,
            r: `${currentRadius + thickness}%`,
          });
          currentRadius += thickness;
        }
      }

      treeChart = echarts.init(chartRef.current);

      if (sunburstData.length === 0) {
        treeChart.setOption({
          title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#999', fontSize: 14 } },
          series: [],
        });
      } else {
        treeChart.setOption({
          tooltip: {
            formatter: (params: any) => {
              const { name, data } = params;
              if (!data) return '';
              const realTotal = data.realTotal ?? data.value ?? 0;
              const anomaly = data.anomaly ?? 0;
              const normal = Math.max(0, realTotal - anomaly);
              return `${name}<br/>总计: ${realTotal} 台<br/>正常: ${normal} 台 | 异常: <span style="color:${anomalyColor}">${anomaly}</span> 台`;
            },
          },
          series: {
            type: 'sunburst',
            data: sunburstData,
            radius: ['0%', '95%'],
            levels: depth > 0 ? sunburstLevels : undefined,
            sort: undefined,
            emphasis: { focus: 'ancestor' },
            itemStyle: { borderRadius: 4, borderWidth: 2, borderColor: '#fff' },
            label: {
              show: true,
              formatter: (params: any) => {
                const { name, data } = params;
                if (!data) return '';
                const realTotal = data.realTotal ?? data.value ?? 0;
                if (name === '全部') {
                  return `全部(${realTotal}台)`;
                }
                return ` ${name}\n${realTotal} 台`;
              },
              rich: {
                name: { color: 'inherit', fontSize: 10, align: 'center', lineHeight: 18 },
                total: { color: 'inherit', fontSize: 12, align: 'center', lineHeight: 16 },
              },
            },
          },
        });

        // 点击中心（"全部"节点）切换视图模式
        treeChart.on('click', (params: any) => {
          if (params.name === '全部' && onViewModeToggle) {
            onViewModeToggle();
          }
        });
      }
    }

    const handleResize = () => treeChart?.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      treeChart?.dispose();
    };
  }, [treeData, anomalyColor, onViewModeToggle]);

  return <div ref={chartRef} style={{ height: 350, width: '100%' }} />;
};

export default SunburstChart;

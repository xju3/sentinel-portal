import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface FaultItem {
  name: string;
  count: number;
}

interface FaultRankBarChartProps {
  data: FaultItem[];
}

const FaultRankBarChart = ({ data }: FaultRankBarChartProps) => {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let chart: echarts.ECharts | undefined;

    if (chartRef.current) {
      chart = echarts.init(chartRef.current);

      if (!data || data.length === 0) {
        chart.setOption({
          title: {
            text: '该维度下暂无报警/故障设备',
            left: 'center',
            top: 'center',
            textStyle: { color: '#999', fontSize: 14, fontWeight: 'normal' },
          },
          series: [],
        }, true);
      } else {
        // 确保数据按故障数量从大到小排序
        const sortedData = [...data].sort((a, b) => b.count - a.count);
        const names = sortedData.map((d) => d.name);
        const values = sortedData.map((d) => d.count);

        chart.setOption({
          tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter: (params: any[]) => {
              const param = params[0];
              return `${param.name}<br/>故障设备数: <span style="color:#ff4d4f;font-weight:bold">${param.value}</span> 台`;
            },
          },
          grid: {
            top: '3%',
            left: '2%',
            right: '6%',
            bottom: '3%',
            containLabel: true,
          },
          xAxis: {
            type: 'value',
            minInterval: 1, // 保证 X 轴刻度为整数
            splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } },
          },
          yAxis: {
            type: 'category',
            inverse: true, // 反转 Y 轴，使数量最多的排在最上方
            data: names,
            axisLabel: {
              width: 130, // 限制标签宽度
              overflow: 'truncate', // 超出显示省略号
              color: '#333',
            },
          },
          series: [
            {
              name: '故障数量',
              type: 'bar',
              barWidth: 16, // 柱子宽度
              label: { show: true, position: 'right', color: '#ff4d4f', fontWeight: 'bold' },
              itemStyle: {
                borderRadius: [0, 4, 4, 0], // 右侧圆角
                color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                  { offset: 0, color: '#ff7875' },
                  { offset: 1, color: '#ff4d4f' }, // 渐变色：从浅红到深红
                ]),
              },
              data: values,
            },
          ],
        }, true); // true 参数表示完全覆写上一次的配置
      }
    }

    const handleResize = () => chart?.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart?.dispose();
    };
  }, [data]);

  return <div ref={chartRef} style={{ height: 263, width: '100%' }} />;
};

export default FaultRankBarChart;
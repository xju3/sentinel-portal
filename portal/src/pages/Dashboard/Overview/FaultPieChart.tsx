import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface FaultPieChartProps {
  totalDevices: number;
  runningDevices: number;
  faultyDevices: number;
  vibrationAnomalyCount: number;
  temperatureAnomalyCount: number;
  bothAnomalyCount: number;
}

const FaultPieChart = ({
  totalDevices,
  runningDevices,
  faultyDevices,
  vibrationAnomalyCount,
  temperatureAnomalyCount,
  bothAnomalyCount,
}: FaultPieChartProps) => {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let pieChart: echarts.ECharts | undefined;

    const normalRunning = Math.max(0, runningDevices - faultyDevices);
    const offlineDevices = Math.max(0, totalDevices - normalRunning - faultyDevices);

    if (chartRef.current) {
      pieChart = echarts.init(chartRef.current);
      pieChart.setOption({
        tooltip: {
          trigger: 'item',
          formatter: (params: any) => {
            return `${params.name}: ${params.value} 台 (${params.percent}%)`;
          },
        },
        series: [
          {
            name: '故障概览',
            type: 'pie',
            radius: ['40%', '70%'],
            avoidLabelOverlap: false,
            itemStyle: {
              borderRadius: 8,
              borderColor: '#fff',
              borderWidth: 2,
            },
            label: {
              show: true,
              formatter: (params: any) => `${params.name}\n${params.value}台`,
              fontSize: 11,
              color: '#333',
              lineHeight: 16,
            },
            emphasis: {
              label: { show: true, fontSize: 14, fontWeight: 'bold' },
            },
            labelLine: {
              show: true,
              length: 8,
              length2: 12,
              smooth: true,
            },
            data: (() => {
              const items = [
                { value: normalRunning, name: '正常运行', itemStyle: { color: '#52c41a' } },
                { value: offlineDevices, name: '离线/未知', itemStyle: { color: '#d9d9d9' } },
              ];
              const hasDetail = vibrationAnomalyCount > 0 || temperatureAnomalyCount > 0 || bothAnomalyCount > 0;
              if (hasDetail) {
                items.splice(1, 0,
                  { value: vibrationAnomalyCount, name: '震动异常', itemStyle: { color: '#faad14' } },
                  { value: temperatureAnomalyCount, name: '温度异常', itemStyle: { color: '#ff4d4f' } },
                  { value: bothAnomalyCount, name: '震动+温度异常', itemStyle: { color: '#eb2f96' } },
                );
              } else if (faultyDevices > 0) {
                items.splice(1, 0,
                  { value: faultyDevices, name: '故障设备', itemStyle: { color: '#ff4d4f' } },
                );
              }
              return items.filter(item => item.value > 0);
            })(),
          },
        ],
      });
    }

    const handleResize = () => pieChart?.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      pieChart?.dispose();
    };
  }, [totalDevices, runningDevices, faultyDevices, vibrationAnomalyCount, temperatureAnomalyCount, bothAnomalyCount]);

  return <div ref={chartRef} style={{ height: 350, width: '100%' }} />;
};

export default FaultPieChart;

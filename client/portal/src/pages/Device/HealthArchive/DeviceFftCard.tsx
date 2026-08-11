import { useEffect, useMemo, useRef, useState } from 'react';
import { Card, Empty, Select, Space, Spin, message, Typography, Segmented } from 'antd';
import * as echarts from 'echarts';
import dayjs from 'dayjs';

import {
  DeviceFftRecord,
  DeviceFftData,
  listDeviceFftRecords,
  getDeviceFftData,
} from '@/services/deviceHealthArchive';

const DeviceFftCard = ({ deviceId, rpm }: { deviceId: string; rpm?: number }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts>();
  
  const [loadingList, setLoadingList] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [records, setRecords] = useState<DeviceFftRecord[]>([]);
  const [selectedRecordId, setSelectedRecordId] = useState<string>();
  const [activeAxis, setActiveAxis] = useState<'x' | 'y' | 'z'>('x');
  const [viewMode, setViewMode] = useState<'low' | 'full'>('low');
  const [fftData, setFftData] = useState<DeviceFftData | null>();

  useEffect(() => {
    if (!deviceId) return;
    let active = true;
    setLoadingList(true);
    listDeviceFftRecords(deviceId)
      .then((items) => {
        if (!active) return;
        setRecords(items);
        if (items.length > 0) {
          setSelectedRecordId(items[0].id);
        } else {
          setFftData(null);
        }
      })
      .catch((error) => {
        if (active) message.error(error?.data?.detail || error?.message || '无法获取FFT记录');
      })
      .finally(() => {
        if (active) setLoadingList(false);
      });
      
    return () => {
      active = false;
    };
  }, [deviceId]);

  useEffect(() => {
    if (!deviceId || !selectedRecordId) return;
    let active = true;
    setLoadingData(true);
    getDeviceFftData(deviceId, selectedRecordId)
      .then((data) => {
        if (!active) return;
        setFftData(data);
      })
      .catch((error) => {
        if (active) {
          message.error(error?.data?.detail || error?.message || '无法获取FFT数据');
          setFftData(null);
        }
      })
      .finally(() => {
        if (active) setLoadingData(false);
      });
      
    return () => {
      active = false;
    };
  }, [deviceId, selectedRecordId]);

  const chartOption = useMemo(() => {
    if (!fftData || fftData.freq_hz.length === 0) return null;
    
    let seriesName = '';
    let seriesData: number[] = [];
    if (activeAxis === 'x') {
      seriesName = 'X 轴';
      seriesData = fftData.x_axis;
    } else if (activeAxis === 'y') {
      seriesName = 'Y 轴';
      seriesData = fftData.y_axis;
    } else {
      seriesName = 'Z 轴';
      seriesData = fftData.z_axis;
    }

    let displayFreq = fftData.freq_hz;
    let displaySeriesData = seriesData;
    
    if (viewMode === 'low') {
      const maxIndex = fftData.freq_hz.findIndex(f => Number(f) > 1000);
      if (maxIndex !== -1) {
        displayFreq = fftData.freq_hz.slice(0, maxIndex);
        displaySeriesData = seriesData.slice(0, maxIndex);
      }
    }

    const markLineData: any[] = [];
    if (viewMode === 'low' && rpm && rpm > 0) {
      const baseHz = rpm / 60;
      const maxFreq = Number(fftData.freq_hz[fftData.freq_hz.length - 1]);
      const maxHz = Math.min(1000, maxFreq);
      for (let i = 1; i <= 10; i++) {
        const harmonicHz = baseHz * i;
        if (harmonicHz > maxHz) break;
        
        const index = Math.round((harmonicHz / maxFreq) * (fftData.freq_hz.length - 1));
        if (index < displayFreq.length) {
          markLineData.push({
            xAxis: index,
            label: {
              formatter: `${i}x (${harmonicHz.toFixed(1)}Hz)`,
              position: 'insideEndTop',
            },
            lineStyle: {
              type: 'dashed',
              color: i === 1 ? '#fa541c' : '#faad14',
              opacity: 0.6,
            },
          });
        }
      }
    }

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          const xValue = Number(params[0].axisValue).toFixed(2);
          let result = `${xValue} Hz<br/>`;
          params.forEach((param: any) => {
            if (param.seriesName) {
              result += `${param.marker} ${param.seriesName}: ${Number(param.value).toFixed(4)} g<br/>`;
            }
          });
          return result;
        },
      },
      legend: {
        data: [seriesName],
        bottom: 0,
      },
      grid: {
        top: 20,
        left: 40,
        right: 40,
        bottom: 40,
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: displayFreq,
        name: 'Hz',
        axisLabel: {
          formatter: (value: string) => Number(value).toFixed(2),
        },
      },
      yAxis: {
        type: 'value',
        name: '振幅 (g)',
        scale: true,
      },
      dataZoom: [
        { type: 'inside', xAxisIndex: 0 },
        { type: 'slider', xAxisIndex: 0, bottom: 20, height: 20 },
      ],
      series: [
        {
          name: seriesName,
          type: 'line',
          showSymbol: false,
          data: displaySeriesData,
          lineStyle: { width: 1 },
          markLine: markLineData.length > 0 ? {
            symbol: ['none', 'none'],
            data: markLineData,
          } : undefined,
        },
      ],
    };
  }, [fftData, activeAxis, viewMode]);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }
    
    if (chartOption) {
      chartInstance.current.setOption(chartOption, true);
    } else {
      chartInstance.current.clear();
    }
    
    const handleResize = () => chartInstance.current?.resize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [chartOption]);

  if (!loadingList && records.length === 0) {
    return null;
  }

  const selectedRecord = records.find(r => r.id === selectedRecordId);

  return (
    <Card style={{ marginBottom: 16 }} title="FFT 频谱分析">
      <Space style={{ marginBottom: 16 }} wrap>
        <Typography.Text type="secondary">选择记录</Typography.Text>
        <Select
          style={{ width: 200 }}
          value={selectedRecordId}
          onChange={setSelectedRecordId}
          loading={loadingList}
          options={records.map((r) => ({
            label: dayjs(r.ts_ms).format('YYYY-MM-DD HH:mm:ss'),
            value: r.id,
          }))}
        />
        <Typography.Text type="secondary" style={{ marginLeft: 16 }}>查看轴</Typography.Text>
        <Segmented
          options={[
            { label: 'X 轴', value: 'x' },
            { label: 'Y 轴', value: 'y' },
            { label: 'Z 轴', value: 'z' },
          ]}
          value={activeAxis}
          onChange={(val) => setActiveAxis(val as 'x' | 'y' | 'z')}
        />
        <Typography.Text type="secondary" style={{ marginLeft: 16 }}>频段显示</Typography.Text>
        <Segmented
          options={[
            { label: '低频分析 (0-1000Hz)', value: 'low' },
            { label: '全频带展示', value: 'full' },
          ]}
          value={viewMode}
          onChange={(val) => setViewMode(val as 'low' | 'full')}
        />
        {selectedRecord && (
          <Typography.Text type="secondary" style={{ marginLeft: 16 }}>
            额定转速: {rpm || '未知'} RPM | 采样频率: {selectedRecord.fs_hz} Hz | 点数: {selectedRecord.points} | 量程: {selectedRecord.range_g}g
          </Typography.Text>
        )}
      </Space>
      
      <Spin spinning={loadingData}>
        {fftData ? (
          <div ref={chartRef} style={{ width: '100%', height: 400 }} />
        ) : (
          <Empty description="未能加载频谱数据" style={{ margin: '40px 0' }} />
        )}
      </Spin>
    </Card>
  );
};

export default DeviceFftCard;

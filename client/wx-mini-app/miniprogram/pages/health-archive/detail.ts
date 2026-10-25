import {
  getDeviceHealthArchive,
  getDevicePointTrends,
} from '../../utils/api'
import * as echarts from '../../components/ec-canvas/echarts'

const app = getApp<IAppOption>()
const wxApi = wx as any

const STATUS_META: Record<string, { label: string; color: string }> = {
  normal: { label: '正常', color: '#00C897' },
  attention: { label: '关注', color: '#F2C94C' },
  abnormal: { label: '异常', color: '#FA8C16' },
  warning: { label: '告警', color: '#FF3366' },
  critical: { label: '严重', color: '#820014' },
  missed: { label: '缺口', color: '#8C8C8C' },
  // waiting: { label: '补传', color: '#1677FF' },
  // processing: { label: '处理中', color: '#13C2C2' },
  no_data: { label: '无数据', color: '#263247' },
}

const ARCHIVE_RANGES = [
  { label: '1天', value: 1 }, { label: '3天', value: 3 },
  { label: '7天', value: 7 },
]

const TREND_RANGES = [
  { label: '1天', value: 1 }, { label: '3天', value: 3 },
  { label: '7天', value: 7 }, { label: '14天', value: 14 },
  { label: '30天', value: 30 }, { label: '90天', value: 90 },
  { label: '半年', value: 180 }, { label: '1年', value: 365 },
]

const WINDOW_OPTIONS: Record<number, Array<{ label: string; value: number }>> = {
  1: [{ label: '原始数据', value: 0 }, { label: '30分钟', value: 30 }, { label: '1小时', value: 60 }],
  3: [{ label: '原始数据', value: 0 }, { label: '1小时', value: 60 }, { label: '2小时', value: 120 }],
  7: [{ label: '1小时', value: 60 }, { label: '2小时', value: 120 }, { label: '4小时', value: 240 }],
  14: [{ label: '2小时', value: 120 }, { label: '4小时', value: 240 }, { label: '8小时', value: 480 }],
  30: [{ label: '4小时', value: 240 }, { label: '8小时', value: 480 }, { label: '24小时', value: 1440 }],
  90: [{ label: '12小时', value: 720 }, { label: '24小时', value: 1440 }],
  180: [{ label: '24小时', value: 1440 }],
  365: [{ label: '24小时', value: 1440 }],
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function formatTime(value: string | number, withYear = false) {
  const date = new Date(value)
  const prefix = withYear ? `${date.getFullYear()}-` : ''
  return `${prefix}${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function decorateBucket(bucket: any) {
  const meta = STATUS_META[bucket.status] || STATUS_META.no_data
  return {
    ...bucket,
    statusLabel: meta.label,
    color: meta.color,
    rangeLabel: `${formatTime(bucket.startAt)} 至 ${formatTime(bucket.endAt)}`,
  }
}

function buildTimelineDays(buckets: any[]) {
  const days: any[] = []
  for (let index = 0; index < buckets.length; index += 24) {
    const dayBuckets = buckets.slice(index, index + 24)
    if (!dayBuckets.length) continue
    days.push({
      key: dayBuckets[0].startAt,
      label: `${formatTime(dayBuckets[0].startAt)} 至 ${formatTime(dayBuckets[dayBuckets.length - 1].endAt)}`,
      buckets: dayBuckets,
    })
  }
  return days
}

Page({
  trendChart: null as any,

  data: {
    deviceId: '',
    deviceName: '',
    loading: true,
    errorText: '',
    archive: null as any,
    points: [] as any[],
    pointIndex: 0,
    selectedLocationId: '',
    selectedSensorText: '',
    rangeOptions: ARCHIVE_RANGES,
    rangeIndex: 0,
    buckets: [] as any[],
    timelineDays: [] as any[],
    selectedBucket: null as any,
    legend: Object.keys(STATUS_META).map((key) => ({ key, ...STATUS_META[key] })),

    trendEc: { lazyLoad: true },
    trendLoading: false,
    trendError: '',
    trendData: null as any,
    trendTab: 'temperature',
    trendRangeOptions: TREND_RANGES,
    trendRangeIndex: 1,
    trendWindowOptions: WINDOW_OPTIONS[3],
    trendWindowIndex: 0,
    fullscreenChart: '',
  },

  async onLoad(options: Record<string, string>) {
    const deviceId = options.id || ''
    const deviceName = decodeURIComponent(options.name || '')
    this.setData({ deviceId, deviceName })
    if (deviceName) wx.setNavigationBarTitle({ title: `${deviceName} · 健康档案` })
    await this.loadArchive(true)
  },

  async onPullDownRefresh() {
    try {
      await this.loadArchive(true)
    } finally {
      wx.stopPullDownRefresh()
    }
  },

  onUnload() {
    if (this.data.fullscreenChart) {
      wxApi.setPageOrientation({ orientation: 'portrait' })
    }
  },

  async loadArchive(refreshTrend = false) {
    const token = app.globalData.session?.accessToken
    const { deviceId, rangeOptions, rangeIndex } = this.data
    if (!token || !deviceId) return

    const rangeDays = rangeOptions[rangeIndex].value
    const end = new Date()
    const start = new Date(end)
    start.setTime(end.getTime() - rangeDays * 24 * 60 * 60 * 1000)

    this.setData({ loading: true, errorText: '' })
    wx.showNavigationBarLoading()
    try {
      const requestParams = {
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        interval_hours: 1,
        location_id: this.data.selectedLocationId || undefined,
      }
      let archive: any
      try {
        archive = await getDeviceHealthArchive(token, deviceId, requestParams)
      } catch (error: any) {
        if (
          requestParams.location_id
          && String(error?.message || '').includes('Monitoring point not found')
        ) {
          archive = await getDeviceHealthArchive(token, deviceId, {
            ...requestParams,
            location_id: undefined,
          })
        } else {
          throw error
        }
      }
      const points = Array.isArray(archive?.points) ? archive.points : []
      const currentLocationIsValid = points.some(
        (point: any) => point.id === this.data.selectedLocationId,
      )
      const selectedLocationId = currentLocationIsValid
        ? this.data.selectedLocationId
        : (archive?.selectedLocationId || points[0]?.id || '')
      const pointIndex = Math.max(0, points.findIndex((point: any) => point.id === selectedLocationId))
      const point = points[pointIndex]
      const buckets = (archive?.buckets || []).map(decorateBucket)
      const selectedSensorText = point?.sensor
        ? [point.sensor.sn, point.sensor.description].filter(Boolean).join(' / ')
        : ''

      this.setData({
        archive,
        deviceName: archive?.device?.name || this.data.deviceName,
        points,
        selectedLocationId,
        pointIndex,
        selectedSensorText,
        buckets,
        timelineDays: buildTimelineDays(buckets),
        selectedBucket: null,
        loading: false,
      }, () => {
        if (refreshTrend && selectedLocationId) this.loadTrend()
      })
    } catch (error: any) {
      console.error('[health archive]', error)
      this.setData({ loading: false, errorText: error?.message || '健康档案加载失败' })
      wx.showToast({ title: '健康档案加载失败', icon: 'none' })
    } finally {
      wx.hideNavigationBarLoading()
    }
  },

  changeArchiveRange(e: any) {
    this.setData({ rangeIndex: Number(e.currentTarget.dataset.index) }, () => this.loadArchive(false))
  },

  changePoint(e: any) {
    const pointIndex = Number(e.detail.value)
    const point = this.data.points[pointIndex]
    this.setData({ pointIndex, selectedLocationId: point?.id || '' }, () => this.loadArchive(true))
  },

  selectBucket(e: any) {
    const startAt = e.currentTarget.dataset.start
    const bucket = this.data.buckets.find((item: any) => item.startAt === startAt)
    if (!bucket) return
    this.setData({ selectedBucket: bucket })
  },

  async loadTrend() {
    const token = app.globalData.session?.accessToken
    const locationId = this.data.selectedLocationId
    if (!token || !locationId) return
    const rangeDays = this.data.trendRangeOptions[this.data.trendRangeIndex].value
    const windowMinutes = this.data.trendWindowOptions[this.data.trendWindowIndex].value
    this.setData({ trendLoading: true, trendError: '' })
    try {
      const trendData = await getDevicePointTrends(token, this.data.deviceId, {
        location_id: locationId,
        range_days: rangeDays,
        window_minutes: windowMinutes,
      })
      this.setData({ trendData }, () => this.renderTrendChart())
    } catch (error: any) {
      console.error('[point trend]', error)
      this.setData({ trendData: null, trendError: error?.message || '趋势加载失败' })
    } finally {
      this.setData({ trendLoading: false })
    }
  },

  changeTrendRange(e: any) {
    const trendRangeIndex = Number(e.detail.value)
    const rangeDays = this.data.trendRangeOptions[trendRangeIndex].value
    this.setData({
      trendRangeIndex,
      trendWindowOptions: WINDOW_OPTIONS[rangeDays],
      trendWindowIndex: 0,
    }, () => this.loadTrend())
  },

  changeTrendWindow(e: any) {
    this.setData({ trendWindowIndex: Number(e.detail.value) }, () => this.loadTrend())
  },

  switchTrendTab(e: any) {
    this.setData({ trendTab: e.currentTarget.dataset.tab }, () => this.renderTrendChart())
  },

  toggleChartFullscreen(e: any) {
    const requestedChart = e.currentTarget.dataset.chart
    const fullscreenChart = this.data.fullscreenChart === requestedChart ? '' : requestedChart
    this.setData({ fullscreenChart }, () => {
      wxApi.setPageOrientation({ orientation: fullscreenChart ? 'landscape' : 'portrait' })
      setTimeout(() => this.resizeChart(), 500)
    })
  },

  resizeChart() {
    const chart = this.trendChart
    const selector = '#trend-chart-box'
    if (!chart) {
      this.renderTrendChart()
      return
    }
    wx.createSelectorQuery().select(selector).boundingClientRect((rect) => {
      if (rect) chart.resize({ width: rect.width, height: rect.height })
      else chart.resize()
    }).exec()
  },

  renderTrendChart() {
    const data = this.data.trendData
    if (!data?.timestamps?.length) {
      if (this.trendChart) this.trendChart.clear()
      return
    }
    const vibration = this.data.trendTab === 'vibration'
    const source = vibration ? data.vibration : data.temperature
    const unit = vibration ? 'mm/s' : '°C'
    const points = data.timestamps.map((time: string, index: number) => {
      const item = source[index]
      const value = item ? (vibration && !data.meta?.raw ? item.max : item.value) : null
      return [time, value]
    })
    const series: any[] = [{
      name: vibration ? '振动' : '设备温度',
      type: 'line', data: points, showSymbol: points.length <= 80,
      connectNulls: false, smooth: false,
      lineStyle: { color: vibration ? '#00D2FF' : '#FA8C16', width: 2 },
      itemStyle: { color: vibration ? '#00D2FF' : '#FA8C16' },
    }]
    if (!vibration && Array.isArray(data.ambientTemperature)) {
      const ambientPoints = data.timestamps.map((time: string, index: number) => [
        time,
        data.ambientTemperature[index] ?? null,
      ])
      if (ambientPoints.some((pt: any) => pt[1] !== null && pt[1] !== undefined)) {
        series.push({
          name: '环境温度 (基准)',
          type: 'line',
          data: ambientPoints,
          showSymbol: false,
          connectNulls: true,
          smooth: false,
          lineStyle: { color: '#8C8C8C', width: 1.5, type: 'dashed' },
          itemStyle: { color: '#8C8C8C' },
        })
      }
    }
    const option = {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: series.length > 1 ? { top: 0, textStyle: { color: 'rgba(255,255,255,0.65)', fontSize: 11 } } : undefined,
      grid: { top: 30, left: 52, right: 20, bottom: 48 },
      xAxis: { type: 'time', axisLabel: { hideOverlap: true } },
      yAxis: { type: 'value', name: unit, scale: true },
      dataZoom: [{ type: 'inside' }],
      series,
    }
    const component = this.selectComponent('#health-trend-chart') as any
    if (!component) return
    if (!this.trendChart) {
      component.init((canvas: any, width: number, height: number, dpr: number) => {
        const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr })
        canvas.setChart(chart)
        chart.setOption(option)
        this.trendChart = chart
        return chart
      })
    } else {
      this.trendChart.setOption(option, true)
    }
  },

  retryArchive() { this.loadArchive(true) },
  retryTrend() { this.loadTrend() },
})

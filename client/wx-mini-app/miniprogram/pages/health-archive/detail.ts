import {
  getDeviceFftData,
  getDeviceFftRecords,
  getDeviceHealthArchive,
  getDevicePointTrends,
} from '../../utils/api'
import * as echarts from '../../components/ec-canvas/echarts'

const app = getApp<IAppOption>()

const STATUS_META: Record<string, { label: string; color: string }> = {
  normal: { label: '正常', color: '#00C897' },
  attention: { label: '关注', color: '#F2C94C' },
  abnormal: { label: '异常', color: '#FA8C16' },
  warning: { label: '告警', color: '#FF3366' },
  critical: { label: '严重', color: '#820014' },
  missed: { label: '诊断缺口', color: '#8C8C8C' },
  waiting: { label: '等待补传', color: '#1677FF' },
  processing: { label: '处理中', color: '#13C2C2' },
  no_data: { label: '无数据', color: '#263247' },
}

const ARCHIVE_RANGES = [
  { label: '1天', value: 1 }, { label: '3天', value: 3 },
  { label: '7天', value: 7 }, { label: '30天', value: 30 },
  { label: '90天', value: 90 }, { label: '1年', value: 365 },
]

const INTERVALS = [
  { label: '1小时', value: 1 }, { label: '4小时', value: 4 },
  { label: '8小时', value: 8 }, { label: '24小时', value: 24 },
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
    shortTime: formatTime(bucket.startAt),
    hourLabel: `${pad(new Date(bucket.startAt).getHours())}:00`,
    dayLabel: pad(new Date(bucket.startAt).getDate()),
  }
}

function buildCalendarMonths(buckets: any[]) {
  const months: Array<any> = []
  buckets.forEach((bucket) => {
    const date = new Date(bucket.startAt)
    const key = `${date.getFullYear()}-${pad(date.getMonth() + 1)}`
    let month = months.find((item) => item.key === key)
    if (!month) {
      month = {
        key,
        label: `${date.getFullYear()}年${date.getMonth() + 1}月`,
        placeholders: Array.from({ length: new Date(date.getFullYear(), date.getMonth(), 1).getDay() }),
        buckets: [],
      }
      months.push(month)
    }
    month.buckets.push(decorateBucket(bucket))
  })
  return months
}

Page({
  trendChart: null as any,
  fftChart: null as any,

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
    intervalOptions: INTERVALS,
    intervalIndex: 0,
    calendarMode: false,
    buckets: [] as any[],
    calendarMonths: [] as any[],
    selectedBucket: null as any,
    dayDetail: null as any,
    dayDetailLoading: false,
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

    fftEc: { lazyLoad: true },
    fftExpanded: false,
    fftListLoading: false,
    fftDataLoading: false,
    fftRecords: [] as any[],
    fftRecordIndex: 0,
    fftData: null as any,
    fftAxis: 'x',
    fftMode: 'low',
    fftError: '',
  },

  async onLoad(options: Record<string, string>) {
    const deviceId = options.id || ''
    const deviceName = decodeURIComponent(options.name || '')
    this.setData({ deviceId, deviceName })
    if (deviceName) wx.setNavigationBarTitle({ title: `${deviceName} · 健康档案` })
    await Promise.all([this.loadArchive(true), this.loadFftRecords()])
  },

  async onPullDownRefresh() {
    try {
      await Promise.all([this.loadArchive(true), this.loadFftRecords()])
    } finally {
      wx.stopPullDownRefresh()
    }
  },

  async loadArchive(refreshTrend = false) {
    const token = app.globalData.session?.accessToken
    const { deviceId, rangeOptions, rangeIndex, intervalOptions, intervalIndex } = this.data
    if (!token || !deviceId) return

    const rangeDays = rangeOptions[rangeIndex].value
    const calendarMode = rangeDays >= 30
    const end = new Date()
    const start = new Date(end)
    if (calendarMode) {
      start.setHours(0, 0, 0, 0)
      start.setDate(start.getDate() - rangeDays + 1)
    } else {
      start.setTime(end.getTime() - rangeDays * 24 * 60 * 60 * 1000)
    }

    this.setData({ loading: true, errorText: '' })
    wx.showNavigationBarLoading()
    try {
      const requestParams = {
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        interval_hours: calendarMode ? 24 : intervalOptions[intervalIndex].value,
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
        calendarMode,
        buckets,
        calendarMonths: calendarMode ? buildCalendarMonths(archive?.buckets || []) : [],
        selectedBucket: null,
        dayDetail: null,
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

  changeInterval(e: any) {
    this.setData({ intervalIndex: Number(e.detail.value) }, () => this.loadArchive(false))
  },

  changePoint(e: any) {
    const pointIndex = Number(e.detail.value)
    const point = this.data.points[pointIndex]
    this.setData({ pointIndex, selectedLocationId: point?.id || '' }, () => this.loadArchive(true))
  },

  selectBucket(e: any) {
    const startAt = e.currentTarget.dataset.start
    const bucket = this.data.buckets.find((item: any) => item.startAt === startAt)
      || this.data.calendarMonths.flatMap((month: any) => month.buckets).find((item: any) => item.startAt === startAt)
    if (!bucket) return
    this.setData({ selectedBucket: bucket, dayDetail: null })
    if (this.data.calendarMode) this.loadDayDetail(bucket)
  },

  async loadDayDetail(bucket: any) {
    const token = app.globalData.session?.accessToken
    if (!token) return
    const start = new Date(bucket.startAt)
    start.setHours(0, 0, 0, 0)
    const end = new Date(start.getTime() + 24 * 60 * 60 * 1000)
    this.setData({ dayDetailLoading: true })
    try {
      const detail = await getDeviceHealthArchive(token, this.data.deviceId, {
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        interval_hours: 1,
        location_id: this.data.selectedLocationId || undefined,
      })
      detail.buckets = (detail.buckets || []).map(decorateBucket)
      this.setData({ dayDetail: detail })
    } catch (error) {
      console.error('[day detail]', error)
      wx.showToast({ title: '当日明细加载失败', icon: 'none' })
    } finally {
      this.setData({ dayDetailLoading: false })
    }
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
    const option = {
      animation: false,
      tooltip: { trigger: 'axis' },
      grid: { top: 30, left: 52, right: 20, bottom: 48 },
      xAxis: { type: 'time', axisLabel: { hideOverlap: true } },
      yAxis: { type: 'value', name: unit, scale: true },
      dataZoom: [{ type: 'inside' }],
      series: [{
        type: 'line', data: points, showSymbol: points.length <= 80,
        connectNulls: false, smooth: false,
        lineStyle: { color: vibration ? '#00D2FF' : '#FA8C16', width: 2 },
        itemStyle: { color: vibration ? '#00D2FF' : '#FA8C16' },
      }],
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

  async loadFftRecords() {
    const token = app.globalData.session?.accessToken
    if (!token || !this.data.deviceId) return
    this.setData({ fftListLoading: true, fftError: '' })
    try {
      const records = await getDeviceFftRecords(token, this.data.deviceId)
      const fftRecords = (records || []).map((record: any) => ({
        ...record,
        label: formatTime(record.ts_ms, true),
      }))
      this.setData({ fftRecords, fftRecordIndex: 0, fftData: null })
      if (this.data.fftExpanded && fftRecords.length) await this.loadFftData()
    } catch (error: any) {
      this.setData({ fftError: error?.message || 'FFT记录加载失败' })
    } finally {
      this.setData({ fftListLoading: false })
    }
  },

  toggleFft() {
    const fftExpanded = !this.data.fftExpanded
    this.setData({ fftExpanded }, () => {
      if (fftExpanded && this.data.fftRecords.length && !this.data.fftData) this.loadFftData()
    })
  },

  changeFftRecord(e: any) {
    this.setData({ fftRecordIndex: Number(e.detail.value) }, () => this.loadFftData())
  },

  switchFftAxis(e: any) {
    this.setData({ fftAxis: e.currentTarget.dataset.axis }, () => this.renderFftChart())
  },

  switchFftMode(e: any) {
    this.setData({ fftMode: e.currentTarget.dataset.mode }, () => this.renderFftChart())
  },

  async loadFftData() {
    const token = app.globalData.session?.accessToken
    const record = this.data.fftRecords[this.data.fftRecordIndex]
    if (!token || !record) return
    this.setData({ fftDataLoading: true, fftError: '' })
    try {
      const fftData = await getDeviceFftData(token, this.data.deviceId, record.id)
      this.setData({ fftData }, () => this.renderFftChart())
    } catch (error: any) {
      this.setData({ fftData: null, fftError: error?.message || 'FFT数据加载失败' })
    } finally {
      this.setData({ fftDataLoading: false })
    }
  },

  renderFftChart() {
    const data = this.data.fftData
    if (!data?.freq_hz?.length) return
    const axisData = data[`${this.data.fftAxis}_axis`] || []
    const pairs: Array<[number, number]> = []
    data.freq_hz.forEach((frequency: number, index: number) => {
      if (this.data.fftMode === 'full' || Number(frequency) <= 1000) {
        pairs.push([Number(frequency), Number(axisData[index] || 0)])
      }
    })
    const markLineData: any[] = []
    const rpm = Number(this.data.archive?.device?.rpm || 0)
    if (this.data.fftMode === 'low' && rpm > 0) {
      const baseHz = rpm / 60
      for (let index = 1; index <= 10 && baseHz * index <= 1000; index += 1) {
        markLineData.push({ xAxis: baseHz * index, name: `${index}x` })
      }
    }
    const option = {
      animation: false,
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      grid: { top: 24, left: 54, right: 20, bottom: 46 },
      xAxis: { type: 'value', name: 'Hz', scale: true },
      yAxis: { type: 'value', name: 'g', scale: true },
      dataZoom: [{ type: 'inside' }],
      series: [{
        type: 'line', data: pairs, showSymbol: false, lineStyle: { color: '#00D2FF', width: 1 },
        markLine: markLineData.length ? {
          symbol: ['none', 'none'], label: { formatter: '{b}' }, data: markLineData,
        } : undefined,
      }],
    }
    const component = this.selectComponent('#health-fft-chart') as any
    if (!component) return
    if (!this.fftChart) {
      component.init((canvas: any, width: number, height: number, dpr: number) => {
        const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr })
        canvas.setChart(chart)
        chart.setOption(option)
        this.fftChart = chart
        return chart
      })
    } else {
      this.fftChart.setOption(option, true)
    }
  },

  retryArchive() { this.loadArchive(true) },
  retryTrend() { this.loadTrend() },
  retryFft() { this.data.fftRecords.length ? this.loadFftData() : this.loadFftRecords() },
})

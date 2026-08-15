import { getProcessDevices, getDeviceSpecComparison, getDeviceCategories, getDeviceSpecs } from '../../utils/api'
import * as echarts from '../../components/ec-canvas/echarts'

const app = getApp<IAppOption>()

function flattenCategories(list: any[], parentId: string | null = null, depth = 0): any[] {
  let result: any[] = []
  const children = list.filter(c => (c.parent_id || null) === parentId)
  const prefix = depth === 0 ? '' : '　'.repeat(depth - 1) + '├─ '
  children.forEach(child => {
    result.push({ id: child.id, name: child.name, label: prefix + child.name })
    result = result.concat(flattenCategories(list, child.id, depth + 1))
  })
  return result
}

const RANGE_OPTIONS = [
  { label: '近 1 天', value: 1 },  { label: '近 3 天', value: 3 },
  { label: '近 1 周', value: 7 },  { label: '近 2 周', value: 14 },
  { label: '近 1 月', value: 30 }, { label: '近 3 月', value: 90 },
  { label: '近半年', value: 180 }, { label: '近 1 年', value: 365 },
]

const WINDOW_OPTIONS_MAP: Record<number, Array<{ label: string; value: number }>> = {
  1:   [{ label: '原始数据', value: 0 }, { label: '30 分钟', value: 30 }, { label: '1 小时', value: 60 }],
  3:   [{ label: '原始数据', value: 0 }, { label: '1 小时', value: 60 }, { label: '2 小时', value: 120 }, { label: '4 小时', value: 240 }],
  7:   [{ label: '1 小时', value: 60 }, { label: '2 小时', value: 120 }, { label: '4 小时', value: 240 }, { label: '8 小时', value: 480 }],
  14:  [{ label: '2 小时', value: 120 }, { label: '4 小时', value: 240 }, { label: '8 小时', value: 480 }, { label: '12 小时', value: 720 }],
  30:  [{ label: '4 小时', value: 240 }, { label: '8 小时', value: 480 }, { label: '12 小时', value: 720 }, { label: '24 小时', value: 1440 }],
  90:  [{ label: '12 小时', value: 720 }, { label: '24 小时', value: 1440 }],
  180: [{ label: '24 小时', value: 1440 }],
  365: [{ label: '24 小时', value: 1440 }],
}

Page({
  data: {
    specId: '',
    specName: '',
    activeTab: 'temperature',
    loading: false,
    drawerVisible: false,
    ec: { lazyLoad: true },

    // Param 1
    categories: [] as any[],
    categoryIndex: 0,
    // Param 2
    deviceSpecs: [] as any[],
    filteredSpecs: [] as any[],
    specIndex: 0,
    // Param 3
    processDevices: [] as any[],
    groupIndex: 0,
    // Param 4
    locations: [] as any[],
    locationIndex: 0,
    // Param 5
    rangeOptions: RANGE_OPTIONS,
    rangeIndex: 0,
    // Param 6
    windowOptions: WINDOW_OPTIONS_MAP[1],
    windowIndex: 0,

    data: null as any,
    metaText: '',
    isFullscreen: false,
  },

  async onLoad(options: any) {
    this.setData({
      specId: options.id || '',
      specName: decodeURIComponent(options.name || '')
    })
    this.chartComponent = this.selectComponent('#mychart-dom-line')
    wx.showNavigationBarLoading()
    await this.init()
  },

  onPullDownRefresh() {
    this.applyParams()
  },

  /**
   * Exactly 4 requests, matching the web page:
   * 1. device-categories
   * 2. device-specs (all, no filter)
   * 3. process-devices?device_spec_id=...
   * 4. comparison?process_device_id=...
   */
  async init() {
    const session = app.globalData.session
    if (!session?.accessToken || !this.data.specId) {
      wx.hideNavigationBarLoading()
      return
    }
    const token = session.accessToken
    const specId = this.data.specId

    try {
      // Request 1 + 2: parallel — categories and ALL specs (no filter)
      const [rawCats, rawSpecs] = await Promise.all([
        getDeviceCategories(token),
        getDeviceSpecs(token, 0, 100),
      ])

      const catList = Array.isArray(rawCats) ? rawCats
        : Array.isArray((rawCats as any)?.items) ? (rawCats as any).items : []
      const specList = Array.isArray(rawSpecs) ? rawSpecs
        : Array.isArray((rawSpecs as any)?.items) ? (rawSpecs as any).items : []

      const categories = flattenCategories(catList)

      // Find current spec in the list to get its category_id
      const specIndex = Math.max(0, specList.findIndex((s: any) => s.id === specId))
      const currentSpec = specList[specIndex]
      const categoryId = currentSpec?.device_category_id
      const categoryIndex = categoryId
        ? Math.max(0, categories.findIndex((c: any) => c.id === categoryId))
        : 0
      
      const catId = categories[categoryIndex]?.id
      const filteredSpecs = catId ? specList.filter((s: any) => s.device_category_id === catId && s.process_device_count > 0) : []
      const newSpecIndex = Math.max(0, filteredSpecs.findIndex((s: any) => s.id === specId))

      this.setData({ 
        categories, categoryIndex, 
        deviceSpecs: specList, filteredSpecs, 
        specIndex: newSpecIndex 
      })

      // Request 3: process-devices for this spec
      await this.loadGroupsBySpec(specId)

    } catch (err: any) {
      console.error('[init]', err)
      wx.hideNavigationBarLoading()
      wx.showToast({ title: '初始化失败', icon: 'none' })
    }
  },

  async loadGroupsBySpec(specId: string) {
    const session = app.globalData.session
    if (!session?.accessToken || !specId) return

    try {
      // Request 3: process-devices?device_spec_id=specId
      const raw = await getProcessDevices(session.accessToken, 0, 100, specId)
      const list = Array.isArray(raw) ? raw : []
      console.log('[groups] specId:', specId, 'count:', list.length, 'ids:', list.map((d:any)=>d.id).join(','))
      const options = list.map((d: any) => ({
        id: d.id,
        label: d.process?.name || d.code || d.id
      }))
      this.setData({ processDevices: options, groupIndex: 0, data: null, locations: [], locationIndex: 0, metaText: '' })
      this.chart = null
      this.chartComponent = null

      if (options.length > 0) {
        console.log('[groups] calling doFetch with processDeviceId:', options[0].id)
        await this.doFetch(
          specId,
          options[0].id,
          undefined,
          this.data.rangeOptions[this.data.rangeIndex].value,
          this.data.windowOptions[this.data.windowIndex].value
        )
      } else {
        wx.hideNavigationBarLoading()
      }
    } catch (err: any) {
      console.error('[loadGroupsBySpec]', err)
      wx.hideNavigationBarLoading()
    }
  },

  async doFetch(
    specId: string,
    processDeviceId: string,
    locationId: string | undefined,
    rangeDays: number,
    windowMinutes: number,
  ) {
    const session = app.globalData.session
    if (!session?.accessToken || !specId || !processDeviceId) {
      wx.hideNavigationBarLoading()
      wx.stopPullDownRefresh()
      return
    }

    this.setData({ loading: true })
    wx.showNavigationBarLoading()
    try {
      console.log('[doFetch] calling API specId:', specId, 'pdId:', processDeviceId, 'range:', rangeDays, 'window:', windowMinutes)
      // Request 4: comparison
      const data = await getDeviceSpecComparison(session.accessToken, specId, {
        process_device_id: processDeviceId,
        location_id: locationId || undefined,
        range_days: rangeDays,
        window_minutes: windowMinutes,
      })
      console.log('[doFetch] API success, series length:', data?.series?.length)

      const newLocations: any[] = Array.isArray(data?.locations) ? data.locations : []
      const selectedId = locationId || data?.selectedLocationId || newLocations[0]?.id
      const locationIndex = Math.max(0, newLocations.findIndex((l: any) => l.id === selectedId))
      const locationName = newLocations[locationIndex]?.name || ''

      const metaText = data?.meta
        ? `测点: ${locationName} · ${data.meta.deviceCount} 台 · ${data.meta.pointCount} 个数据点`
        : ''

      this.setData({ data, locations: newLocations, locationIndex, loading: false, metaText }, () => {
        this.renderChart()
      })
    } catch (err: any) {
      console.error('[doFetch]', err)
      this.setData({ loading: false })
      wx.showToast({ title: '获取对比数据失败', icon: 'none' })
    } finally {
      wx.hideNavigationBarLoading()
      wx.stopPullDownRefresh()
    }
  },

  renderChart() {
    if (!this.chartComponent) {
      this.chartComponent = this.selectComponent('#mychart-dom-line')
    }
    const { data, activeTab } = this.data
    if (!this.chartComponent || !data?.series) {
      console.warn('[renderChart] Aborted: component or data missing', { hasComp: !!this.chartComponent, hasData: !!data?.series })
      return
    }
    const isVib = activeTab === 'vibration'
    const unit = isVib ? 'mm/s' : '°C'

    const fallbackColors = ['#1677FF', '#52C41A', '#FA8C16', '#F5222D', '#722ED1', '#13C2C2', '#EB2F96', '#FADB14']

    const series = data.series.map((item: any, idx: number) => {
      const src = isVib ? item.vibration : item.temperature
      const pts = (item.timestamps || []).map((ts: string, i: number) => {
        const v = src?.[i]
        return [ts, v ? (v.value ?? v.max ?? null) : null]
      })
      const color = item.device?.color || fallbackColors[idx % fallbackColors.length]
      item._displayColor = color
      return {
        name: item.device?.code || item.device?.name || '?',
        type: 'line', smooth: true, showSymbol: false,
        data: pts, itemStyle: { color }
      }
    })

    // Update the local data to include _displayColor so the wxml can read it
    this.setData({ data: this.data.data })

    const option = {
      color: data.series.map((s: any, idx: number) => s.device?.color || fallbackColors[idx % fallbackColors.length]),
      tooltip: {
        trigger: 'axis',
        formatter: (ps: any[]) =>
          ps.map((p: any) => `${p.seriesName}: ${p.value[1] != null ? Number(p.value[1]).toFixed(2) : '--'} ${unit}`).join('\n')
      },
      grid: { top: 20, left: 50, right: 20, bottom: 30 },
      xAxis: {
        type: 'time',
        axisLabel: {
          hideOverlap: true,
          formatter: (v: number) => {
            const d = new Date(v)
            const dateStr = `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
            const timeStr = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
            const rangeDays = this.data.rangeOptions?.[this.data.rangeIndex]?.value || 1
            return rangeDays <= 7 ? `${dateStr}\n${timeStr}` : dateStr
          }
        }
      },
      yAxis: { type: 'value', name: unit, scale: true },
      series,
    }

    if (!this.chart) {
      this.chartComponent.init((canvas: any, w: number, h: number, dpr: number) => {
        const chart = echarts.init(canvas, null, { width: w, height: h, devicePixelRatio: dpr })
        chart.setOption(option)
        this.chart = chart
        return chart
      })
    } else {
      this.chart.setOption(option, true)
    }
  },

  switchTab(e: any) {
    this.setData({ activeTab: e.currentTarget.dataset.tab })
    this.renderChart()
  },

  toggleFullscreen() {
    const nextState = !this.data.isFullscreen
    this.setData({ isFullscreen: nextState }, () => {
      wx.setPageOrientation({
        orientation: nextState ? 'landscape' : 'portrait'
      })
      // Small delay to allow orientation to change and CSS to settle before resizing canvas
      setTimeout(() => {
        if (this.chart) {
          const query = wx.createSelectorQuery()
          query.select('.chart-box').boundingClientRect((res) => {
            if (res) {
              this.chart.resize({
                width: res.width,
                height: res.height
              })
            } else {
              this.chart.resize()
            }
          }).exec()
        } else {
          this.renderChart()
        }
      }, 500)
    })
  },

  openDrawer() { this.setData({ drawerVisible: true }) },
  closeDrawer() { this.setData({ drawerVisible: false }) },

  applyParams() {
    this.setData({ drawerVisible: false })
    const { specId, processDevices, groupIndex, locations, locationIndex, rangeOptions, rangeIndex, windowOptions, windowIndex } = this.data
    this.doFetch(
      specId,
      processDevices[groupIndex]?.id,
      locations[locationIndex]?.id,
      rangeOptions[rangeIndex].value,
      windowOptions[windowIndex].value,
    )
  },

  onCategoryChange(e: any) {
    const idx = Number(e.detail.value)
    const cat = this.data.categories[idx]
    if (!cat?.id) return
    this.setData({ categoryIndex: idx })
    const filtered = this.data.deviceSpecs.filter((s: any) => s.device_category_id === cat.id && s.process_device_count > 0)
    if (filtered.length > 0) {
      const specIndex = 0
      const spec = filtered[specIndex]
      this.setData({
        filteredSpecs: filtered,
        specIndex,
        specId: spec.id,
        specName: `${spec.name} ${spec.model || ''}`,
        processDevices: [], groupIndex: 0,
        locations: [], locationIndex: 0,
        data: null, metaText: ''
      })
      this.chart = null
      this.chartComponent = null
      this.loadGroupsBySpec(spec.id)
    } else {
      this.setData({
        filteredSpecs: [],
        specIndex: 0,
        specId: '',
        specName: '',
        processDevices: [], groupIndex: 0,
        locations: [], locationIndex: 0,
        data: null, metaText: ''
      })
    }
  },

  onSpecChange(e: any) {
    const idx = Number(e.detail.value)
    const spec = this.data.filteredSpecs[idx]
    if (!spec?.id) return
    this.setData({
      specIndex: idx, 
      specId: spec.id,
      specName: `${spec.name} ${spec.model || ''}`,
      processDevices: [], groupIndex: 0,
      locations: [], locationIndex: 0,
      data: null, metaText: ''
    })
    this.chart = null
    this.chartComponent = null
    this.loadGroupsBySpec(spec.id)
  },

  onGroupChange(e: any) {
    const idx = Number(e.detail.value)
    const { specId, processDevices, rangeOptions, rangeIndex, windowOptions, windowIndex } = this.data
    this.setData({ groupIndex: idx, locations: [], locationIndex: 0, data: null, metaText: '' })
    this.chart = null
    this.chartComponent = null
    this.doFetch(specId, processDevices[idx]?.id, undefined, rangeOptions[rangeIndex].value, windowOptions[windowIndex].value)
  },

  onLocationChange(e: any) {
    const idx = Number(e.detail.value)
    const { specId, processDevices, groupIndex, locations, rangeOptions, rangeIndex, windowOptions, windowIndex } = this.data
    this.setData({ locationIndex: idx })
    this.doFetch(specId, processDevices[groupIndex]?.id, locations[idx]?.id, rangeOptions[rangeIndex].value, windowOptions[windowIndex].value)
  },

  onRangeChange(e: any) {
    const rIdx = Number(e.detail.value)
    const rangeDays = RANGE_OPTIONS[rIdx].value
    const newWindows = WINDOW_OPTIONS_MAP[rangeDays] || WINDOW_OPTIONS_MAP[1]
    const curWinVal = this.data.windowOptions[this.data.windowIndex]?.value
    const wIdx = Math.max(0, newWindows.findIndex((w: any) => w.value === curWinVal))
    this.setData({ rangeIndex: rIdx, windowOptions: newWindows, windowIndex: wIdx })
  },

  onWindowChange(e: any) {
    this.setData({ windowIndex: Number(e.detail.value) })
  },
})

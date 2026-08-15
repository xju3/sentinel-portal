import { getHealthArchiveDevices } from '../../utils/api'
import { createPagedListLoader, PagedListLoader } from '../../utils/pagination'

const app = getApp<IAppOption>()
const PAGE_SIZE = 10

interface HealthArchiveDeviceCardItem {
  id: string
  name: string
  code: string
  specName: string
  categoryName: string
  statusText: string
  statusTone: 'active' | 'history'
  currentBindingCount: number
  historicalPointCount: number
  description: string
  raw: any
}

function firstText(...values: Array<unknown>): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return ''
}

function firstNumber(...values: Array<unknown>): number {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }
  }
  return 0
}

function normalizeDevice(item: any): HealthArchiveDeviceCardItem {
  const currentBindingCount = firstNumber(
    item?.activeBindingCount,
    item?.active_binding_count,
    item?.currentBindingCount,
    item?.current_binding_count,
    item?.activeMonitoringCount,
    item?.active_monitoring_count,
    item?.currentMonitoredPointCount,
    item?.current_monitored_point_count,
  )

  const historicalPointCount = firstNumber(
    item?.historicalPointCount,
    item?.historical_point_count,
    item?.historyPointCount,
    item?.history_point_count,
    item?.monitoredPointCount,
    item?.monitored_point_count,
    item?.locationCount,
    item?.location_count,
  )

  const statusText = firstText(
    item?.monitoringStatus,
    item?.monitoring_status,
    currentBindingCount > 0 ? '监控中' : '',
    historicalPointCount > 0 ? '历史监控' : '',
  ) || '未监控'

  return {
    id: firstText(item?.id, item?.deviceId, item?.device_id, item?.device?.id),
    name: firstText(item?.name, item?.deviceName, item?.device_name, item?.device?.name) || '未命名设备',
    code: firstText(item?.code, item?.deviceCode, item?.device_code, item?.device?.code) || '--',
    specName:
      firstText(
        item?.specName,
        item?.spec_name,
        item?.deviceSpecName,
        item?.device_spec_name,
        item?.deviceSpec?.name,
        item?.device_spec?.name,
        item?.spec?.name,
      ) || '--',
    categoryName:
      firstText(
        item?.categoryName,
        item?.category_name,
        item?.deviceCategoryName,
        item?.device_category_name,
        item?.deviceCategory?.name,
        item?.device_category?.name,
        item?.category?.name,
      ) || '--',
    statusText,
    statusTone: currentBindingCount > 0 ? 'active' : 'history',
    currentBindingCount,
    historicalPointCount,
    description:
      firstText(item?.desc, item?.description, item?.device?.description, item?.remark, item?.notes) ||
      '查看设备诊断历史、健康基线与测点详情',
    raw: item,
  }
}

Page({
  deviceLoader: null as PagedListLoader<any> | null,

  data: {
    devices: [] as HealthArchiveDeviceCardItem[],
    loading: true,
    hasMore: true,
  },

  onLoad() {
    this.deviceLoader = createPagedListLoader({
      pageSize: PAGE_SIZE,
      fetchPage: (skip, limit) => {
        const token = app.globalData.session?.accessToken
        if (!token) {
          return Promise.reject(new Error('用户未登录'))
        }
        return getHealthArchiveDevices(token, skip, limit)
      },
      onChange: ({ items, loading, hasMore }) => {
        this.setData({
          devices: items.map(normalizeDevice),
          loading,
          hasMore,
        })
      },
    })

    this.fetchData()
  },

  async onPullDownRefresh() {
    try {
      await this.fetchData()
    } finally {
      wx.stopPullDownRefresh()
    }
  },

  async onReachBottom() {
    await this.fetchData(true)
  },

  async fetchData(append = false) {
    if (!this.deviceLoader || !app.globalData.session?.accessToken) {
      this.setData({ loading: false })
      return
    }

    const current = this.deviceLoader.getSnapshot()
    if (current.loading || (append && !current.hasMore)) {
      return
    }

    if (!append) {
      wx.showNavigationBarLoading()
    }

    try {
      if (append) {
        await this.deviceLoader.loadMore()
      } else {
        await this.deviceLoader.refresh()
      }
    } catch (error) {
      console.error('Fetch health archive devices failed', error)
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      if (!append) {
        wx.hideNavigationBarLoading()
      }
    }
  },

  navToDetail(e: WechatMiniprogram.CustomEvent<HealthArchiveDeviceCardItem>) {
    const item = e.detail
    if (!item?.id) {
      return
    }
    wx.navigateTo({
      url: `/pages/health-archive/detail?id=${item.id}&name=${encodeURIComponent(item.name)}`,
    })
  },
})

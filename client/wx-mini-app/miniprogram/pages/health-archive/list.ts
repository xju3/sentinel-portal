import { getHealthArchiveDeviceFilters, getHealthArchiveDevices } from '../../utils/api'
import { createPagedListLoader, PagedListLoader } from '../../utils/pagination'

const app = getApp<IAppOption>()
const PAGE_SIZE = 10
const FILTER_STORAGE_PREFIX = 'health-archive:filters:'
const FAVORITE_STORAGE_PREFIX = 'health-archive:favorites:'

interface StoredFilters {
  categoryId: string
  specId: string
  groupId: string
}

interface FilterOption { id: string; name: string }
interface SpecFilterOption extends FilterOption { deviceCategoryId: string }
interface GroupFilterOption extends FilterOption { deviceSpecIds: string[] }
type FilterKey = 'category' | 'spec' | 'group'

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
  isFavorite: boolean
  raw: any
}

function storageScope() {
  const session = app.globalData.session
  return session?.accountId || session?.tenantId || 'default'
}

function readStoredFilters(): StoredFilters {
  try {
    const value = wx.getStorageSync(`${FILTER_STORAGE_PREFIX}${storageScope()}`)
    return {
      categoryId: typeof value?.categoryId === 'string' ? value.categoryId : '',
      specId: typeof value?.specId === 'string' ? value.specId : '',
      groupId: typeof value?.groupId === 'string' ? value.groupId : '',
    }
  } catch (error) {
    console.warn('Read health archive filters failed', error)
    return { categoryId: '', specId: '', groupId: '' }
  }
}

function readFavoriteIds(): string[] {
  try {
    const value = wx.getStorageSync(`${FAVORITE_STORAGE_PREFIX}${storageScope()}`)
    return Array.isArray(value)
      ? value.filter((id): id is string => typeof id === 'string' && Boolean(id))
      : []
  } catch (error) {
    console.warn('Read health archive favorites failed', error)
    return []
  }
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

function normalizeDevice(item: any, favoriteIds: string[]): HealthArchiveDeviceCardItem {
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

  const id = firstText(item?.id, item?.deviceId, item?.device_id, item?.device?.id)
  return {
    id,
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
    isFavorite: favoriteIds.includes(id),
    raw: item,
  }
}

function normalizeAndSortDevices(items: any[], favoriteIds: string[]) {
  return items
    .map((item) => normalizeDevice(item, favoriteIds))
    .sort((left, right) => Number(right.isFavorite) - Number(left.isFavorite))
}

Page({
  deviceLoader: null as PagedListLoader<any> | null,
  filterRefreshPending: false,
  allCategories: [] as FilterOption[],
  allSpecs: [] as SpecFilterOption[],
  allGroups: [] as GroupFilterOption[],

  data: {
    devices: [] as HealthArchiveDeviceCardItem[],
    loading: true,
    hasMore: true,
    filtersLoading: true,
    filterError: '',
    categoryId: '',
    specId: '',
    groupId: '',
    categoryOptions: [{ id: '', name: '全部类别' }] as FilterOption[],
    specOptions: [{ id: '', name: '全部规格' }] as FilterOption[],
    groupOptions: [{ id: '', name: '全部分组' }] as FilterOption[],
    filtersExpanded: false,
    filterSummary: '全部设备',
    activeFilterKey: 'category' as FilterKey,
    activeFilterTitle: '设备类别',
    activeFilterValue: '',
    activeFilterOptions: [{ id: '', name: '全部类别' }] as FilterOption[],
    favoriteIds: [] as string[],
    favoriteCount: 0,
    hasActiveFilter: false,
  },

  onLoad() {
    const filters = readStoredFilters()
    const favoriteIds = readFavoriteIds()
    this.setData({
      categoryId: filters.categoryId,
      specId: filters.specId,
      groupId: filters.groupId,
      favoriteIds,
      favoriteCount: favoriteIds.length,
      hasActiveFilter: Boolean(filters.categoryId || filters.specId || filters.groupId),
    })

    this.deviceLoader = createPagedListLoader({
      pageSize: PAGE_SIZE,
      fetchPage: (skip, limit) => {
        const token = app.globalData.session?.accessToken
        if (!token) {
          return Promise.reject(new Error('用户未登录'))
        }
        return getHealthArchiveDevices(token, skip, limit, {
          deviceCategoryId: this.data.categoryId,
          deviceSpecId: this.data.specId,
          processDeviceId: this.data.groupId,
        })
      },
      onChange: ({ items, loading, hasMore }) => {
        this.setData({
          devices: normalizeAndSortDevices(items, this.data.favoriteIds),
          loading,
          hasMore,
        })
        if (!loading && this.filterRefreshPending) {
          this.filterRefreshPending = false
          setTimeout(() => this.fetchData(), 0)
        }
      },
    })

    this.loadFilterOptions(filters)
  },

  async loadFilterOptions(storedFilters: StoredFilters) {
    const token = app.globalData.session?.accessToken
    if (!token) {
      this.setData({ filtersLoading: false, loading: false })
      return
    }
    this.setData({ filtersLoading: true, filterError: '' })
    try {
      const result = await getHealthArchiveDeviceFilters(token)
      this.allCategories = Array.isArray(result?.categories) ? result.categories : []
      this.allSpecs = Array.isArray(result?.specs) ? result.specs : []
      this.allGroups = Array.isArray(result?.groups) ? result.groups : []
      this.setFilterState(storedFilters, false)
    } catch (error) {
      console.error('Fetch health archive filters failed', error)
      this.allCategories = []
      this.allSpecs = []
      this.allGroups = []
      this.setData({
        categoryId: '',
        specId: '',
        groupId: '',
        categoryOptions: [{ id: '', name: '全部类别' }],
        specOptions: [{ id: '', name: '全部规格' }],
        groupOptions: [{ id: '', name: '全部分组' }],
        hasActiveFilter: false,
        filterSummary: '筛选暂不可用',
        filterError: '筛选服务暂不可用，请更新服务后重试',
      })
      wx.showToast({ title: '筛选项加载失败', icon: 'none' })
    } finally {
      this.setData({ filtersLoading: false })
      this.fetchData()
    }
  },

  setFilterState(filters: StoredFilters, refresh = true) {
    const categoryId = this.allCategories.some((item) => item.id === filters.categoryId)
      ? filters.categoryId
      : ''
    const categorySpecs = categoryId
      ? this.allSpecs.filter((item) => item.deviceCategoryId === categoryId)
      : this.allSpecs
    const specId = categorySpecs.some((item) => item.id === filters.specId)
      ? filters.specId
      : ''
    const allowedSpecIds = new Set(categorySpecs.map((item) => item.id))
    const visibleGroups = this.allGroups.filter((item) => {
      if (specId) return item.deviceSpecIds.includes(specId)
      if (categoryId) return item.deviceSpecIds.some((id) => allowedSpecIds.has(id))
      return true
    })
    const groupId = visibleGroups.some((item) => item.id === filters.groupId)
      ? filters.groupId
      : ''
    const categoryOptions = [{ id: '', name: '全部类别' }, ...this.allCategories]
    const specOptions = [{ id: '', name: '全部规格' }, ...categorySpecs]
    const groupOptions = [{ id: '', name: '全部分组' }, ...visibleGroups]
    const selectedNames = [
      categoryOptions.find((item) => item.id === categoryId)?.name,
      specOptions.find((item) => item.id === specId)?.name,
      groupOptions.find((item) => item.id === groupId)?.name,
    ].filter((name) => name && !name.startsWith('全部'))
    this.setData({
      categoryId,
      specId,
      groupId,
      categoryOptions,
      specOptions,
      groupOptions,
      hasActiveFilter: Boolean(categoryId || specId || groupId),
      filterSummary: selectedNames.length ? selectedNames.join(' · ') : '全部设备',
    }, () => {
      this.updateActiveFilterOptions()
      this.saveFilters()
      if (refresh) this.refreshForFilters()
    })
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

  toggleFilters() {
    const filtersExpanded = !this.data.filtersExpanded
    this.setData({ filtersExpanded }, () => {
      if (filtersExpanded) this.updateActiveFilterOptions()
    })
  },

  closeFilters() {
    this.setData({ filtersExpanded: false })
  },

  keepFilterPanelOpen() {},

  changeFilterTab(e: WechatMiniprogram.TouchEvent) {
    const key = e.currentTarget.dataset.key as FilterKey
    if (!['category', 'spec', 'group'].includes(key)) return
    this.updateActiveFilterOptions(key)
  },

  updateActiveFilterOptions(key?: FilterKey) {
    const activeKey = key || (this.data.activeFilterKey as FilterKey)
    const config = {
      category: {
        title: '设备类别',
        value: this.data.categoryId,
        options: this.data.categoryOptions,
      },
      spec: {
        title: '设备规格',
        value: this.data.specId,
        options: this.data.specOptions,
      },
      group: {
        title: '设备分组',
        value: this.data.groupId,
        options: this.data.groupOptions,
      },
    }[activeKey]
    this.setData({
      activeFilterKey: activeKey,
      activeFilterTitle: config.title,
      activeFilterValue: config.value,
      activeFilterOptions: config.options,
    })
  },

  selectFilterOption(e: WechatMiniprogram.TouchEvent) {
    const id = String(e.currentTarget.dataset.id || '')
    if (this.data.activeFilterKey === 'category') {
      this.setFilterState({ categoryId: id, specId: '', groupId: '' })
      return
    }
    if (this.data.activeFilterKey === 'spec') {
      this.setFilterState({ categoryId: this.data.categoryId, specId: id, groupId: '' })
      return
    }
    this.setFilterState({
      categoryId: this.data.categoryId,
      specId: this.data.specId,
      groupId: id,
    })
  },

  retryFilterOptions() {
    this.loadFilterOptions(readStoredFilters())
  },

  resetFilters() {
    this.setFilterState({ categoryId: '', specId: '', groupId: '' })
  },

  saveFilters() {
    const filters: StoredFilters = {
      categoryId: this.data.categoryId,
      specId: this.data.specId,
      groupId: this.data.groupId,
    }
    try {
      wx.setStorageSync(`${FILTER_STORAGE_PREFIX}${storageScope()}`, filters)
    } catch (error) {
      console.warn('Save health archive filters failed', error)
    }
  },

  refreshForFilters() {
    if (this.deviceLoader?.getSnapshot().loading) {
      this.filterRefreshPending = true
      return
    }
    this.fetchData()
  },

  toggleFavorite(e: WechatMiniprogram.CustomEvent<HealthArchiveDeviceCardItem>) {
    const item = e.detail
    if (!item?.id) return
    const favorites = new Set(this.data.favoriteIds)
    if (favorites.has(item.id)) favorites.delete(item.id)
    else favorites.add(item.id)
    const favoriteIds = Array.from(favorites)
    try {
      wx.setStorageSync(`${FAVORITE_STORAGE_PREFIX}${storageScope()}`, favoriteIds)
    } catch (error) {
      console.warn('Save health archive favorites failed', error)
      wx.showToast({ title: '关注状态保存失败', icon: 'none' })
      return
    }
    const snapshotItems = this.deviceLoader?.getSnapshot().items || []
    this.setData({
      favoriteIds,
      favoriteCount: favoriteIds.length,
      devices: normalizeAndSortDevices(snapshotItems, favoriteIds),
    })
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

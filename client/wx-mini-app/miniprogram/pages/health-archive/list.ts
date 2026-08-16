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
interface CategoryFilterOption extends FilterOption { parentId: string }
interface SpecFilterOption extends FilterOption { deviceCategoryId: string }
interface GroupFilterOption extends FilterOption { deviceSpecIds: string[] }
type FilterKey = 'category' | 'spec' | 'group'

interface HealthArchiveDeviceCardItem {
  id: string
  name: string
  code: string
  specName: string
  categoryName: string
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

function normalizeDevice(item: any, favoriteIds: string[]): HealthArchiveDeviceCardItem {
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
  allCategories: [] as CategoryFilterOption[],
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
    rootCategoryTabs: [{ id: '', name: '全部' }] as FilterOption[],
    childCategoryTabs: [] as FilterOption[],
    activeRootCategoryId: '',
    activeChildCategoryId: '',
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
      this.allCategories = Array.isArray(result?.categories)
        ? result.categories.map((item) => ({
          id: item.id,
          name: item.name,
          parentId: item.parentId || '',
        }))
        : []
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
        rootCategoryTabs: [{ id: '', name: '全部' }],
        childCategoryTabs: [],
        activeRootCategoryId: '',
        activeChildCategoryId: '',
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
    const selectedCategoryIds = this.getCategoryAndDescendantIds(categoryId)
    const categorySpecs = categoryId
      ? this.allSpecs.filter((item) => selectedCategoryIds.has(item.deviceCategoryId))
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
    const categoryTabState = this.getCategoryTabState(categoryId)
    this.setData({
      categoryId,
      specId,
      groupId,
      categoryOptions,
      specOptions,
      groupOptions,
      ...categoryTabState,
      hasActiveFilter: Boolean(categoryId || specId || groupId),
      filterSummary: selectedNames.length ? selectedNames.join(' · ') : '全部设备',
    }, () => {
      this.updateActiveFilterOptions()
      this.saveFilters()
      if (refresh) this.refreshForFilters()
    })
  },

  getCategoryAndDescendantIds(categoryId: string) {
    const ids = new Set<string>()
    if (!categoryId) return ids
    ids.add(categoryId)
    let changed = true
    while (changed) {
      changed = false
      this.allCategories.forEach((item) => {
        if (item.parentId && ids.has(item.parentId) && !ids.has(item.id)) {
          ids.add(item.id)
          changed = true
        }
      })
    }
    return ids
  },

  getCategoryTabState(categoryId: string) {
    const categoryIds = new Set(this.allCategories.map((item) => item.id))
    const roots = this.allCategories.filter(
      (item) => !item.parentId || !categoryIds.has(item.parentId),
    )
    const categoryById = new Map(this.allCategories.map((item) => [item.id, item]))
    const lineage: CategoryFilterOption[] = []
    const visited = new Set<string>()
    let current = categoryById.get(categoryId)
    while (current && !visited.has(current.id)) {
      lineage.unshift(current)
      visited.add(current.id)
      current = categoryById.get(current.parentId)
    }
    const activeRootCategoryId = lineage[0]?.id || ''
    const directChildren = activeRootCategoryId
      ? this.allCategories.filter((item) => item.parentId === activeRootCategoryId)
      : []
    const activeChildCategoryId = lineage[1]?.id || ''
    return {
      rootCategoryTabs: [{ id: '', name: '全部' }, ...roots],
      childCategoryTabs: directChildren,
      activeRootCategoryId,
      activeChildCategoryId,
    }
  },

  selectRootCategory(e: WechatMiniprogram.TouchEvent) {
    const categoryId = String(e.currentTarget.dataset.id || '')
    if (categoryId === this.data.categoryId && !this.data.specId && !this.data.groupId) {
      return
    }
    this.setFilterState({ categoryId, specId: '', groupId: '' })
  },

  selectChildCategory(e: WechatMiniprogram.TouchEvent) {
    const categoryId = String(e.currentTarget.dataset.id || '')
    if (categoryId === this.data.categoryId && !this.data.specId && !this.data.groupId) {
      return
    }
    this.setFilterState({ categoryId, specId: '', groupId: '' })
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

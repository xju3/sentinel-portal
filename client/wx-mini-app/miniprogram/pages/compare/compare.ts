import { getGroupedDeviceSpecs } from '../../utils/api'
import { createPagedListLoader, PagedListLoader } from '../../utils/pagination'

const app = getApp<IAppOption>()

Page({
  specLoader: null as PagedListLoader<any> | null,

  data: {
    specs: [] as any[],
    loading: true,
    hasMore: true,
  },

  onLoad() {
    this.specLoader = createPagedListLoader({
      pageSize: 10,
      fetchPage: (skip, limit) => {
        const token = app.globalData.session?.accessToken
        if (!token) {
          return Promise.reject(new Error('用户未登录'))
        }
        return getGroupedDeviceSpecs(token, skip, limit)
      },
      onChange: ({ items, loading, hasMore }) => {
        this.setData({ specs: items, loading, hasMore })
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
    if (!this.specLoader || !app.globalData.session?.accessToken) {
      this.setData({ loading: false })
      return
    }

    const current = this.specLoader.getSnapshot()
    if (current.loading || (append && !current.hasMore)) return

    if (!append) {
      wx.showNavigationBarLoading()
    }

    try {
      if (append) {
        await this.specLoader.loadMore()
      } else {
        await this.specLoader.refresh()
      }
    } catch (err) {
      console.error('Fetch specs failed', err)
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      if (!append) {
        wx.hideNavigationBarLoading()
      }
    }
  },

  navToDetail(e: any) {
    const { id, name } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/compare/detail?id=${id}&name=${encodeURIComponent(name)}`
    })
  }
})

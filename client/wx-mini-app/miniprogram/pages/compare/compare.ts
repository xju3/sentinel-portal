import { getDeviceSpecs } from '../../utils/api'

const app = getApp<IAppOption>()

Page({
  data: {
    specs: [] as any[],
    loading: true,
    skip: 0,
    hasMore: true,
  },

  onLoad() {
    this.fetchData()
  },

  async onPullDownRefresh() {
    this.setData({ skip: 0, hasMore: true })
    await this.fetchData()
    wx.stopPullDownRefresh()
  },

  async onReachBottom() {
    if (!this.data.hasMore || this.data.loading) return
    await this.fetchData(true)
  },

  async fetchData(append = false) {
    const session = app.globalData.session
    if (!session?.accessToken) return

    this.setData({ loading: true })
    if (!append) {
      wx.showNavigationBarLoading()
    }

    try {
      const data = await getDeviceSpecs(session.accessToken, this.data.skip, 20)
      
      this.setData({
        specs: append ? [...this.data.specs, ...data] : data,
        skip: this.data.skip + data.length,
        hasMore: data.length === 20,
        loading: false
      })
    } catch (err) {
      console.error('Fetch specs failed', err)
      this.setData({ loading: false })
      wx.showToast({ title: '加载失败', icon: 'none' })
    } finally {
      wx.hideNavigationBarLoading()
    }
  },

  navToDetail(e: any) {
    const { id, name } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/compare/detail?id=${id}&name=${encodeURIComponent(name)}`
    })
  }
})

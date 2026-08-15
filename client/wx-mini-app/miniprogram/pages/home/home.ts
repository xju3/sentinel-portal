// pages/home/home.ts
const app = getApp<IAppOption>()

interface StatCard {
  label: string
  value: string | number
  unit: string
  color: string
}

Page({
  data: {
    tenantName: '',
    contactName: '',
    stats: [] as StatCard[],
    loading: true,
  },

  onLoad() {
    const session = app.globalData.session
    if (!session?.registered) {
      wx.reLaunch({ url: '/pages/index/index' })
      return
    }
    this.setData({
      tenantName: session.tenantName || '我的企业',
      contactName: session.contactName || '',
    })
    // Load overview stats (placeholder until backend overview API is ready)
    setTimeout(() => {
      this.setData({
        loading: false,
        stats: [
          { label: '设备总数', value: '--', unit: '台', color: '#1A6EF5' },
          { label: '在线设备', value: '--', unit: '台', color: '#00C897' },
          { label: '活跃告警', value: '--', unit: '条', color: '#F25C54' },
          { label: '今日诊断', value: '--', unit: '次', color: '#F5A623' },
        ],
      })
    }, 300)
  },

  onPullDownRefresh() {
    wx.stopPullDownRefresh()
  },
})

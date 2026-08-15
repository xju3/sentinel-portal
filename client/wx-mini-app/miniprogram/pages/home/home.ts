import { getDashboardHealth } from '../../utils/api'

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
    total: '--' as string | number,
    loading: true,
  },

  onLoad() {
    const session = app.globalData.session
    if (!session?.registered) {
      wx.reLaunch({ url: '/pages/index/index' })
      return
    }

    if (wx.hideHomeButton) {
      wx.hideHomeButton()
    }
    const tenantName = session.tenantName || '我的企业'
    const contactName = session.contactName || ''
    
    this.setData({
      tenantName,
      contactName,
    })

    const title = contactName ? `${contactName} @ ${tenantName}` : tenantName
    wx.setNavigationBarTitle({ title })
    // Load overview stats from backend
    this.fetchData()
  },

  async onShow() {
    // Refresh data each time the page is shown
    await this.fetchData()
  },

  async onPullDownRefresh() {
    await this.fetchData()
    wx.stopPullDownRefresh()
  },

  async fetchData() {
    const session = app.globalData.session
    if (!session?.accessToken) return

    this.setData({ loading: true })
    wx.showNavigationBarLoading()
    try {
      const data = await getDashboardHealth(session.accessToken)
      const summary = data?.healthSummary || {}
      
      const total = summary.total || 0
      
      const metrics = [
        { key: 'severe', label: '危险', value: summary.severe || 0, color: '#FF3366', icon: 'icon-fire' },
        { key: 'warning', label: '警告', value: summary.warning || 0, color: '#EC008C', icon: 'icon-warning' },
        { key: 'abnormal', label: '异常', value: summary.abnormal || 0, color: '#FA8C16', icon: 'icon-abnormal' },
        { key: 'attention', label: '关注', value: summary.attention || 0, color: '#F2C94C', icon: 'icon-attention' },
        { key: 'normal', label: '正常', value: summary.normal || 0, color: '#00C897', icon: 'icon-normal' },
        { key: 'uninspected', label: '漏检', value: summary.uninspected || 0, color: '#8C8C8C', icon: 'icon-uninspected' },
      ]

      const stats = metrics.map(m => {
        const isZero = m.value === 0
        return {
          label: m.label,
          value: m.value,
          unit: '台',
          color: isZero ? '#4B5A73' : m.color,
          icon: m.icon,
          isZero
        }
      })

      this.setData({
        stats,
        total,
        loading: false
      })
    } catch (err) {
      console.error('Fetch dashboard failed', err)
      this.setData({ loading: false })
      wx.showToast({ title: '数据加载失败', icon: 'none' })
    } finally {
      wx.hideNavigationBarLoading()
      wx.stopPullDownRefresh()
    }
  },

  navToCompare() {
    wx.navigateTo({ url: '/pages/compare/compare' })
  }
})

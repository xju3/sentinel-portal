import { getDashboardHealth } from '../../utils/api'

const app = getApp<IAppOption>()

interface StatCard {
  label: string
  value: string | number
  unit: string
  color: string
}

interface FaultDeviceCard {
  deviceId: string
  deviceName: string
  deviceCode: string
  category: string
  area: string
  level: string
  levelColor: string
  metricsText: string
}

const LEVEL_COLORS: Record<string, string> = {
  '关注': '#F2C94C',
  '异常': '#FA8C16',
  '警告': '#EC008C',
  '严重': '#FF3366',
}

function normalizeFaultDevice(item: any): FaultDeviceCard | null {
  const deviceId = typeof item?.deviceId === 'string' ? item.deviceId : ''
  if (!deviceId) return null

  const metrics = Array.isArray(item?.metrics)
    ? item.metrics.filter((metric: unknown): metric is string => typeof metric === 'string' && Boolean(metric))
    : []
  const level = typeof item?.level === 'string' && item.level ? item.level : '异常'

  return {
    deviceId,
    deviceName: item?.deviceName || '未命名设备',
    deviceCode: item?.deviceCode || '--',
    category: item?.category || '',
    area: item?.area || '',
    level,
    levelColor: LEVEL_COLORS[level] || LEVEL_COLORS['异常'],
    metricsText: metrics.join('、'),
  }
}

Page({
  data: {
    tenantName: '',
    contactName: '',
    stats: [] as StatCard[],
    faultDevices: [] as FaultDeviceCard[],
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

      const faultDevices = (Array.isArray(data?.faultDevices) ? data.faultDevices : [])
        .map(normalizeFaultDevice)
        .filter((item: FaultDeviceCard | null): item is FaultDeviceCard => item !== null)

      this.setData({
        stats,
        faultDevices,
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
  },

  navToHealthArchive() {
    wx.navigateTo({ url: '/pages/health-archive/list' })
  },

  navToDeviceHealth(e: WechatMiniprogram.BaseEvent) {
    const { id, name } = e.currentTarget.dataset
    if (!id) return
    wx.navigateTo({
      url: `/pages/health-archive/detail?id=${encodeURIComponent(id)}&name=${encodeURIComponent(name || '')}`,
    })
  }
})

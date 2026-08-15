// pages/index/index.ts — Splash & auth routing page
import { miniLogin } from '../../utils/api'

const app = getApp<IAppOption>()

Page({
  data: {
    status: 'loading' as 'loading' | 'error',
    errorMsg: '',
  },

  onLoad() {
    this.doLogin()
  },

  doLogin() {
    this.setData({ status: 'loading', errorMsg: '' })

    wx.login({
      success: async (res) => {
        if (!res.code) {
          this.setData({ status: 'error', errorMsg: '微信登录失败，请重试' })
          return
        }
        try {
          const result = await miniLogin(res.code)
          if (result.registered) {
            // Store session globally
            app.globalData.session = {
              registered: true,
              accessToken: result.access_token,
              tenantName: result.tenant_name,
              contactName: result.contact_name,
              accountId: result.account_id,
              tenantId: result.tenant_id,
            }
            wx.reLaunch({ url: '/pages/home/home' })
          } else {
            app.globalData.session = { registered: false, openid: result.openid }
            wx.reLaunch({ url: '/pages/register/register' })
          }
        } catch (e: any) {
          this.setData({ status: 'error', errorMsg: e.message || '网络异常，请重试' })
        }
      },
      fail: () => {
        this.setData({ status: 'error', errorMsg: '微信登录失败，请重试' })
      },
    })
  },

  onRetry() {
    this.doLogin()
  },
})

// pages/login/login.ts
import { miniLoginWithPassword } from '../../utils/api'

const app = getApp<IAppOption>()

Page({
  data: {
    form: {
      username: '',
      password: '',
    },
    openid: '',
    unionid: '',
    submitting: false,
    errors: {} as Record<string, string>,
  },

  onLoad() {
    const session = app.globalData.session
    if (!session || session.registered) {
      wx.reLaunch({ url: '/pages/index/index' })
      return
    }
    this.setData({ 
      openid: session.openid || '',
      unionid: session.unionid || ''
    })
  },

  onInput(e: any) {
    const field = e.currentTarget.dataset.field as string
    const value = e.detail.value as string
    this.setData({
      [`form.${field}`]: value,
      [`errors.${field}`]: '',
    })
  },

  validate(): boolean {
    const { form } = this.data
    const errors: Record<string, string> = {}

    if (!form.username.trim()) errors.username = '请输入用户名/邮箱'
    if (!form.password)        errors.password = '请输入密码'

    this.setData({ errors })
    return Object.keys(errors).length === 0
  },

  async onSubmit() {
    if (this.data.submitting) return
    if (!this.validate()) return

    this.setData({ submitting: true })
    try {
      const result = await miniLoginWithPassword({
        username: this.data.form.username,
        password: this.data.form.password,
        openid: this.data.openid,
        unionid: this.data.unionid || undefined,
      })
      
      // Update global session with success data
      app.globalData.session = {
        registered: true,
        accessToken: result.access_token,
        tenantName: result.tenant_name,
        contactName: result.contact_name,
        accountId: result.account_id,
        tenantId: result.tenant_id,
      }

      wx.showToast({ title: '登录成功', icon: 'success', duration: 1500 })
      setTimeout(() => {
        wx.reLaunch({ url: '/pages/home/home' })
      }, 1500)
    } catch (e: any) {
      wx.showToast({ title: e.message || '登录失败，请检查用户名和密码', icon: 'none', duration: 3000 })
    } finally {
      this.setData({ submitting: false })
    }
  },

  onGoToRegister() {
    wx.navigateTo({ url: '/pages/register/register' })
  }
})

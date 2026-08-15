// pages/register/register.ts
import { miniRegister } from '../../utils/api'

const app = getApp<IAppOption>()

Page({
  data: {
    form: {
      company_name: '',
      contact_name: '',
      phone: '',
      email: '',
    },
    openid: '',
    submitting: false,
    errors: {} as Record<string, string>,
  },

  onLoad() {
    const session = app.globalData.session
    if (!session || session.registered) {
      wx.reLaunch({ url: '/pages/index/index' })
      return
    }
    this.setData({ openid: session.openid || '' })
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

    if (!form.company_name.trim())   errors.company_name  = '请填写公司名称'
    if (!form.contact_name.trim())   errors.contact_name  = '请填写联系人姓名'
    if (!/^\d{7,15}$/.test(form.phone.replace(/\D/g, '')))
                                     errors.phone         = '请输入有效的手机号'
    if (!form.email.trim() || !form.email.includes('@'))
                                     errors.email         = '请输入有效的邮箱地址'

    this.setData({ errors })
    return Object.keys(errors).length === 0
  },

  async onSubmit() {
    if (this.data.submitting) return
    if (!this.validate()) return

    this.setData({ submitting: true })
    try {
      await miniRegister({ ...this.data.form, openid: this.data.openid })
      wx.showToast({ title: '注册成功', icon: 'success', duration: 1500 })
      setTimeout(() => {
        wx.reLaunch({ url: '/pages/index/index' })
      }, 1500)
    } catch (e: any) {
      wx.showToast({ title: e.message || '注册失败，请重试', icon: 'none', duration: 3000 })
    } finally {
      this.setData({ submitting: false })
    }
  },
})

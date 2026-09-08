var { syncTabBar } = require('../../utils/tabbar')

Page({
  data: {
    faqs: [
      {
        id: 'browse',
        q: '打开后可以先体验什么？',
        a: '打开即可浏览首页的服务介绍、使用指南和常见问题，无需登录。',
        open: false,
      },
      {
        id: 'login',
        q: '什么时候需要登录？',
        a: '查看个人消息，或修改头像、昵称时，可到「我的」自行选择登录。浏览首页不要求授权。',
        open: false,
      },
      {
        id: 'privacy',
        q: '登录会获取哪些信息？',
        a: '登录仅使用微信登录凭证识别账号。头像和昵称由您在「我的」自愿填写，不会在进入时强制授权。',
        open: false,
      },
      {
        id: 'member',
        q: '如何开通会员？',
        a: '在首页、「服务动态」或「我的」进入「会员」，查看各等级权益后点「申请开通」。登录提交申请，运营将在 1 个工作日内处理，结果发到消息中心。',
        open: false,
      },
      {
        id: 'service',
        q: '本小程序提供哪些服务？',
        a: '提供会员、服务动态、站内通知与账号管理。打开即可浏览介绍，登录后可申请会员并管理资料。',
        open: false,
      },
    ],
  },

  onShow() {
    syncTabBar(this)
  },

  toggleFaq(e) {
    var id = e.currentTarget.dataset.id
    var faqs = (this.data.faqs || []).map(function (item) {
      var next = Object.assign({}, item)
      next.open = item.id === id ? !item.open : false
      return next
    })
    this.setData({ faqs: faqs })
  },

  goNotify() {
    wx.switchTab({ url: '/pages/signals/signals' })
  },

  goProfile() {
    wx.switchTab({ url: '/pages/profile/profile' })
  },

  goMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' })
  },

  goHelp() {
    wx.pageScrollTo({ selector: '.faq-card', duration: 280 })
  },
})

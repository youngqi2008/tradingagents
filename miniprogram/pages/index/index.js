const { isLoggedIn, promptProfileSetupIfNeeded } = require('../../utils/auth')
const { request, login } = require('../../utils/api')
const { syncTabBar } = require('../../utils/tabbar')

Page({
  data: {
    stockCode: '',
    reports: [],
    isLoggedIn: false,
    statusText: {
      pending: '排队中',
      processing: '生成中',
      running: '生成中',
      completed: '已完成',
      failed: '失败',
      cancelled: '已取消',
    },
  },

  onShow() {
    syncTabBar(this)
    var loggedIn = isLoggedIn()
    this.setData({ isLoggedIn: loggedIn })
    if (loggedIn) {
      this.loadReports()
    } else {
      this.setData({ reports: [] })
    }
  },

  onLoginTap() {
    wx.showLoading({ title: '登录中...' })
    login({})
      .then(function (result) {
        wx.hideLoading()
        wx.showToast({ title: '登录成功', icon: 'success' })
        this.setData({ isLoggedIn: true })
        this.loadReports()
        promptProfileSetupIfNeeded(result && result.user)
      }.bind(this))
      .catch(function (e) {
        wx.hideLoading()
        wx.showToast({ title: (e && e.message) || '登录失败', icon: 'none' })
      })
  },

  onInput(e) {
    this.setData({ stockCode: e.detail.value.trim() })
  },

  goAnalysis() {
    if (!isLoggedIn()) {
      wx.showModal({
        title: '请先登录',
        content: '生成研报需要微信登录',
        confirmText: '去登录',
        success: function (r) {
          if (r.confirm) this.onLoginTap()
        }.bind(this),
      })
      return
    }
    var code = this.data.stockCode
    if (!code) {
      wx.showToast({ title: '请输入股票代码', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/analysis/analysis?code=' + code })
  },

  openReport(e) {
    var id = e.currentTarget.dataset.id
    wx.navigateTo({ url: '/pages/report/report?id=' + id })
  },

  loadReports() {
    request({ url: '/api/mp/reports/list?page_size=20' })
      .then(function (res) {
        if (res.success) {
          this.setData({ reports: res.data.reports })
        }
      }.bind(this))
      .catch(function (e) {
        console.error(e)
      })
  },
})

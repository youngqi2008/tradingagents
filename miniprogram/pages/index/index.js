const { isLoggedIn, promptProfileSetupIfNeeded } = require('../../utils/auth')
const { request, login } = require('../../utils/api')
const { syncTabBar } = require('../../utils/tabbar')

var LIST_POLL_INTERVAL = 10000
var RUNNING_STATUSES = { pending: 1, processing: 1, running: 1 }

Page({
  data: {
    stockCode: '',
    reports: [],
    isLoggedIn: false,
    hasRunning: false,
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
      this.stopListPoll()
      this.setData({ reports: [], hasRunning: false })
    }
  },

  onHide() {
    this.stopListPoll()
  },

  onUnload() {
    this.stopListPoll()
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

  onClearStockCode() {
    this.setData({ stockCode: '' })
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

  hasRunningReports(list) {
    for (var i = 0; i < list.length; i++) {
      if (RUNNING_STATUSES[list[i].status]) return true
    }
    return false
  },

  stopListPoll() {
    if (this._listPollTimer) {
      clearInterval(this._listPollTimer)
      this._listPollTimer = null
    }
  },

  startListPoll() {
    var that = this
    if (this._listPollTimer) return
    this._listPollTimer = setInterval(function () {
      that.loadReports({ silent: true })
    }, LIST_POLL_INTERVAL)
  },

  loadReports(options) {
    var silent = !!(options && options.silent)
    var prevRunningIds = {}
    if (silent) {
      var prev = this.data.reports || []
      for (var i = 0; i < prev.length; i++) {
        if (RUNNING_STATUSES[prev[i].status]) {
          prevRunningIds[String(prev[i].task_id)] = prev[i].stock_name || prev[i].stock_code || ''
        }
      }
    }

    request({ url: '/api/mp/reports/list?page_size=20' })
      .then(function (res) {
        if (!res.success) return
        var list = res.data.reports || []
        var hasRunning = this.hasRunningReports(list)
        this.setData({ reports: list, hasRunning: hasRunning })

        if (silent) {
          for (var j = 0; j < list.length; j++) {
            var id = String(list[j].task_id)
            if (prevRunningIds[id] && list[j].status === 'completed') {
              wx.showToast({
                title: (prevRunningIds[id] || '研报') + ' 已完成',
                icon: 'success',
              })
              break
            }
          }
        }

        if (hasRunning) this.startListPoll()
        else this.stopListPoll()
      }.bind(this))
      .catch(function (e) {
        console.error(e)
      })
  },
})

const {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  login,
  getNotificationUnreadCount,
} = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')
const { syncTabBar, refreshTabBadges } = require('../../utils/tabbar')
const { requestSignalSubscribe } = require('../../utils/subscribe')

var SIGNAL_TYPES = 'buy_signal,sell_signal'
var TYPE_META = {
  buy_signal: { label: '关注', cls: 'buy' },
  sell_signal: { label: '不关注', cls: 'sell' },
}

Page({
  data: {
    loading: true,
    notifications: [],
    unreadCount: 0,
    detail: null,
    needLogin: false,
  },

  onShow() {
    syncTabBar(this)
    wx.setNavigationBarTitle({ title: '关注信号' })
    if (!isLoggedIn()) {
      this.setData({
        loading: false,
        needLogin: true,
        notifications: [],
        unreadCount: 0,
        detail: null,
      })
      refreshTabBadges(this)
      return
    }
    this.setData({ needLogin: false, detail: null })
    this.loadList()
    this.tryAskSubscribe(false)
  },

  tryAskSubscribe(showTip) {
    var app = getApp()
    if (!showTip && app && app.globalData && app.globalData.signalSubscribeAsked) {
      return
    }
    requestSignalSubscribe().then(function (res) {
      if (app && app.globalData) app.globalData.signalSubscribeAsked = true
      if (!showTip) return
      if (res && res.skipped) {
        wx.showToast({ title: '请先在后台配置订阅消息模板', icon: 'none' })
        return
      }
      var result = (res && res.result) || {}
      var accepted = false
      Object.keys(result).forEach(function (id) {
        if (result[id] === 'accept') accepted = true
      })
      wx.showToast({
        title: accepted ? '已开启微信提醒' : '未开启提醒，信号将只在本页展示',
        icon: 'none',
      })
    })
  },

  onEnablePush() {
    this.tryAskSubscribe(true)
  },

  onLoginTap() {
    var self = this
    wx.showLoading({ title: '登录中...' })
    login({})
      .then(function () {
        wx.hideLoading()
        wx.showToast({ title: '登录成功', icon: 'success' })
        self.setData({ needLogin: false, detail: null })
        syncTabBar(self)
        self.loadList()
        self.tryAskSubscribe(true)
      })
      .catch(function (e) {
        wx.hideLoading()
        wx.showToast({ title: (e && e.message) || '登录失败', icon: 'none' })
      })
  },

  enrichNotification(n) {
    var meta = TYPE_META[n.notice_type] || { label: '信号', cls: '' }
    return Object.assign({}, n, {
      title: n.title || '关注信号',
      timeText: this.formatTime(n.created_at),
      preview: (n.content || '').slice(0, 80) + ((n.content || '').length > 80 ? '...' : ''),
      typeLabel: meta.label,
      typeClass: meta.cls,
    })
  },

  loadList() {
    var self = this
    self.setData({ loading: true, detail: null })
    Promise.all([
      listNotifications({ limit: 50, notice_types: SIGNAL_TYPES }),
      getNotificationUnreadCount({ notice_types: SIGNAL_TYPES }),
    ])
      .then(function (results) {
        var data = results[0] || {}
        var list = (data.notifications || []).map(function (n) {
          return self.enrichNotification(n)
        })
        var unread = results[1] || 0
        self.setData({
          loading: false,
          notifications: list,
          unreadCount: unread,
        })
        refreshTabBadges(self)
      })
      .catch(function (e) {
        self.setData({ loading: false })
        wx.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
      })
  },

  formatTime(iso) {
    if (!iso) return ''
    var d = new Date(iso)
    var pad = function (n) {
      return n < 10 ? '0' + n : '' + n
    }
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
  },

  onTapItem(e) {
    var id = e.currentTarget.dataset.id
    var item = this.data.notifications.find(function (n) {
      return String(n.id) === String(id)
    })
    if (!item) return
    var self = this
    if (!item.is_read) {
      markNotificationRead(id)
        .then(function () {
          var list = self.data.notifications.map(function (n) {
            if (String(n.id) === String(id)) {
              return Object.assign({}, n, { is_read: true })
            }
            return n
          })
          var unread = Math.max(0, (self.data.unreadCount || 0) - 1)
          self.setData({
            notifications: list,
            unreadCount: unread,
            detail: Object.assign({}, item, { is_read: true }),
          })
          refreshTabBadges(self)
        })
        .catch(function () {
          self.setData({ detail: item })
        })
      return
    }
    self.setData({ detail: item })
  },

  onCloseDetail() {
    this.setData({ detail: null })
  },

  onMarkAllRead() {
    var self = this
    markAllNotificationsRead()
      .then(function () {
        wx.showToast({ title: '已全部已读', icon: 'success' })
        self.loadList()
      })
      .catch(function () {
        wx.showToast({ title: '操作失败', icon: 'none' })
      })
  },
})

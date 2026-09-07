const {
  listNotifications,
  getNotification,
  markNotificationRead,
  markAllNotificationsRead,
  login,
  getNotificationUnreadCount,
} = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')
const { syncTabBar, refreshTabBadges } = require('../../utils/tabbar')
const {
  requestSignalSubscribe,
  askSignalSubscribeWithModal,
  savePendingSignalId,
  takePendingSignalId,
  pickQueryId,
} = require('../../utils/subscribe')

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

  onLoad(options) {
    var id = pickQueryId(options)
    if (id) savePendingSignalId(id)
  },

  onShow() {
    syncTabBar(this)
    wx.setNavigationBarTitle({ title: '关注信号' })
    var pending = this.takeOpenSignalId()
    if (!isLoggedIn()) {
      if (pending) savePendingSignalId(pending)
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
    this.setData({ needLogin: false })
    this.refreshAndOpen(pending)
  },

  takeOpenSignalId() {
    var pending = takePendingSignalId()
    var enter = {}
    try {
      enter = (wx.getEnterOptionsSync && wx.getEnterOptionsSync()) || {}
    } catch (e) {}
    var enterId = pickQueryId(enter)
    var key = String((enter.scene || '') + ':' + (pending || enterId || ''))
    if (key === ':') {
      return pending
    }
    if (this._openedEnterKey && key === this._openedEnterKey) {
      return ''
    }
    var id = pending || enterId
    if (id) this._openedEnterKey = key
    return id
  },

  refreshAndOpen(pendingId) {
    var self = this
    this.loadList()
      .then(function () {
        if (pendingId) self.openSignalById(pendingId)
      })
      .catch(function () {})
  },

  showSubscribeResult(res) {
    if (res && res.skipped) {
      if (res.reason === '未配置模板') {
        wx.showToast({ title: '请先在后台配置订阅消息模板', icon: 'none' })
      }
      return
    }
    wx.showToast({
      title: res && res.accepted ? '已开启微信提醒' : '未开启提醒，信号将只在本页展示',
      icon: 'none',
    })
  },

  onEnablePush() {
    var self = this
    requestSignalSubscribe().then(function (res) {
      self.showSubscribeResult(res)
    })
  },

  onLoginTap() {
    var self = this
    wx.showLoading({ title: '登录中...' })
    login({})
      .then(function () {
        wx.hideLoading()
        wx.showToast({ title: '登录成功', icon: 'success' })
        self.setData({ needLogin: false })
        syncTabBar(self)
        var pending = takePendingSignalId()
        self.refreshAndOpen(pending)
        return askSignalSubscribeWithModal()
      })
      .then(function (res) {
        if (res) self.showSubscribeResult(res)
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
    self.setData({ loading: true })
    return Promise.all([
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
        return list
      })
      .catch(function (e) {
        self.setData({ loading: false })
        wx.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
        return []
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

  markItemRead(id) {
    var self = this
    return markNotificationRead(id)
      .then(function () {
        var list = self.data.notifications.map(function (n) {
          if (String(n.id) === String(id)) {
            return Object.assign({}, n, { is_read: true })
          }
          return n
        })
        var unread = Math.max(0, (self.data.unreadCount || 0) - 1)
        var patch = { notifications: list, unreadCount: unread }
        if (self.data.detail && String(self.data.detail.id) === String(id)) {
          patch.detail = Object.assign({}, self.data.detail, { is_read: true })
        }
        self.setData(patch)
        refreshTabBadges(self)
      })
      .catch(function () {})
  },

  showDetail(item, replenishSubscribe) {
    if (!item) return
    var detail = this.enrichNotification(item)
    this.setData({ detail: detail })
    if (!item.is_read) this.markItemRead(item.id)
    if (replenishSubscribe) requestSignalSubscribe()
  },

  openSignalById(id) {
    if (!id) return
    var self = this
    var item = (this.data.notifications || []).find(function (n) {
      return String(n.id) === String(id)
    })
    if (item) {
      this.showDetail(item, true)
      return
    }
    getNotification(id)
      .then(function (n) {
        if (!n) {
          wx.showToast({ title: '信号不存在或已过期', icon: 'none' })
          return
        }
        self.showDetail(n, true)
      })
      .catch(function () {
        wx.showToast({ title: '信号不存在或已过期', icon: 'none' })
      })
  },

  onTapItem(e) {
    var id = e.currentTarget.dataset.id
    var item = this.data.notifications.find(function (n) {
      return String(n.id) === String(id)
    })
    if (!item) return
    this.showDetail(item, true)
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

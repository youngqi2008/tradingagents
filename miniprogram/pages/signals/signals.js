const {
  listNotifications,
  getNotification,
  markNotificationRead,
  markAllNotificationsRead,
  login,
  getNotificationUnreadCount,
} = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')
const { softenCopy } = require('../../utils/copy')
const { syncTabBar, refreshTabBadges } = require('../../utils/tabbar')
const {
  requestSignalSubscribe,
  replenishSignalSubscribe,
  askSignalSubscribeWithModal,
  refreshSubscribeStatus,
  isAlwaysAccept,
  isAlwaysReject,
  subscribeStatusText,
  describeSubscribeResult,
  savePendingSignalId,
  takePendingSignalId,
  pickQueryId,
} = require('../../utils/subscribe')

var SIGNAL_TYPES = 'buy_signal,sell_signal'
var TYPE_META = {
  buy_signal: { label: '订阅', cls: 'buy' },
  sell_signal: { label: '更新', cls: 'sell' },
}

Page({
  data: {
    loading: true,
    notifications: [],
    unreadCount: 0,
    detail: null,
    needLogin: false,
    pushAlways: false,
    pushRejected: false,
    pushStatusText: '未开启',
  },

  onLoad(options) {
    var id = pickQueryId(options)
    if (id) savePendingSignalId(id)
  },

  onShow() {
    syncTabBar(this)
    wx.setNavigationBarTitle({ title: '服务动态' })
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
    this.syncPushStatus()
    this.refreshAndOpen(pending)
  },

  syncPushStatus() {
    var self = this
    refreshSubscribeStatus().then(function (status) {
      self.setData({
        pushAlways: isAlwaysAccept(status),
        pushRejected: isAlwaysReject(status),
        pushStatusText: subscribeStatusText(status),
      })
    })
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
    this.syncPushStatus()
    var title = describeSubscribeResult(res)
    if (!title) return
    if (res && res.accepted && !res.always) return
    wx.showToast({ title: title, icon: 'none' })
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
    var meta = TYPE_META[n.notice_type] || { label: '动态', cls: '' }
    var title = softenCopy(n.title || '服务动态')
    var content = softenCopy(n.content || '')
    return Object.assign({}, n, {
      title: title,
      content: content,
      timeText: this.formatTime(n.created_at),
      preview: content.slice(0, 80) + (content.length > 80 ? '...' : ''),
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

  showDetail(item) {
    if (!item) return
    var detail = this.enrichNotification(item)
    this.setData({ detail: detail })
    if (!item.is_read) this.markItemRead(item.id)
  },

  openSignalById(id) {
    if (!id) return
    var self = this
    replenishSignalSubscribe()
    var item = (this.data.notifications || []).find(function (n) {
      return String(n.id) === String(id)
    })
    if (item) {
      this.showDetail(item)
      return
    }
    getNotification(id)
      .then(function (n) {
        if (!n) {
          wx.showToast({ title: '内容不存在或已过期', icon: 'none' })
          return
        }
        self.showDetail(n)
      })
      .catch(function () {
        wx.showToast({ title: '内容不存在或已过期', icon: 'none' })
      })
  },

  onTapItem(e) {
    replenishSignalSubscribe()
    var id = e.currentTarget.dataset.id
    var item = this.data.notifications.find(function (n) {
      return String(n.id) === String(id)
    })
    if (!item) return
    this.showDetail(item)
  },

  onCloseDetail() {
    replenishSignalSubscribe()
    this.setData({ detail: null })
  },

  goMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' })
  },

  onMarkAllRead() {
    replenishSignalSubscribe()
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

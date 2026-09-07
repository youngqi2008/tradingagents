const { listNotifications, markNotificationRead, markAllNotificationsRead, login } = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')
const { syncTabBar, refreshTabBadges } = require('../../utils/tabbar')

var CATEGORIES = [
  { key: 'all', label: '全部', types: '' },
  { key: 'broadcast', label: '广播消息', types: 'announcement' },
  { key: 'risk', label: '风控消息', types: 'risk_alert' },
  { key: 'signal', label: '关注信号', types: 'buy_signal,sell_signal' },
  { key: 'digest', label: '日报', types: 'favorites_digest' },
  { key: 'review', label: '复盘', types: 'market_review' },
]

var TYPE_META = {
  buy_signal: { label: '关注', cls: 'buy' },
  sell_signal: { label: '不关注', cls: 'sell' },
  risk_alert: { label: '风控', cls: 'risk' },
  announcement: { label: '广播', cls: 'broadcast' },
  market_review: { label: '复盘', cls: 'review' },
  favorites_digest: { label: '日报', cls: 'custom' },
}

var EMPTY_HINT = {
  all: '暂无消息',
  broadcast: '暂无广播消息',
  risk: '暂无风控消息',
  signal: '暂无关注信号',
  digest: '暂无日报',
  review: '暂无复盘消息',
}

Page({
  data: {
    loading: true,
    categories: CATEGORIES,
    activeCategory: 'all',
    notifications: [],
    unreadCount: 0,
    categoryUnread: 0,
    detail: null,
    needLogin: false,
    emptyHint: EMPTY_HINT.all,
  },

  onShow() {
    syncTabBar(this)
    if (!isLoggedIn()) {
      this.setData({
        loading: false,
        needLogin: true,
        notifications: [],
        unreadCount: 0,
        categoryUnread: 0,
        detail: null,
      })
      refreshTabBadges(this, 0)
      return
    }
    this.setData({ needLogin: false, detail: null })
    this._setNavTitle(this.data.activeCategory || 'all')
    this.loadList()
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
        self._setNavTitle(self.data.activeCategory || 'all')
        self.loadList()
        try {
          require('../../utils/subscribe').askSignalSubscribeWithModal()
        } catch (e) {}
      })
      .catch(function (e) {
        wx.hideLoading()
        wx.showToast({ title: (e && e.message) || '登录失败', icon: 'none' })
      })
  },

  onCategoryTap(e) {
    var key = e.currentTarget.dataset.key
    if (!key || key === this.data.activeCategory) return
    this.setData({ activeCategory: key, detail: null })
    this._setNavTitle(key)
    this.loadList()
  },

  _setNavTitle(key) {
    var titles = {
      all: '消息',
      broadcast: '广播消息',
      risk: '风控消息',
      signal: '关注信号',
      digest: '日报',
      review: '复盘',
    }
    wx.setNavigationBarTitle({ title: titles[key] || '消息' })
  },

  getActiveTypes() {
    var key = this.data.activeCategory
    for (var i = 0; i < CATEGORIES.length; i++) {
      if (CATEGORIES[i].key === key) return CATEGORIES[i].types
    }
    return ''
  },

  resolveTypeMeta(noticeType) {
    return TYPE_META[noticeType] || { label: '通知', cls: '' }
  },

  enrichNotification(n) {
    var meta = this.resolveTypeMeta(n.notice_type)
    return Object.assign({}, n, {
      title: n.title || '通知',
      timeText: this.formatTime(n.created_at),
      preview: (n.content || '').slice(0, 60) + ((n.content || '').length > 60 ? '...' : ''),
      typeLabel: meta.label,
      typeClass: meta.cls,
    })
  },

  loadList() {
    var self = this
    var types = self.getActiveTypes()
    var params = { limit: 50 }
    if (types) params.notice_types = types
    self.setData({
      loading: true,
      detail: null,
      emptyHint: EMPTY_HINT[self.data.activeCategory] || '暂无此类消息',
    })
    listNotifications(params)
      .then(function (data) {
        var list = (data.notifications || []).map(function (n) {
          return self.enrichNotification(n)
        })
        var unread = data.unread_count || 0
        var categoryUnread = 0
        for (var i = 0; i < list.length; i++) {
          if (!list[i].is_read) categoryUnread += 1
        }
        self.setData({
          loading: false,
          notifications: list,
          unreadCount: unread,
          categoryUnread: categoryUnread,
        })
        refreshTabBadges(self, unread)
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
        .then(function (res) {
          var unread = (res.data && res.data.unread_count) || 0
          var list = self.data.notifications.map(function (n) {
            if (String(n.id) === String(id)) {
              return Object.assign({}, n, { is_read: true })
            }
            return n
          })
          var categoryUnread = 0
          for (var i = 0; i < list.length; i++) {
            if (!list[i].is_read) categoryUnread += 1
          }
          var detail = Object.assign({}, item, { is_read: true })
          self.setData({
            notifications: list,
            unreadCount: unread,
            categoryUnread: categoryUnread,
            detail: detail,
          })
          refreshTabBadges(self, unread)
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
        refreshTabBadges(self, 0)
        self.loadList()
      })
      .catch(function () {
        wx.showToast({ title: '操作失败', icon: 'none' })
      })
  },
})

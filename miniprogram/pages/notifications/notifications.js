const { listNotifications, markNotificationRead, markAllNotificationsRead } = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')
const { syncTabBar, setTabBarUnreadCount } = require('../../utils/tabbar')

/** 消息分类：与后端 notice_type 对应 */
var CATEGORIES = [
  { key: 'all', label: '全部', types: '' },
  { key: 'signal', label: '买卖信号', types: 'buy_signal,sell_signal' },
  { key: 'risk', label: '风控消息', types: 'risk_alert' },
  { key: 'broadcast', label: '广播消息', types: 'announcement' },
  { key: 'review', label: '定时复盘', types: 'market_review' },
  { key: 'custom', label: '自选检测', types: 'favorites_digest' },
]

var TYPE_META = {
  buy_signal: { label: '买点', cls: 'buy' },
  sell_signal: { label: '卖点', cls: 'sell' },
  risk_alert: { label: '风控', cls: 'risk' },
  announcement: { label: '广播', cls: 'broadcast' },
  market_review: { label: '复盘', cls: 'review' },
  favorites_digest: { label: '自选', cls: 'custom' },
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
      setTabBarUnreadCount(this, 0)
      return
    }
    this.setData({ needLogin: false })
    this.loadList()
  },

  onLoginTap() {
    wx.switchTab({ url: '/pages/profile/profile' })
  },

  onCategoryTap(e) {
    var key = e.currentTarget.dataset.key
    if (!key || key === this.data.activeCategory) return
    this.setData({ activeCategory: key, detail: null })
    this.loadList()
  },

  getActiveTypes() {
    var key = this.data.activeCategory
    for (var i = 0; i < CATEGORIES.length; i++) {
      if (CATEGORIES[i].key === key) return CATEGORIES[i].types
    }
    return ''
  },

  resolveTypeMeta(noticeType) {
    return TYPE_META[noticeType] || { label: '', cls: '' }
  },

  loadList() {
    var self = this
    var types = self.getActiveTypes()
    var params = { limit: 50 }
    if (types) params.notice_types = types
    self.setData({ loading: true, detail: null })
    listNotifications(params)
      .then(function (data) {
        var list = (data.notifications || []).map(function (n) {
          var meta = self.resolveTypeMeta(n.notice_type)
          return Object.assign({}, n, {
            timeText: self.formatTime(n.created_at),
            preview: (n.content || '').slice(0, 60) + ((n.content || '').length > 60 ? '...' : ''),
            typeLabel: meta.label,
            typeClass: meta.cls,
          })
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
        setTabBarUnreadCount(self, unread)
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
          self.setData({ notifications: list, unreadCount: unread, categoryUnread: categoryUnread })
          setTabBarUnreadCount(self, unread)
        })
        .catch(function () {})
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
        setTabBarUnreadCount(self, 0)
        self.loadList()
      })
      .catch(function () {
        wx.showToast({ title: '操作失败', icon: 'none' })
      })
  },
})

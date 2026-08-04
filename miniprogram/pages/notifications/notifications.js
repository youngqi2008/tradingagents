const { listNotifications, markNotificationRead, markAllNotificationsRead } = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')

Page({
  data: {
    loading: true,
    notifications: [],
    unreadCount: 0,
    detail: null,
  },

  onShow() {
    if (!isLoggedIn()) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      setTimeout(function () {
        wx.navigateBack()
      }, 800)
      return
    }
    this.loadList()
  },

  loadList() {
    var self = this
    self.setData({ loading: true, detail: null })
    listNotifications()
      .then(function (data) {
        var list = (data.notifications || []).map(function (n) {
          var typeLabel = ''
          var typeClass = ''
          if (n.notice_type === 'buy_signal') {
            typeLabel = '买点'
            typeClass = 'buy'
          } else if (n.notice_type === 'sell_signal') {
            typeLabel = '卖点'
            typeClass = 'sell'
          } else if (n.notice_type === 'risk_alert') {
            typeLabel = '风控'
            typeClass = 'risk'
          }
          return Object.assign({}, n, {
            timeText: self.formatTime(n.created_at),
            preview: (n.content || '').slice(0, 60) + ((n.content || '').length > 60 ? '...' : ''),
            typeLabel: typeLabel,
            typeClass: typeClass,
          })
        })
        self.setData({
          loading: false,
          notifications: list,
          unreadCount: data.unread_count || 0,
        })
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
          self.setData({ notifications: list, unreadCount: unread })
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
        self.loadList()
      })
      .catch(function () {
        wx.showToast({ title: '操作失败', icon: 'none' })
      })
  },
})

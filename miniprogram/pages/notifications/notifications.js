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

var SIGNAL_TYPES = { buy_signal: 1, sell_signal: 1 }

function extractStockCode(n) {
  if (!n) return ''
  var content = n.content || ''
  var title = n.title || ''
  var m = content.match(/(\d{6})\.[A-Za-z]+/)
  if (m) return m[1]
  m = title.match(/[·•]\s*(\d{6})\s*$/)
  if (m) return m[1]
  m = title.match(/(\d{6})/)
  if (m) return m[1]
  m = content.match(/(\d{6})/)
  return m ? m[1] : ''
}

function buildAskMessage(code, noticeType) {
  if (noticeType === 'sell_signal') {
    return code + ' 出现卖点信号，请分析当前走势、风险，以及是否应减仓或离场'
  }
  return code + ' 出现买点信号，请分析当前走势、风险与操作建议'
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

  enrichNotification(n) {
    var meta = this.resolveTypeMeta(n.notice_type)
    var isSignal = !!SIGNAL_TYPES[n.notice_type]
    var stockCode = isSignal ? extractStockCode(n) : ''
    return Object.assign({}, n, {
      timeText: this.formatTime(n.created_at),
      preview: (n.content || '').slice(0, 60) + ((n.content || '').length > 60 ? '...' : ''),
      typeLabel: meta.label,
      typeClass: meta.cls,
      isSignal: isSignal,
      stockCode: stockCode,
      canAct: isSignal && !!stockCode,
    })
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
          var detail = Object.assign({}, item, { is_read: true })
          self.setData({
            notifications: list,
            unreadCount: unread,
            categoryUnread: categoryUnread,
            detail: detail,
          })
          setTabBarUnreadCount(self, unread)
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

  noop() {},

  resolveActionTarget(e) {
    var code = e.currentTarget.dataset.code
    var type = e.currentTarget.dataset.type
    if (code) {
      return { stockCode: code, noticeType: type || '' }
    }
    var detail = this.data.detail
    if (detail && detail.stockCode) {
      return { stockCode: detail.stockCode, noticeType: detail.notice_type || '' }
    }
    return null
  },

  goAskStock(e) {
    var target = this.resolveActionTarget(e)
    if (!target || !target.stockCode) {
      wx.showToast({ title: '未识别股票代码', icon: 'none' })
      return
    }
    try {
      wx.setStorageSync('chat_jump', {
        stock_code: target.stockCode,
        message: buildAskMessage(target.stockCode, target.noticeType),
        auto_send: false,
        from: 'signal',
      })
    } catch (err) {}
    wx.switchTab({ url: '/pages/chat/chat' })
  },

  goGenerateReport(e) {
    var target = this.resolveActionTarget(e)
    if (!target || !target.stockCode) {
      wx.showToast({ title: '未识别股票代码', icon: 'none' })
      return
    }
    wx.navigateTo({
      url: '/pages/analysis/analysis?code=' + encodeURIComponent(target.stockCode),
    })
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

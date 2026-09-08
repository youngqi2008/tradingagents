var { syncTabBar, refreshTabBadges } = require('../../utils/tabbar')
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
    loading: false,
    notifications: [],
    unreadCount: 0,
    detail: null,
    needLogin: true,
    pushAlways: false,
    pushRejected: false,
    pushStatusText: '未开启',
    samples: [
      {
        id: 'demo-sub',
        title: '服务动态示例',
        preview: '登录后可在此查看已订阅的服务更新，并可自行开启微信提醒。',
        timeText: '示例内容，可点开浏览',
        typeLabel: '订阅',
        typeClass: 'buy',
        content: '这是服务动态的示例说明。打开首页即可浏览用途与帮助，不要求授权手机号、头像或昵称。需要查看个人动态时，可自行选择登录。',
      },
      {
        id: 'demo-upd',
        title: '服务更新示例',
        preview: '已订阅内容如有更新，会显示在首页服务动态中。',
        timeText: '示例内容，可点开浏览',
        typeLabel: '更新',
        typeClass: 'sell',
        content: '这是服务更新的示例。您可以先体验浏览，再决定是否登录查看属于自己的动态。',
      },
    ],
    faqs: [
      {
        id: 'browse',
        q: '打开后可以先体验什么？',
        a: '打开即可浏览首页的服务动态说明、示例和常见问题，无需登录。',
        open: false,
      },
      {
        id: 'login',
        q: '什么时候需要登录？',
        a: '查看个人服务动态或消息时，可到本页或「我的」自行选择登录。浏览首页不要求授权。',
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
        a: '在首页或「我的」进入「会员」，查看各等级权益后点「申请开通」。登录提交申请，运营将在 1 个工作日内处理。',
        open: false,
      },
    ],
  },

  onLoad(options) {
    var id = pickQueryId(options)
    if (id) savePendingSignalId(id)
  },

  onShow() {
    syncTabBar(this)
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

  takeOpenSignalId() {
    var pending = takePendingSignalId()
    var enter = {}
    try {
      enter = (wx.getEnterOptionsSync && wx.getEnterOptionsSync()) || {}
    } catch (e) {}
    var enterId = pickQueryId(enter)
    var key = String((enter.scene || '') + ':' + (pending || enterId || ''))
    if (key === ':') return pending
    if (this._openedEnterKey && key === this._openedEnterKey) return ''
    var id = pending || enterId
    if (id) this._openedEnterKey = key
    return id
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

  refreshAndOpen(pendingId) {
    var self = this
    this.loadList()
      .then(function () {
        if (pendingId) self.openSignalById(pendingId)
      })
      .catch(function () {})
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
        self.setData({ needLogin: false, detail: null })
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

  onTapSample(e) {
    var id = e.currentTarget.dataset.id
    var item = (this.data.samples || []).find(function (n) {
      return String(n.id) === String(id)
    })
    if (item) this.setData({ detail: item })
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

  toggleFaq(e) {
    var id = e.currentTarget.dataset.id
    var faqs = (this.data.faqs || []).map(function (item) {
      var next = Object.assign({}, item)
      next.open = item.id === id ? !item.open : false
      return next
    })
    this.setData({ faqs: faqs })
  },

  goMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' })
  },
})

var api = require('../../utils/api')
var auth = require('../../utils/auth')
var { syncTabBar } = require('../../utils/tabbar')

function fmtTime(v) {
  if (!v) return ''
  var s = String(v).replace('T', ' ')
  return s.slice(0, 16)
}

Page({
  data: {
    isLoggedIn: false,
    loading: false,
    onlyFav: false,
    list: [],
    displayList: [],
    detail: null,
  },

  onShow() {
    syncTabBar(this)
    var loggedIn = auth.isLoggedIn()
    this.setData({ isLoggedIn: loggedIn })
    if (loggedIn) this.loadNews()
  },

  goLogin() {
    wx.switchTab({ url: '/pages/profile/profile' })
  },

  toggleOnlyFav() {
    if (this.data.detail) return
    var onlyFav = !this.data.onlyFav
    this.setData({ onlyFav: onlyFav })
    this.applyFilter()
  },

  applyFilter() {
    var list = this.data.list || []
    if (this.data.onlyFav) {
      list = list.filter(function (x) { return x.highlight })
    }
    this.setData({ displayList: list })
  },

  onRefresh() {
    if (this.data.detail) {
      this.setData({ detail: null })
    }
    this.loadNews()
  },

  loadNews() {
    var self = this
    this.setData({ loading: true, detail: null })
    api.listLatestNews({ hours: 72, limit: 50 })
      .then(function (data) {
        var items = (data && data.items) || []
        items = items.map(function (it) {
          var content = it.content || it.summary || ''
          var summary = it.summary || ''
          if (!summary && content) {
            summary = content.length > 120 ? content.slice(0, 120) + '…' : content
          }
          return Object.assign({}, it, {
            timeText: fmtTime(it.publish_time),
            favorite_symbolsText: (it.favorite_symbols || []).join('、'),
            summary: summary,
            content: content,
            hasMore: !!(content && summary && content.length > summary.replace(/…$/, '').length),
          })
        })
        self.setData({ list: items, loading: false })
        self.applyFilter()
      })
      .catch(function (e) {
        self.setData({ loading: false })
        if (e && e.message === '未登录') {
          self.setData({ isLoggedIn: false })
          return
        }
        wx.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
      })
  },

  onOpen(e) {
    var id = e.currentTarget.dataset.id
    var item = (this.data.displayList || []).find(function (x) {
      return String(x.id) === String(id)
    })
    if (!item) return
    this.setData({ detail: item })
  },

  onCloseDetail() {
    this.setData({ detail: null })
  },

  onCopyLink() {
    var detail = this.data.detail
    var url = detail && detail.url
    if (!url || (url.indexOf('http://') !== 0 && url.indexOf('https://') !== 0)) {
      wx.showToast({ title: '暂无原文链接', icon: 'none' })
      return
    }
    wx.setClipboardData({
      data: url,
      success: function () {
        wx.showToast({ title: '原文链接已复制', icon: 'none' })
      },
    })
  },

  onOpenLink() {
    var detail = this.data.detail
    var url = detail && detail.url
    if (!url || (url.indexOf('http://') !== 0 && url.indexOf('https://') !== 0)) {
      wx.showToast({ title: '暂无原文链接', icon: 'none' })
      return
    }
    // 优先尝试系统打开；失败则复制
    if (wx.openOfficialAccountArticle && url.indexOf('mp.weixin.qq.com') >= 0) {
      wx.openOfficialAccountArticle({ url: url })
      return
    }
    wx.setClipboardData({
      data: url,
      success: function () {
        wx.showModal({
          title: '打开原文',
          content: '小程序内无法直接打开外链，链接已复制，请粘贴到浏览器查看。',
          showCancel: false,
          confirmText: '知道了',
        })
      },
    })
  },

  onGoKline() {
    var detail = this.data.detail
    var symbol = detail && detail.symbol
    if (!symbol) {
      wx.showToast({ title: '无关联股票', icon: 'none' })
      return
    }
    try {
      wx.setStorageSync('kline_jump', {
        code: symbol,
        name: (detail && detail.stock_name) || '',
      })
    } catch (err) {}
    wx.switchTab({ url: '/pages/kline/kline' })
  },
})

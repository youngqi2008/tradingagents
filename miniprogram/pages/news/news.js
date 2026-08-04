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
    this.loadNews()
  },

  loadNews() {
    var self = this
    this.setData({ loading: true })
    api.listLatestNews({ hours: 72, limit: 50 })
      .then(function (data) {
        var items = (data && data.items) || []
        items = items.map(function (it) {
          return Object.assign({}, it, {
            timeText: fmtTime(it.publish_time),
            favorite_symbolsText: (it.favorite_symbols || []).join('、'),
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
    var url = e.currentTarget.dataset.url
    var symbol = e.currentTarget.dataset.symbol
    var name = e.currentTarget.dataset.name || ''
    if (url && (url.indexOf('http://') === 0 || url.indexOf('https://') === 0)) {
      wx.setClipboardData({
        data: url,
        success: function () {
          wx.showToast({ title: '链接已复制', icon: 'none' })
        },
      })
      return
    }
    if (symbol) {
      try {
        wx.setStorageSync('kline_jump', { code: symbol, name: name })
      } catch (err) {}
      wx.switchTab({ url: '/pages/kline/kline' })
    }
  },
})

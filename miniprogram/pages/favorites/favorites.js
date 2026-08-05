var api = require('../../utils/api')
var auth = require('../../utils/auth')

Page({
  data: {
    isLoggedIn: false,
    keyword: '',
    suggests: [],
    favorites: [],
    loading: false,
  },

  onShow() {
    var loggedIn = auth.isLoggedIn()
    this.setData({ isLoggedIn: loggedIn })
    if (loggedIn) this.loadFavorites()
  },

  goLogin() {
    wx.switchTab({ url: '/pages/profile/profile' })
  },

  onInput(e) {
    this.setData({ keyword: e.detail.value || '' })
  },

  onClearKeyword() {
    this.setData({ keyword: '', suggests: [] })
  },

  onSearch() {
    var kw = (this.data.keyword || '').trim()
    if (!kw) {
      this.setData({ suggests: [] })
      return
    }
    var self = this
    api.searchStocks(kw)
      .then(function (res) {
        var items = (res && res.data && res.data.items) || (res && res.items) || []
        // 自选订阅排除指数
        items = items.filter(function (it) { return !it.is_index })
        if (!items.length && /^\d{6}$/.test(kw)) {
          items = [{ code: kw, name: kw }]
        }
        self.setData({ suggests: items.slice(0, 8) })
      })
      .catch(function () {
        if (/^\d{6}$/.test(kw)) {
          self.setData({ suggests: [{ code: kw, name: kw }] })
        } else {
          wx.showToast({ title: '搜索失败', icon: 'none' })
        }
      })
  },

  loadFavorites() {
    var self = this
    this.setData({ loading: true })
    api.listFavorites()
      .then(function (list) {
        self.setData({ favorites: list || [], loading: false })
      })
      .catch(function (e) {
        self.setData({ loading: false })
        wx.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
      })
  },

  onAdd(e) {
    var code = e.currentTarget.dataset.code
    var name = e.currentTarget.dataset.name || code
    var self = this
    wx.showLoading({ title: '订阅中' })
    api.addFavorite({ stock_code: code, stock_name: name })
      .then(function () {
        wx.hideLoading()
        wx.showToast({ title: '已订阅', icon: 'success' })
        self.setData({ suggests: [], keyword: '' })
        self.loadFavorites()
      })
      .catch(function (err) {
        wx.hideLoading()
        wx.showToast({ title: (err && err.message) || '订阅失败', icon: 'none' })
      })
  },

  onRemove(e) {
    var code = e.currentTarget.dataset.code
    var self = this
    wx.showModal({
      title: '取消订阅',
      content: '确定取消自选 ' + code + '？',
      success: function (r) {
        if (!r.confirm) return
        api.removeFavorite(code)
          .then(function () {
            wx.showToast({ title: '已取消', icon: 'none' })
            self.loadFavorites()
          })
          .catch(function (err) {
            wx.showToast({ title: (err && err.message) || '操作失败', icon: 'none' })
          })
      },
    })
  },

  goKline(e) {
    var code = e.currentTarget.dataset.code
    var name = e.currentTarget.dataset.name || ''
    try {
      wx.setStorageSync('kline_jump', { code: code, name: name })
    } catch (err) {}
    wx.switchTab({ url: '/pages/kline/kline' })
  },
})

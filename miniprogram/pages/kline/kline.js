var api = require('../../utils/api')
var auth = require('../../utils/auth')
var { syncTabBar, setTabBarUnreadCount } = require('../../utils/tabbar')

// 默认展示沪指；输入个股代码后切换
var DEFAULT_CODE = 'sh000001'
var DEFAULT_NAME = '上证指数'
var PERIODS = [
  { label: '日K', value: 'day' },
  { label: '周K', value: 'week' },
  { label: '月K', value: 'month' },
]

function fmtNum(v, digits) {
  var n = Number(v)
  if (!Number.isFinite(n)) return '-'
  return n.toFixed(digits == null ? 2 : digits)
}

function fmtAmount(v) {
  var n = Number(v)
  if (!Number.isFinite(n)) return '-'
  if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}

function periodLabel(period) {
  for (var i = 0; i < PERIODS.length; i++) {
    if (PERIODS[i].value === period) return PERIODS[i].label
  }
  return period
}

Page({
  data: {
    isLoggedIn: false,
    keyword: '',
    stockCode: DEFAULT_CODE,
    stockName: DEFAULT_NAME,
    suggests: [],
    periods: PERIODS,
    period: 'day',
    periodLabel: '日K',
    quote: null,
    quoteUp: false,
    quoteDown: false,
    priceText: '-',
    chgText: '-',
    openText: '-',
    highText: '-',
    lowText: '-',
    amountText: '-',
    loading: false,
    errorMsg: '',
    hasData: false,
    barCount: 0,
    lastTime: '',
    canvasWidth: 320,
    canvasHeight: 240,
  },

  _bars: [],
  _searchTimer: null,
  _canvasNode: null,
  _canvasCtx: null,

  onShow() {
    syncTabBar(this)
    var loggedIn = auth.isLoggedIn()
    this.setData({ isLoggedIn: loggedIn })
    if (!loggedIn) {
      setTabBarUnreadCount(this, 0)
      return
    }
    this.refreshUnreadBadge()
    try {
      var jump = wx.getStorageSync('kline_jump')
      if (jump && jump.code) {
        wx.removeStorageSync('kline_jump')
        this.measureCanvas(function () {
          this.loadStock(jump.code, jump.name)
        }.bind(this))
        return
      }
    } catch (e) {}
    this.measureCanvas(function () {
      this.loadStock(this.data.stockCode)
    }.bind(this))
  },

  refreshUnreadBadge() {
    var self = this
    api.getNotificationUnreadCount()
      .then(function (count) {
        setTabBarUnreadCount(self, count)
      })
      .catch(function () {})
  },

  onHide() {
    if (this._searchTimer) {
      clearTimeout(this._searchTimer)
      this._searchTimer = null
    }
  },

  onLoginTap() {
    var self = this
    wx.showLoading({ title: '登录中...' })
    api.login({})
      .then(function (result) {
        wx.hideLoading()
        wx.showToast({ title: '登录成功', icon: 'success' })
        self.setData({ isLoggedIn: true })
        self.measureCanvas(function () {
          self.loadStock(self.data.stockCode)
        })
        auth.promptProfileSetupIfNeeded(result && result.user)
      })
      .catch(function (e) {
        wx.hideLoading()
        wx.showToast({ title: (e && e.message) || '登录失败', icon: 'none' })
      })
  },

  onKeywordInput(e) {
    var keyword = (e.detail.value || '').trim()
    this.setData({ keyword: keyword, suggests: [] })
    if (this._searchTimer) clearTimeout(this._searchTimer)
    if (!keyword || keyword.length < 1) return
    var self = this
    this._searchTimer = setTimeout(function () {
      api.searchStocks(keyword, 8)
        .then(function (res) {
          var items = (res && res.data && res.data.items) || []
          self.setData({ suggests: items })
        })
        .catch(function () {
          self.setData({ suggests: [] })
        })
    }, 280)
  },

  onSearchConfirm() {
    var code = (this.data.keyword || '').trim()
    // 空查询 → 回到默认沪指
    if (!code) {
      this.loadStock(DEFAULT_CODE, DEFAULT_NAME)
      return
    }
    // 沪指别名
    if (code === '沪指' || code === '上证' || code === '上证指数' || /^sh000001$/i.test(code)) {
      this.loadStock(DEFAULT_CODE, DEFAULT_NAME)
      return
    }
    // 纯数字不足 6 位时补齐；名称搜索走建议列表
    if (/^\d+$/.test(code) && code.length <= 6) {
      code = ('000000' + code).slice(-6)
      this.loadStock(code)
      return
    }
    if (this.data.suggests.length) {
      var first = this.data.suggests[0]
      this.loadStock(first.code, first.name)
      return
    }
    this.loadStock(code)
  },

  onSelectSuggest(e) {
    var code = e.currentTarget.dataset.code
    var name = e.currentTarget.dataset.name
    this.loadStock(code, name)
  },

  onPeriodChange(e) {
    var period = e.currentTarget.dataset.period
    if (!period || period === this.data.period) return
    this.setData({ period: period, periodLabel: periodLabel(period) })
    this.fetchKline(this.data.stockCode, period)
  },

  loadStock(code, name) {
    var displayKeyword = code === DEFAULT_CODE ? '' : code
    this.setData({
      stockCode: code,
      stockName: name || (code === DEFAULT_CODE ? DEFAULT_NAME : ''),
      keyword: displayKeyword,
      suggests: [],
    })
    this.fetchQuote(code)
    this.fetchKline(code, this.data.period)
  },

  fetchQuote(code) {
    var self = this
    api.getStockQuote(code)
      .then(function (res) {
        var q = (res && res.data) || null
        if (!q) {
          self.setData({ quote: null })
          return
        }
        var price = Number(q.price != null ? q.price : q.close)
        var pct = Number(q.change_percent != null ? q.change_percent : q.pct_chg)
        var up = Number.isFinite(pct) && pct > 0
        var down = Number.isFinite(pct) && pct < 0
        var chgText = Number.isFinite(pct)
          ? ((pct > 0 ? '+' : '') + pct.toFixed(2) + '%')
          : '-'
        self.setData({
          quote: q,
          stockName: q.name || self.data.stockName,
          quoteUp: up,
          quoteDown: down,
          priceText: fmtNum(price),
          chgText: chgText,
          openText: fmtNum(q.open),
          highText: fmtNum(q.high),
          lowText: fmtNum(q.low),
          amountText: fmtAmount(q.amount),
        })
      })
      .catch(function () {
        self.setData({ quote: null })
      })
  },

  fetchKline(code, period) {
    var self = this
    this.setData({ loading: true, errorMsg: '', hasData: false })
    api.getStockKline(code, period, 120, 'none')
      .then(function (res) {
        var items = (res && res.data && res.data.items) || []
        var bars = []
        for (var i = 0; i < items.length; i++) {
          var it = items[i]
          var o = Number(it.open)
          var h = Number(it.high)
          var l = Number(it.low)
          var c = Number(it.close)
          var t = String(it.time || it.trade_date || it.trade_time || '')
          if (!t || !Number.isFinite(o) || !Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c)) {
            continue
          }
          bars.push({ time: t, open: o, high: h, low: l, close: c })
        }
        self._bars = bars
        var last = bars.length ? bars[bars.length - 1] : null
        self.setData({
          loading: false,
          hasData: bars.length > 0,
          barCount: bars.length,
          lastTime: last ? last.time : '',
          errorMsg: bars.length ? '' : '暂无 K 线数据',
        })
        self.drawKline(bars)
      })
      .catch(function (e) {
        self._bars = []
        self.setData({
          loading: false,
          hasData: false,
          barCount: 0,
          lastTime: '',
          errorMsg: (e && e.message) || '加载失败',
        })
        self.drawKline([])
      })
  },

  measureCanvas(done) {
    var self = this
    if (!this.data.isLoggedIn) {
      if (done) done()
      return
    }
    var tryMeasure = function (attempt) {
      var query = wx.createSelectorQuery()
      query.select('#klineCanvas').fields({ node: true, size: true }).exec(function (res) {
        var info = res && res[0]
        if (!info || !info.node) {
          if (attempt < 8) {
            setTimeout(function () { tryMeasure(attempt + 1) }, 50)
            return
          }
          if (done) done()
          return
        }
        var sys = wx.getSystemInfoSync()
        var width = info.width || Math.max(280, (sys.windowWidth || 375) - 48)
        var height = Math.max(220, Math.round(width * 0.72))
        var dpr = sys.pixelRatio || 2
        var canvas = info.node
        canvas.width = width * dpr
        canvas.height = height * dpr
        var ctx = canvas.getContext('2d')
        ctx.setTransform(1, 0, 0, 1, 0, 0)
        ctx.scale(dpr, dpr)
        self._canvasNode = canvas
        self._canvasCtx = ctx
        self.setData({ canvasWidth: width, canvasHeight: height }, function () {
          if (done) done()
        })
      })
    }
    tryMeasure(0)
  },

  drawKline(bars) {
    var self = this
    if (!this._canvasCtx) {
      this.measureCanvas(function () {
        self.drawKline(bars)
      })
      return
    }
    var ctx = this._canvasCtx
    var w = this.data.canvasWidth
    var h = this.data.canvasHeight
    ctx.clearRect(0, 0, w, h)

    if (!bars || !bars.length) return

    var padL = 8
    var padR = 8
    var padT = 16
    var padB = 28
    var chartW = w - padL - padR
    var chartH = h - padT - padB

    var minP = bars[0].low
    var maxP = bars[0].high
    for (var i = 1; i < bars.length; i++) {
      if (bars[i].low < minP) minP = bars[i].low
      if (bars[i].high > maxP) maxP = bars[i].high
    }
    var span = maxP - minP || 1
    minP -= span * 0.05
    maxP += span * 0.05
    span = maxP - minP

    function yOf(price) {
      return padT + ((maxP - price) / span) * chartH
    }

    // 背景网格
    ctx.strokeStyle = '#eef1f7'
    ctx.lineWidth = 1
    for (var g = 0; g <= 4; g++) {
      var gy = padT + (chartH * g) / 4
      ctx.beginPath()
      ctx.moveTo(padL, gy)
      ctx.lineTo(padL + chartW, gy)
      ctx.stroke()
    }

    // 价格刻度
    ctx.fillStyle = '#9ca3af'
    ctx.font = '10px sans-serif'
    ctx.textAlign = 'left'
    for (var t = 0; t <= 4; t++) {
      var price = maxP - (span * t) / 4
      ctx.fillText(price.toFixed(2), padL + 2, padT + (chartH * t) / 4 - 2)
    }

    var n = bars.length
    var slot = chartW / n
    var bodyW = Math.max(1.5, Math.min(10, slot * 0.62))

    for (var j = 0; j < n; j++) {
      var bar = bars[j]
      var x = padL + slot * j + slot / 2
      var yO = yOf(bar.open)
      var yC = yOf(bar.close)
      var yH = yOf(bar.high)
      var yL = yOf(bar.low)
      var up = bar.close >= bar.open
      var color = up ? '#ef4444' : '#16a34a'
      ctx.strokeStyle = color
      ctx.fillStyle = color
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x, yH)
      ctx.lineTo(x, yL)
      ctx.stroke()
      var top = Math.min(yO, yC)
      var bodyH = Math.max(1, Math.abs(yC - yO))
      ctx.fillRect(x - bodyW / 2, top, bodyW, bodyH)
    }

    // 首尾日期
    ctx.fillStyle = '#9ca3af'
    ctx.font = '10px sans-serif'
    ctx.textAlign = 'left'
    ctx.fillText(String(bars[0].time).slice(0, 10), padL, h - 8)
    ctx.textAlign = 'right'
    ctx.fillText(String(bars[n - 1].time).slice(0, 10), padL + chartW, h - 8)
  },
})

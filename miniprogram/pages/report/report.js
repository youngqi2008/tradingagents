const { request, BASE_URL } = require('../../utils/api')
const { getToken } = require('../../utils/auth')

var POLL_INTERVAL = 5000
var RUNNING_STATUSES = { pending: 1, processing: 1, running: 1 }

Page({
  data: {
    report: null,
    reportId: '',
    isGenerating: false,
    pollHint: '深度研报通常需要 5–10 分钟，请耐心等待，本页会自动刷新。',
  },

  onLoad(options) {
    this.setData({ reportId: options.id })
    this.loadReport()
  },

  onShow() {
    if (this.data.isGenerating) this.startPoll()
  },

  onHide() {
    this.stopPoll()
  },

  onUnload() {
    this.stopPoll()
  },

  stopPoll() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer)
      this._pollTimer = null
    }
  },

  startPoll() {
    var that = this
    if (this._pollTimer) return
    this._pollTimer = setInterval(function () {
      that.loadReport({ silent: true })
    }, POLL_INTERVAL)
  },

  async loadReport(options) {
    var silent = !!(options && options.silent)
    try {
      const res = await request({ url: `/api/mp/reports/${this.data.reportId}` })
      if (!res.success) return
      var report = res.data
      var status = report && report.status
      var isGenerating = !!(status && RUNNING_STATUSES[status])
      var wasGenerating = this.data.isGenerating
      this.setData({ report: report, isGenerating: isGenerating })

      if (isGenerating) {
        this.startPoll()
      } else {
        this.stopPoll()
        if (wasGenerating && status === 'completed' && !silent) {
          wx.showToast({ title: '研报已生成', icon: 'success' })
        } else if (wasGenerating && status === 'completed' && silent) {
          wx.showToast({ title: '研报已生成', icon: 'success' })
        }
      }
    } catch (e) {
      if (!silent) wx.showToast({ title: '加载失败', icon: 'none' })
    }
  },

  onRefreshTap() {
    this.loadReport()
  },

  download(e) {
    const format = e.currentTarget.dataset.format
    const url = `${BASE_URL}/api/mp/reports/${this.data.reportId}/download?format=${format}`
    wx.showLoading({ title: '下载中' })
    wx.downloadFile({
      url,
      header: { Authorization: `Bearer ${getToken()}` },
      success(res) {
        wx.hideLoading()
        if (res.statusCode === 200) {
          wx.openDocument({ filePath: res.tempFilePath, showMenu: true })
        } else {
          wx.showToast({ title: '下载失败', icon: 'none' })
        }
      },
      fail() {
        wx.hideLoading()
        wx.showToast({ title: '下载失败', icon: 'none' })
      },
    })
  },
})

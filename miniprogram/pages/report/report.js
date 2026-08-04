const { request, BASE_URL } = require('../../utils/api')
const { getToken } = require('../../utils/auth')

Page({
  data: { report: null, reportId: '' },

  onLoad(options) {
    this.setData({ reportId: options.id })
    this.loadReport()
  },

  async loadReport() {
    try {
      const res = await request({ url: `/api/mp/reports/${this.data.reportId}` })
      if (res.success) this.setData({ report: res.data })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'none' })
    }
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

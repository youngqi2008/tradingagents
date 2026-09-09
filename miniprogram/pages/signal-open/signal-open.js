const { pickQueryId, savePendingSignalId } = require('../../utils/subscribe')

Page({
  onLoad(options) {
    var id = pickQueryId(options)
    if (id) savePendingSignalId(id)
    wx.switchTab({
      url: '/pages/index/index',
    })
  },
})

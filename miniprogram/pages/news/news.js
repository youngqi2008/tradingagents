Page({
  onShow() {
    try {
      wx.setStorageSync('market_pane', 'news')
    } catch (e) {}
    wx.switchTab({ url: '/pages/kline/kline' })
  },
})

Page({
  onShow() {
    try {
      wx.setStorageSync('research_pane', 'report')
    } catch (e) {}
    wx.switchTab({ url: '/pages/chat/chat' })
  },
})

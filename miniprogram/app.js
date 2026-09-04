const { checkServer, restoreSession } = require('./utils/api')
const { isLoggedIn, getUserInfo } = require('./utils/auth')
const { refreshTabBadges } = require('./utils/tabbar')

App({
  globalData: {
    isLoggedIn: false,
    userInfo: null,
    signalSubscribeAsked: false,
  },

  onLaunch: function () {
    var that = this
    that.globalData.isLoggedIn = isLoggedIn()
    that.globalData.userInfo = getUserInfo()

    restoreSession()
      .then(function (ok) {
        that.globalData.isLoggedIn = !!ok || isLoggedIn()
        that.globalData.userInfo = getUserInfo()
      })
      .catch(function () {})

    checkServer().catch(function (e) {
      console.error('健康检查失败', e)
      var msg = (e && e.message) || '网络异常'
      if (msg.indexOf('超时') >= 0 || msg.indexOf('无法连接') >= 0) {
        wx.showModal({
          title: '无法连接服务器',
          content: msg,
          showCancel: false,
        })
      }
    })
  },

  onShow: function () {
    var pages = getCurrentPages() || []
    var page = pages.length ? pages[pages.length - 1] : null
    if (page) refreshTabBadges(page)
  },
})

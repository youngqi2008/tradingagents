const { checkServer, getMe } = require('./utils/api')
const { isLoggedIn, getUserInfo, getUser, setAuth, getToken } = require('./utils/auth')

App({
  globalData: {
    isLoggedIn: false,
    userInfo: null,
  },

  onLaunch: function () {
    var that = this
    that.globalData.isLoggedIn = isLoggedIn()
    that.globalData.userInfo = getUserInfo()

    // 启动时刷新角色，保证默认用户不出现风控 Tab、专员能及时出现
    if (isLoggedIn()) {
      getMe()
        .then(function (u) {
          if (!u) return
          var cached = getUser() || {}
          var next = Object.assign({}, cached, {
            role: u.role || 'normal',
            role_name: u.role_name || '普通',
            id: u.id || cached.id,
            nickname: u.nickname || cached.nickname,
          })
          setAuth(getToken(), next)
        })
        .catch(function () {})
    }

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
})

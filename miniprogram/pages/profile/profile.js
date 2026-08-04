const { request, login, getMe, updateMe, uploadAvatar, applyAvatarDisplay, getNotificationUnreadCount } = require('../../utils/api')
const {
  isLoggedIn,
  getUserInfo,
  setUserInfo,
  getUser,
  setAuth,
  getToken,
  logout,
  isRiskOfficer,
  needsProfileSetup,
  isProfileSetupPending,
  setProfileSetupPending,
  isDefaultNickname,
} = require('../../utils/auth')
const { syncTabBar, setTabBarUnreadCount } = require('../../utils/tabbar')

Page({
  data: {
    profile: null,
    records: [],
    unreadCount: 0,
    isLoggedIn: false,
    isRiskOfficer: false,
    userInfo: { nickName: '', avatarUrl: '' },
    showProfileSetup: false,
    setupNickName: '',
    setupAvatarUrl: '',
  },

  onShow() {
    syncTabBar(this)
    this.checkLoginStatus()
  },

  checkLoginStatus() {
    var loggedIn = isLoggedIn()
    var userInfo = getUserInfo() || { nickName: '', avatarUrl: '' }
    this.setData({
      isLoggedIn: loggedIn,
      userInfo: userInfo,
      isRiskOfficer: isRiskOfficer(),
    })
    if (!loggedIn) {
      this.setData({
        profile: null,
        records: [],
        unreadCount: 0,
        showProfileSetup: false,
        setupNickName: '',
        setupAvatarUrl: '',
      })
      setTabBarUnreadCount(this, 0)
      syncTabBar(this)
      return
    }
    this.loadProfile()
    this.loadRecords()
    this.loadUnreadCount()
    getMe()
      .then(function (u) {
        if (!u) return
        var cached = getUser() || {}
        if (u.role) {
          cached.role = u.role
          cached.role_name = u.role_name
          setAuth(getToken(), Object.assign({}, cached, u))
        }
        this.setData({ isRiskOfficer: cached.role === 'risk_officer' || u.role === 'risk_officer' })
        syncTabBar(this)
        return applyAvatarDisplay(u.nickname, u.avatar_url).then(function (fresh) {
          setUserInfo(fresh)
          this.setData({ userInfo: fresh })
          this.maybeOpenProfileSetup(u, fresh)
        }.bind(this))
      }.bind(this))
      .catch(function () {
        this.maybeOpenProfileSetup(getUser(), getUserInfo())
      }.bind(this))
  },

  maybeOpenProfileSetup(user, userInfo) {
    if (!isLoggedIn()) return
    if (this._profileSetupDismissed) return
    if (!isProfileSetupPending() && !needsProfileSetup(user, userInfo)) return
    this.openProfileSetup(userInfo || getUserInfo())
  },

  openProfileSetup(userInfo) {
    var info = userInfo || getUserInfo() || { nickName: '', avatarUrl: '' }
    var nick = (info.nickName || '').trim()
    this.setData({
      showProfileSetup: true,
      setupNickName: isDefaultNickname(nick) ? '' : nick,
      setupAvatarUrl: info.avatarUrl || '',
    })
  },

  onLoginTap() {
    wx.showLoading({ title: '登录中...' })
    login({})
      .then(function (result) {
        wx.hideLoading()
        wx.showToast({ title: '登录成功', icon: 'success' })
        this._profileSetupDismissed = false
        this.checkLoginStatus()
        var user = (result && result.user) || getUser()
        if (needsProfileSetup(user)) {
          this.openProfileSetup(getUserInfo())
        }
      }.bind(this))
      .catch(function (e) {
        wx.hideLoading()
        wx.showToast({ title: (e && e.message) || '登录失败', icon: 'none' })
      })
  },

  onChooseAvatar(e) {
    var avatarUrl = e.detail.avatarUrl
    if (!avatarUrl) return
    if (this.data.showProfileSetup) {
      this.setData({ setupAvatarUrl: avatarUrl })
      return
    }
    var userInfo = Object.assign({}, this.data.userInfo, { avatarUrl: avatarUrl })
    this.setData({ userInfo: userInfo })
    setUserInfo(userInfo)
    wx.showLoading({ title: '上传头像...' })
    uploadAvatar(avatarUrl)
      .then(function () {
        wx.hideLoading()
        wx.showToast({ title: '头像已更新', icon: 'success' })
      })
      .catch(function (err) {
        wx.hideLoading()
        wx.showToast({ title: (err && err.message) || '上传失败', icon: 'none' })
      })
  },

  onSetupChooseAvatar(e) {
    this.onChooseAvatar(e)
  },

  onNicknameInput(e) {
    this.setData({ 'userInfo.nickName': e.detail.value })
  },

  onSetupNicknameInput(e) {
    this.setData({ setupNickName: e.detail.value })
  },

  onNicknameBlur(e) {
    var nickName = (e.detail.value || '').trim()
    if (!nickName || !isLoggedIn()) return
    if (isDefaultNickname(nickName)) {
      wx.showToast({ title: '请使用真实昵称', icon: 'none' })
      return
    }
    var userInfo = Object.assign({}, this.data.userInfo, { nickName: nickName })
    setUserInfo(userInfo)
    this.setData({ userInfo: userInfo })
    updateMe({ nickname: nickName })
      .then(function () {
        setProfileSetupPending(false)
        wx.showToast({ title: '昵称已保存', icon: 'success' })
      })
      .catch(function () {
        wx.showToast({ title: '昵称同步失败', icon: 'none' })
      })
  },

  preventMove() {},

  onSetupNicknameBlur(e) {
    var nickName = (e.detail.value || '').trim()
    this.setData({ setupNickName: nickName })
  },

  onProfileSetupSkip() {
    this._profileSetupDismissed = true
    setProfileSetupPending(false)
    this.setData({ showProfileSetup: false })
  },

  onProfileSetupConfirm() {
    var nickName = (this.data.setupNickName || '').trim()
    var avatarUrl = this.data.setupAvatarUrl || ''
    if (!nickName) {
      wx.showToast({ title: '请填写昵称', icon: 'none' })
      return
    }
    if (isDefaultNickname(nickName)) {
      wx.showToast({ title: '请使用真实昵称', icon: 'none' })
      return
    }

    var self = this
    wx.showLoading({ title: '保存中...' })

    var chain = Promise.resolve()
    if (avatarUrl && isLocalTempAvatar(avatarUrl)) {
      chain = uploadAvatar(avatarUrl).catch(function (err) {
        throw new Error((err && err.message) || '头像上传失败')
      })
    }

    chain
      .then(function () {
        return updateMe({ nickname: nickName })
      })
      .then(function () {
        return getMe()
      })
      .then(function (u) {
        return applyAvatarDisplay(
          (u && u.nickname) || nickName,
          (u && u.avatar_url) || ''
        ).then(function (fresh) {
          if (!fresh.avatarUrl && avatarUrl) {
            fresh.avatarUrl = avatarUrl
          }
          if (!fresh.nickName) {
            fresh.nickName = nickName
          }
          setUserInfo(fresh)
          setProfileSetupPending(false)
          self._profileSetupDismissed = true
          wx.hideLoading()
          self.setData({
            showProfileSetup: false,
            userInfo: fresh,
            setupNickName: '',
            setupAvatarUrl: '',
          })
          wx.showToast({ title: '资料已完善', icon: 'success' })
          self.loadProfile()
        })
      })
      .catch(function (err) {
        wx.hideLoading()
        wx.showToast({ title: (err && err.message) || '保存失败', icon: 'none' })
      })
  },

  onLogoutTap() {
    wx.showModal({
      title: '退出登录',
      content: '确定退出当前账号？',
      success: function (r) {
        if (r.confirm) {
          logout()
          this._profileSetupDismissed = false
          this.setData({
            isLoggedIn: false,
            isRiskOfficer: false,
            profile: null,
            records: [],
            userInfo: { nickName: '', avatarUrl: '' },
            showProfileSetup: false,
            setupNickName: '',
            setupAvatarUrl: '',
          })
          syncTabBar(this)
          wx.showToast({ title: '已退出', icon: 'none' })
        }
      }.bind(this),
    })
  },

  loadProfile() {
    request({ url: '/api/mp/user/profile' })
      .then(function (res) {
        if (!res.success) return
        this.setData({ profile: res.data })
        var cached = getUser() || {}
        if (res.data && res.data.role) {
          cached.role = res.data.role
          cached.role_name = res.data.role_name
          setAuth(getToken(), cached)
          this.setData({ isRiskOfficer: res.data.role === 'risk_officer' })
          syncTabBar(this)
        }
      }.bind(this))
      .catch(function (e) {
        console.error('[profile]', e && e.statusCode, e && e.message, e && e.data)
      })
  },

  loadRecords() {
    request({ url: '/api/mp/user/billing-records?limit=10' })
      .then(function (res) {
        if (res.success) this.setData({ records: res.data.records })
      }.bind(this))
      .catch(function (e) {
        console.error('[billing-records]', e && e.statusCode, e && e.message)
      })
  },

  loadUnreadCount() {
    getNotificationUnreadCount()
      .then(function (count) {
        this.setData({ unreadCount: count })
        setTabBarUnreadCount(this, count)
      }.bind(this))
      .catch(function () {})
  },

  goRecharge() {
    if (!isLoggedIn()) {
      this.onLoginTap()
      return
    }
    wx.navigateTo({ url: '/pages/recharge/recharge' })
  },

  goFavorites() {
    if (!isLoggedIn()) {
      this.onLoginTap()
      return
    }
    wx.navigateTo({ url: '/pages/favorites/favorites' })
  },

  goMembership() {
    if (!isLoggedIn()) {
      this.onLoginTap()
      return
    }
    wx.navigateTo({ url: '/pages/membership/membership' })
  },

  goNotifications() {
    wx.switchTab({ url: '/pages/notifications/notifications' })
  },

  goRiskMessage() {
    if (!isLoggedIn()) {
      this.onLoginTap()
      return
    }
    if (!isRiskOfficer()) {
      wx.showToast({ title: '仅风控专员可进入', icon: 'none' })
      return
    }
    wx.switchTab({ url: '/pages/risk-message/risk-message' })
  },
})

function isLocalTempAvatar(path) {
  if (!path) return false
  return (
    path.indexOf('wxfile://') === 0 ||
    path.indexOf('http://tmp') === 0 ||
    path.indexOf('https://tmp') === 0 ||
    path.indexOf('tmp/') >= 0 ||
    path.indexOf('/tmp') >= 0
  )
}

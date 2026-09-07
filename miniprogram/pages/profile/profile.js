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
  isDefaultNickname,
} = require('../../utils/auth')
const { syncTabBar, refreshTabBadges } = require('../../utils/tabbar')

Page({
  data: {
    profile: null,
    records: [],
    unreadCount: 0,
    isLoggedIn: false,
    isRiskOfficer: false,
    userInfo: { nickName: '', avatarUrl: '' },
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
      })
      refreshTabBadges(this)
      syncTabBar(this)
      return
    }
    this.loadProfile()
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
        }.bind(this))
      }.bind(this))
      .catch(function () {})
  },

  onLoginTap() {
    wx.showLoading({ title: '登录中...' })
    login({})
      .then(function () {
        wx.hideLoading()
        wx.showToast({ title: '登录成功', icon: 'success' })
        this.checkLoginStatus()
        try {
          require('../../utils/subscribe').askSignalSubscribeWithModal()
        } catch (e) {}
      }.bind(this))
      .catch(function (e) {
        wx.hideLoading()
        wx.showToast({ title: (e && e.message) || '登录失败', icon: 'none' })
      })
  },

  onChooseAvatar(e) {
    var avatarUrl = e.detail.avatarUrl
    if (!avatarUrl) return
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

  onNicknameInput(e) {
    this.setData({ 'userInfo.nickName': e.detail.value })
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
        wx.showToast({ title: '昵称已保存', icon: 'success' })
      })
      .catch(function () {
        wx.showToast({ title: '昵称同步失败', icon: 'none' })
      })
  },

  onLogoutTap() {
    wx.showModal({
      title: '退出登录',
      content: '确定退出当前账号？',
      success: function (r) {
        if (r.confirm) {
          logout()
          this.setData({
            isLoggedIn: false,
            isRiskOfficer: false,
            profile: null,
            records: [],
            userInfo: { nickName: '', avatarUrl: '' },
            unreadCount: 0,
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
        refreshTabBadges(this)
      }.bind(this))
      .catch(function () {})
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

  goSignals() {
    wx.switchTab({ url: '/pages/signals/signals' })
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

var PROFILE_SETUP_FLAG = 'mp_need_profile_setup'

function getToken() {
  return wx.getStorageSync('access_token') || ''
}

function setAuth(token, user) {
  wx.setStorageSync('access_token', token)
  wx.setStorageSync('user', user)
}

function getUser() {
  return wx.getStorageSync('user') || null
}

function setUserInfo(userInfo) {
  wx.setStorageSync('userInfo', userInfo || {})
}

function getUserInfo() {
  return wx.getStorageSync('userInfo') || null
}

function clearAuth() {
  wx.removeStorageSync('access_token')
  wx.removeStorageSync('user')
  wx.removeStorageSync('userInfo')
  wx.removeStorageSync(PROFILE_SETUP_FLAG)
}

function isLoggedIn() {
  return !!getToken()
}

function isRiskOfficer() {
  // 仅精确匹配风控专员；缺省/普通角色一律 false
  var user = getUser()
  if (!user || !isLoggedIn()) return false
  return String(user.role || '') === 'risk_officer'
}

/** 系统默认昵称（微信用户xxxx）或空，视为未完善 */
function isDefaultNickname(name) {
  var n = String(name || '').trim()
  if (!n) return true
  return /^微信用户/.test(n)
}

/**
 * 是否需要完善资料（合规：头像选择器 + 昵称输入）
 * 优先看本地 userInfo，再看服务端 user.nickname
 */
function needsProfileSetup(user, userInfo) {
  var info = userInfo || getUserInfo() || {}
  var u = user || getUser() || {}
  var nick = (info.nickName || u.nickname || '').trim()
  return isDefaultNickname(nick)
}

function setProfileSetupPending(pending) {
  if (pending) {
    wx.setStorageSync(PROFILE_SETUP_FLAG, '1')
  } else {
    wx.removeStorageSync(PROFILE_SETUP_FLAG)
  }
}

function isProfileSetupPending() {
  return wx.getStorageSync(PROFILE_SETUP_FLAG) === '1'
}

/** 登录后若资料未完善：打标并跳转「我的」完善页 */
function promptProfileSetupIfNeeded(user) {
  if (!needsProfileSetup(user)) {
    setProfileSetupPending(false)
    return false
  }
  setProfileSetupPending(true)
  try {
    var pages = getCurrentPages() || []
    var cur = pages.length ? pages[pages.length - 1] : null
    var route = (cur && (cur.route || cur.__route__)) || ''
    if (route.indexOf('pages/profile/profile') >= 0) {
      return true
    }
  } catch (e) {}
  wx.switchTab({ url: '/pages/profile/profile' })
  return true
}

function ensureLogin() {
  var api = require('./api')
  if (isLoggedIn()) {
    return Promise.resolve(getUser())
  }
  return api.login({}).then(function (result) {
    var user = (result && result.user) || getUser()
    promptProfileSetupIfNeeded(user)
    return user
  })
}

function logout() {
  clearAuth()
}

module.exports = {
  getToken,
  setAuth,
  getUser,
  setUserInfo,
  getUserInfo,
  clearAuth,
  isLoggedIn,
  isRiskOfficer,
  isDefaultNickname,
  needsProfileSetup,
  setProfileSetupPending,
  isProfileSetupPending,
  promptProfileSetupIfNeeded,
  ensureLogin,
  logout,
}

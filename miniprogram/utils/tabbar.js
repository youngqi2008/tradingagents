const { isRiskOfficer, isLoggedIn } = require('./auth')

var SIGNAL_TYPES = 'buy_signal,sell_signal'

/** 关注信号为首页 Tab，打开小程序第一眼可见 */
var BASE_TABS = [
  { pagePath: '/pages/signals/signals', text: '关注信号', icon: 'signal' },
  { pagePath: '/pages/notifications/notifications', text: '消息', icon: 'notify' },
  { pagePath: '/pages/profile/profile', text: '我的', icon: 'me' },
]

var RISK_TAB = {
  pagePath: '/pages/risk-message/risk-message',
  text: '风控',
  icon: 'risk',
}

function buildTabList(isRisk) {
  if (!isRisk) {
    return BASE_TABS.map(function (t) {
      return Object.assign({}, t)
    })
  }
  var meIndex = BASE_TABS.length - 1
  return BASE_TABS.slice(0, meIndex)
    .concat([Object.assign({}, RISK_TAB)])
    .concat(BASE_TABS.slice(meIndex))
    .map(function (t) {
      return Object.assign({}, t)
    })
}

function syncTabBar(page) {
  if (!page || typeof page.getTabBar !== 'function') return
  var tabBar = page.getTabBar()
  if (!tabBar) return
  var showRisk = isRiskOfficer()
  if (typeof tabBar.updateForRole === 'function') {
    tabBar.updateForRole(showRisk)
  }
  var route = '/' + (page.route || '')
  if (!showRisk && route.indexOf('risk-message') >= 0) {
    route = '/pages/profile/profile'
  }
  if (typeof tabBar.setSelectedByPath === 'function') {
    tabBar.setSelectedByPath(route)
  }
}

function setTabBarUnreadCount(page, count) {
  if (!page || typeof page.getTabBar !== 'function') return
  var tabBar = page.getTabBar()
  if (!tabBar || typeof tabBar.setUnreadCount !== 'function') return
  tabBar.setUnreadCount(count)
}

function setTabBarSignalCount(page, count) {
  if (!page || typeof page.getTabBar !== 'function') return
  var tabBar = page.getTabBar()
  if (!tabBar || typeof tabBar.setSignalUnreadCount !== 'function') return
  tabBar.setSignalUnreadCount(count)
}

function refreshTabBadges(page) {
  if (!isLoggedIn()) {
    setTabBarUnreadCount(page, 0)
    setTabBarSignalCount(page, 0)
    return
  }
  var api = require('./api')
  api.getNotificationUnreadCount()
    .then(function (count) {
      setTabBarUnreadCount(page, count)
    })
    .catch(function () {})
  api.getNotificationUnreadCount({ notice_types: SIGNAL_TYPES })
    .then(function (count) {
      setTabBarSignalCount(page, count)
    })
    .catch(function () {})
}

module.exports = {
  buildTabList,
  syncTabBar,
  setTabBarUnreadCount,
  setTabBarSignalCount,
  refreshTabBadges,
  RISK_TAB,
  BASE_TABS,
  SIGNAL_TYPES,
}

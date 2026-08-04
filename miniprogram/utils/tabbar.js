const { isRiskOfficer } = require('./auth')

/** 全体用户可见的基础 Tab（不含风控） */
var BASE_TABS = [
  { pagePath: '/pages/kline/kline', text: '行情', icon: 'kline' },
  { pagePath: '/pages/news/news', text: '新闻', icon: 'news' },
  { pagePath: '/pages/chat/chat', text: '问股', icon: 'chat' },
  { pagePath: '/pages/index/index', text: '研报', icon: 'report' },
  { pagePath: '/pages/notifications/notifications', text: '消息', icon: 'notify' },
  { pagePath: '/pages/profile/profile', text: '我的', icon: 'me' },
]

var RISK_TAB = {
  pagePath: '/pages/risk-message/risk-message',
  text: '风控',
  icon: 'risk',
}

/**
 * 默认用户：6 个 Tab（含消息）
 * 风控专员：在「我的」前插入「风控」
 */
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
  // 普通用户若误入风控页，不选中风控项
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

module.exports = {
  buildTabList,
  syncTabBar,
  setTabBarUnreadCount,
  RISK_TAB,
  BASE_TABS,
}

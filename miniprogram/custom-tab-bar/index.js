const { buildTabList } = require('../utils/tabbar')
const { isRiskOfficer } = require('../utils/auth')

Component({
  data: {
    selected: 0,
    list: buildTabList(false),
    showRisk: false,
    unreadCount: 0,
  },
  lifetimes: {
    attached() {
      this.refreshByRole()
    },
  },
  pageLifetimes: {
    show() {
      this.refreshByRole()
    },
  },
  methods: {
    refreshByRole() {
      this.updateForRole(isRiskOfficer())
    },
    updateForRole(isRisk) {
      var showRisk = !!isRisk && isRiskOfficer()
      var list = buildTabList(showRisk)
      this.setData({
        showRisk: showRisk,
        list: list,
      })
    },
    setUnreadCount(count) {
      var n = Number(count) || 0
      if (n < 0) n = 0
      this.setData({ unreadCount: n })
    },
    setSelectedByPath(path) {
      var list = this.data.list || []
      var idx = -1
      for (var i = 0; i < list.length; i++) {
        if (list[i].pagePath === path) {
          idx = i
          break
        }
      }
      if (idx >= 0) {
        this.setData({ selected: idx })
      }
    },
    switchTab(e) {
      var path = e.currentTarget.dataset.path
      var index = e.currentTarget.dataset.index
      if (path.indexOf('risk-message') >= 0 && !isRiskOfficer()) {
        wx.showToast({ title: '仅风控专员可用', icon: 'none' })
        this.updateForRole(false)
        return
      }
      wx.switchTab({ url: path })
      this.setData({ selected: index })
    },
  },
})

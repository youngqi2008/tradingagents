const { listMembershipLevels } = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')

Page({
  data: {
    loading: true,
    currentId: '',
    levels: [],
    profile: null,
  },

  onShow() {
    if (!isLoggedIn()) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      setTimeout(function () {
        wx.navigateBack()
      }, 800)
      return
    }
    this.loadData()
  },

  loadData() {
    var self = this
    self.setData({ loading: true })
    Promise.all([
      listMembershipLevels(),
      require('../../utils/api').request({ url: '/api/mp/user/profile' }),
    ])
      .then(function (results) {
        var levelRes = results[0]
        var profileRes = results[1]
        var currentId = levelRes.current_membership_level_id || ''
        var rawLevels = levelRes.levels || []
        var levels = rawLevels.map(function (lv) {
          return self.decorateLevel(lv, currentId)
        })
        self.setData({
          loading: false,
          currentId: currentId,
          levels: levels,
          profile: profileRes.success ? profileRes.data : null,
        })
      })
      .catch(function (e) {
        self.setData({ loading: false })
        wx.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
      })
  },

  decorateLevel(level, currentId) {
    var isCurrent = String(level.id) === String(currentId)
    var monthlyReport = level.benefit_monthly_report || 0
    var monthlyAsk = level.benefit_monthly_ask || 0
    var monthlyPush = level.benefit_monthly_push || 0
    var onceReport = level.benefit_once_report || 0
    var onceAsk = level.benefit_once_ask || 0
    var oncePush = level.benefit_once_push || 0
    return Object.assign({}, level, {
      isCurrent: isCurrent,
      benefit_monthly_report_text: level.benefit_monthly_report_text || String(monthlyReport),
      hasMonthlyBenefit: monthlyReport > 0 || monthlyAsk > 0 || monthlyPush > 0,
      hasOnceBenefit: onceReport > 0 || onceAsk > 0 || oncePush > 0,
    })
  },
})

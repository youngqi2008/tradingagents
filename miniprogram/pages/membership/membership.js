const { listMembershipLevels, applyMembership, login } = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')

Page({
  data: {
    loading: true,
    loggedIn: false,
    currentId: '',
    levels: [],
    profile: null,
    selectedId: '',
    applying: false,
  },

  onShow() {
    this.setData({ loggedIn: isLoggedIn() })
    this.loadData()
  },

  loadData() {
    var self = this
    var loggedIn = isLoggedIn()
    self.setData({ loading: true, loggedIn: loggedIn })
    var tasks = [listMembershipLevels()]
    if (loggedIn) {
      tasks.push(require('../../utils/api').request({ url: '/api/mp/user/profile' }))
    }
    Promise.all(tasks)
      .then(function (results) {
        var levelRes = results[0] || {}
        var profileRes = results[1]
        var currentId = levelRes.current_membership_level_id || ''
        var rawLevels = levelRes.levels || []
        var levels = rawLevels.map(function (lv) {
          return self.decorateLevel(lv, currentId)
        })
        var profile = null
        if (profileRes && profileRes.success) profile = profileRes.data
        else if (profileRes && profileRes.data) profile = profileRes.data
        var selectedId = self.data.selectedId
        if (!selectedId && levels.length) {
          var firstOther = levels.find(function (lv) { return !lv.isCurrent })
          selectedId = (firstOther && firstOther.id) || levels[0].id
        }
        self.setData({
          loading: false,
          currentId: currentId,
          levels: levels,
          profile: profile,
          selectedId: selectedId,
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

  onSelectLevel(e) {
    var id = e.currentTarget.dataset.id
    if (!id) return
    this.setData({ selectedId: id })
  },

  onCurrentTap() {
    wx.showToast({ title: '您已是该会员', icon: 'none' })
  },

  onLoginTap() {
    var self = this
    wx.showLoading({ title: '登录中...' })
    login({})
      .then(function () {
        wx.hideLoading()
        wx.showToast({ title: '登录成功', icon: 'success' })
        self.setData({ loggedIn: true })
        self.loadData()
        var pending = self._pendingApplyId
        self._pendingApplyId = ''
        if (pending) {
          setTimeout(function () {
            self.submitApply(pending)
          }, 400)
        }
      })
      .catch(function (e) {
        wx.hideLoading()
        wx.showToast({ title: (e && e.message) || '登录失败', icon: 'none' })
      })
  },

  onApplyTap(e) {
    var id = e.currentTarget.dataset.id
    if (!id) return
    this.setData({ selectedId: id })
    if (!isLoggedIn()) {
      this._pendingApplyId = id
      wx.showModal({
        title: '申请开通会员',
        content: '登录后即可提交开通申请，运营将在 1 个工作日内处理。',
        confirmText: '去登录',
        success: function (r) {
          if (r.confirm) this.onLoginTap()
        }.bind(this),
      })
      return
    }
    this.confirmApply(id)
  },

  confirmApply(id) {
    var self = this
    var level = (this.data.levels || []).find(function (lv) {
      return String(lv.id) === String(id)
    })
    var name = (level && level.name) || '该等级'
    wx.showModal({
      title: '申请开通',
      content: '确认申请开通「' + name + '」？提交后运营将在 1 个工作日内处理，结果会发到消息中心。',
      confirmText: '提交申请',
      success: function (r) {
        if (r.confirm) self.submitApply(id)
      },
    })
  },

  submitApply(id) {
    var self = this
    if (this.data.applying) return
    this.setData({ applying: true })
    wx.showLoading({ title: '提交中...' })
    applyMembership(id)
      .then(function (res) {
        wx.hideLoading()
        self.setData({ applying: false })
        var msg = (res && res.message) || '申请已提交'
        wx.showModal({
          title: '申请已提交',
          content: msg + '。可到「消息」查看申请回执。',
          confirmText: '查看消息',
          cancelText: '继续浏览',
          success: function (r) {
            if (r.confirm) {
              wx.switchTab({ url: '/pages/notifications/notifications' })
            }
          },
        })
      })
      .catch(function (e) {
        wx.hideLoading()
        self.setData({ applying: false })
        wx.showToast({ title: (e && e.message) || '提交失败', icon: 'none' })
      })
  },
})

const { listMembershipLevels, changeMembership } = require('../../utils/api')
const { isLoggedIn } = require('../../utils/auth')

Page({
  data: {
    loading: true,
    changing: false,
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
        var currentLevel = rawLevels.find(function (l) {
          return String(l.id) === String(currentId)
        })
        var currentSort = currentLevel ? currentLevel.sort_order : -1
        var levels = rawLevels.map(function (lv) {
          return self.decorateLevel(lv, currentId, currentSort)
        })
        self.setData({
          loading: false,
          currentId: levelRes.current_membership_level_id || '',
          levels: levels,
          profile: profileRes.success ? profileRes.data : null,
        })
      })
      .catch(function (e) {
        self.setData({ loading: false })
        wx.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
      })
  },

  decorateLevel(level, currentId, currentSort) {
    var isCurrent = String(level.id) === String(currentId)
    var action = 'switch'
    var actionText = '选择'
    if (isCurrent) {
      action = 'current'
      actionText = '当前等级'
    } else if (level.sort_order > currentSort) {
      action = 'upgrade'
      actionText = '升级'
    } else if (level.sort_order < currentSort) {
      action = 'downgrade'
      actionText = '降级'
    }
    return Object.assign({}, level, {
      isCurrent: isCurrent,
      action: action,
      actionText: actionText,
      monthly_price_text: Number(level.monthly_price || 0).toFixed(2),
      per_generation_price_text: Number(level.per_generation_price || 0).toFixed(2),
      per_ask_price_text: Number(level.per_ask_price || 0).toFixed(2),
    })
  },

  onSelectLevel(e) {
    var levelId = e.currentTarget.dataset.id
    var level = this.data.levels.find(function (l) {
      return String(l.id) === String(levelId)
    })
    if (!level || level.isCurrent) return
    var fee = Number(level.monthly_price || 0)
    var feePaid = this.data.profile && this.data.profile.membership_fee_paid
    var lines = [
      '月费：¥' + level.monthly_price_text + (fee > 0 && !feePaid ? '（变更时将扣除）' : ''),
      '免费研报：' + level.monthly_free_generations + ' 次/月',
      '研报超限：¥' + level.per_generation_price_text + '/次',
      '免费问股：' + (level.monthly_free_asks || 0) + ' 次/月',
      '问股超限：¥' + level.per_ask_price_text + '/次',
    ]
    if (level.description) lines.push(level.description)
    var self = this
    wx.showModal({
      title: '确认' + level.actionText + '为「' + level.name + '」',
      content: lines.join('\n'),
      confirmText: level.actionText,
      success: function (r) {
        if (r.confirm) self.doChange(level)
      },
    })
  },

  doChange(level) {
    var self = this
    if (self.data.changing) return
    self.setData({ changing: true })
    wx.showLoading({ title: '处理中...' })
    changeMembership(level.id)
      .then(function (res) {
        wx.hideLoading()
        wx.showToast({
          title: (res && res.message) || '变更成功',
          icon: 'success',
        })
        self.loadData()
      })
      .catch(function (e) {
        wx.hideLoading()
        if (e && e.statusCode === 402) {
          var detail = e.detail || {}
          var content = (e.message || '余额不足') + '\n当前余额 ¥' + (detail.balance || 0) + '，需要 ¥' + (detail.required || 0)
          wx.showModal({
            title: '余额不足',
            content: content,
            confirmText: '去充值',
            cancelText: '知道了',
            success: function (r) {
              if (r.confirm) wx.navigateTo({ url: '/pages/recharge/recharge' })
            },
          })
          return
        }
        wx.showToast({ title: (e && e.message) || '变更失败', icon: 'none' })
      })
      .finally(function () {
        self.setData({ changing: false })
      })
  },

  goRecharge() {
    wx.navigateTo({ url: '/pages/recharge/recharge' })
  },
})

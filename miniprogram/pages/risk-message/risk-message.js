const {
  listMembershipLevels,
  createRiskMessage,
  listRiskMessages,
} = require('../../utils/api')
const { isLoggedIn, isRiskOfficer } = require('../../utils/auth')
const { syncTabBar } = require('../../utils/tabbar')

Page({
  data: {
    checking: true,
    allowed: false,
    title: '',
    content: '',
    targetType: 'all',
    levels: [],
    selectedLevelIds: [],
    selectedLevelNamesText: '',
    sending: false,
    history: [],
    historyLoading: false,
  },

  onShow() {
    syncTabBar(this)
    if (!isLoggedIn()) {
      this.setData({ checking: false, allowed: false })
      wx.showToast({ title: '请先登录', icon: 'none' })
      setTimeout(function () {
        wx.switchTab({ url: '/pages/profile/profile' })
      }, 500)
      return
    }
    var allowed = isRiskOfficer()
    this.setData({ checking: false, allowed: allowed })
    if (!allowed) {
      wx.showToast({ title: '仅风控专员可进入', icon: 'none' })
      setTimeout(function () {
        wx.switchTab({ url: '/pages/profile/profile' })
      }, 400)
      return
    }
    this.loadLevels()
    this.loadHistory()
  },

  loadLevels() {
    var self = this
    var selected = {}
    ;(this.data.selectedLevelIds || []).forEach(function (id) {
      selected[String(id)] = true
    })
    listMembershipLevels()
      .then(function (data) {
        var levels = ((data && data.levels) || []).map(function (l) {
          var id = String(l.id)
          return Object.assign({}, l, {
            id: id,
            selected: !!selected[id],
          })
        })
        self.setData({
          levels: levels,
          selectedLevelNamesText: self._selectedNamesText(levels),
        })
      })
      .catch(function () {})
  },

  _selectedNamesText(levels) {
    var names = (levels || [])
      .filter(function (l) {
        return l.selected
      })
      .map(function (l) {
        return l.name
      })
    if (!names.length) return '请选择一个或多个会员等级'
    return '已选：' + names.join('、')
  },

  loadHistory() {
    var self = this
    self.setData({ historyLoading: true })
    listRiskMessages()
      .then(function (data) {
        var list = ((data && data.notifications) || []).map(function (n) {
          var targetText = '全部用户'
          if (n.target_type === 'membership') {
            targetText = '会员等级'
          }
          return Object.assign({}, n, {
            timeText: self.formatTime(n.created_at),
            targetText: targetText,
            preview: (n.content || '').slice(0, 80) + ((n.content || '').length > 80 ? '...' : ''),
          })
        })
        self.setData({ history: list, historyLoading: false })
      })
      .catch(function () {
        self.setData({ historyLoading: false })
      })
  },

  formatTime(iso) {
    if (!iso) return ''
    var d = new Date(iso)
    var pad = function (n) {
      return n < 10 ? '0' + n : '' + n
    }
    return (
      pad(d.getMonth() + 1) +
      '-' +
      pad(d.getDate()) +
      ' ' +
      pad(d.getHours()) +
      ':' +
      pad(d.getMinutes())
    )
  },

  onTitle(e) {
    this.setData({ title: e.detail.value })
  },

  onContent(e) {
    this.setData({ content: e.detail.value })
  },

  onTargetType(e) {
    this.setData({ targetType: e.currentTarget.dataset.type })
  },

  onToggleLevel(e) {
    var id = String(e.currentTarget.dataset.id || '')
    if (!id) return
    var levels = (this.data.levels || []).map(function (l) {
      if (String(l.id) !== id) return l
      return Object.assign({}, l, { selected: !l.selected })
    })
    var selectedLevelIds = levels
      .filter(function (l) {
        return l.selected
      })
      .map(function (l) {
        return String(l.id)
      })
    this.setData({
      levels: levels,
      selectedLevelIds: selectedLevelIds,
      selectedLevelNamesText: this._selectedNamesText(levels),
    })
  },

  onSend() {
    var self = this
    var title = (this.data.title || '').trim()
    var content = (this.data.content || '').trim()
    if (!title || !content) {
      wx.showToast({ title: '请填写标题和内容', icon: 'none' })
      return
    }
    var payload = {
      title: title,
      content: content,
      target_type: this.data.targetType,
    }
    var selectedLevels = []
    if (this.data.targetType === 'membership') {
      selectedLevels = (this.data.levels || []).filter(function (l) {
        return l.selected
      })
      if (!selectedLevels.length) {
        wx.showToast({ title: '请至少选择一个会员等级', icon: 'none' })
        return
      }
      payload.target_membership_level_ids = selectedLevels.map(function (l) {
        return String(l.id)
      })
    }

    var confirmText =
      this.data.targetType === 'all'
        ? '将发送给全部小程序用户，确认？'
        : '将发送给 ' +
          selectedLevels.length +
          ' 个会员等级（' +
          selectedLevels
            .map(function (l) {
              return l.name
            })
            .join('、') +
          '），确认？'

    wx.showModal({
      title: '确认发送',
      content: confirmText,
      success: function (r) {
        if (!r.confirm) return
        self.setData({ sending: true })
        createRiskMessage(payload)
          .then(function (res) {
            self.setData({ sending: false, title: '', content: '' })
            wx.showToast({ title: (res && res.message) || '已发送', icon: 'success' })
            self.loadHistory()
          })
          .catch(function (e) {
            self.setData({ sending: false })
            wx.showToast({ title: (e && e.message) || '发送失败', icon: 'none' })
          })
      },
    })
  },
})

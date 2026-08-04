const { request } = require('../../utils/api')
const { ensureLogin } = require('../../utils/auth')

var POLL_INTERVAL = 3000
var MAX_POLL_DURATION_MS = 30 * 60 * 1000
var MAX_CONSECUTIVE_ERRORS = 5
var TERMINAL_STATUSES = ['completed', 'failed', 'cancelled']

var STATUS_LABELS = {
  pending: '排队中',
  processing: '生成中',
  running: '生成中',
  completed: '已完成',
  failed: '生成失败',
  cancelled: '已取消',
}

function listIncludes(list, item) {
  for (var i = 0; i < list.length; i++) {
    if (list[i] === item) return true
  }
  return false
}

function normalizeStatus(status) {
  if (!status) return ''
  var s = String(status).toLowerCase()
  return s === 'running' ? 'processing' : s
}

function isRunningStatus(status) {
  return !!status && !listIncludes(TERMINAL_STATUSES, status)
}

function isTerminalStatus(status) {
  return listIncludes(TERMINAL_STATUSES, status)
}

Page({
  data: {
    stockCode: '',
    billing: null,
    taskId: '',
    status: '',
    progress: 0,
    message: '',
    submitting: false,
    pollTimer: null,
    buttonText: '确认生成',
    isFailed: false,
  },

  onLoad: function (options) {
    var that = this
    this.setData({ stockCode: (options && options.code) || '' })
    ensureLogin()
      .then(function () { return that.loadBilling() })
      .catch(function () { wx.navigateBack() })
  },

  onUnload: function () {
    this.stopPoll()
  },

  updateButtonText: function (status) {
    var buttonText = '确认生成'
    if (this.data.taskId) {
      if (status === 'completed') buttonText = '查看报告'
      else if (status === 'failed' || status === 'cancelled') buttonText = '重新生成'
      else buttonText = '生成中...'
    }
    this.setData({
      buttonText: buttonText,
      isFailed: status === 'failed' || status === 'cancelled',
    })
  },

  getStatusLabel: function (status) {
    return STATUS_LABELS[status] || status || '处理中'
  },

  stopPoll: function () {
    if (this.data.pollTimer) {
      clearInterval(this.data.pollTimer)
      this.setData({ pollTimer: null })
    }
  },

  markTaskFailed: function (message) {
    var msg = message || '生成失败，请重试'
    this.stopPoll()
    this.setData({
      status: 'failed',
      message: msg,
      progress: 0,
    })
    this.updateButtonText('failed')
    wx.showToast({ title: msg, icon: 'none', duration: 3000 })
  },

  resetTask: function () {
    this.stopPoll()
    this.setData({
      taskId: '',
      status: '',
      progress: 0,
      message: '',
      isFailed: false,
      buttonText: '确认生成',
    })
    this._pollStartTime = 0
    this._pollErrorCount = 0
  },

  loadBilling: function () {
    var that = this
    return request({ url: '/api/mp/billing/check' })
      .then(function (res) {
        if (res.success) that.setData({ billing: res.data })
      })
      .catch(function (e) {
        console.error(e)
      })
  },

  submit: function () {
    var that = this
    if (this.data.status === 'completed' && this.data.taskId) {
      wx.redirectTo({ url: '/pages/report/report?id=' + this.data.taskId })
      return
    }

    if (this.data.taskId && isRunningStatus(this.data.status)) {
      return
    }

    if (this.data.taskId && (this.data.status === 'failed' || this.data.status === 'cancelled')) {
      this.resetTask()
    }

    this.setData({ submitting: true })
    request({
      url: '/api/mp/analysis/submit',
      method: 'POST',
      data: {
        symbol: this.data.stockCode,
        parameters: { market_type: 'A股', research_depth: '标准' },
      },
    })
      .then(function (res) {
        if (res.success) {
          var taskId = res.data.task_id
          var chargeMsg = (res.data.charge && res.data.charge.message) || '任务已提交'
          that.setData({
            taskId: taskId,
            status: 'pending',
            message: chargeMsg,
            progress: 0,
          })
          that.updateButtonText('pending')
          that.loadBilling()
          that.startPoll(taskId)
        } else {
          wx.showToast({ title: res.message || '提交失败', icon: 'none' })
        }
      })
      .catch(function (e) {
        var msg = (e && e.message) || '提交失败'
        if (e && e.detail && e.detail.message) {
          msg = e.detail.message
        }
        wx.showToast({ title: msg, icon: 'none', duration: 3000 })
      })
      .then(function () {
        that.setData({ submitting: false })
      })
  },

  pollOnce: function (taskId) {
    var that = this
    if (this._pollStartTime && Date.now() - this._pollStartTime > MAX_POLL_DURATION_MS) {
      this.markTaskFailed('生成超时，请稍后在首页查看或重试')
      return
    }

    request({ url: '/api/mp/analysis/task/' + taskId + '/status' })
      .then(function (res) {
        if (!res.success) {
          that._pollErrorCount = (that._pollErrorCount || 0) + 1
          if (that._pollErrorCount >= MAX_CONSECUTIVE_ERRORS) {
            that.markTaskFailed('无法获取任务状态，请检查网络后重试')
          }
          return
        }

        that._pollErrorCount = 0
        var d = res.data || {}
        var status = normalizeStatus(d.status)
        var message = d.message || that.getStatusLabel(status)

        that.setData({
          status: status,
          progress: d.progress || 0,
          message: message,
        })
        that.updateButtonText(status)

        if (isTerminalStatus(status)) {
          that.stopPoll()
          if (status === 'completed') {
            wx.showToast({ title: '研报生成完成', icon: 'success' })
          } else {
            wx.showToast({ title: message, icon: 'none', duration: 3000 })
          }
        }
      })
      .catch(function (e) {
        that._pollErrorCount = (that._pollErrorCount || 0) + 1
        console.error(e)
        if (that._pollErrorCount >= MAX_CONSECUTIVE_ERRORS) {
          var errMsg = (e && e.message) || '网络异常，请重试'
          that.markTaskFailed(errMsg)
        }
      })
  },

  startPoll: function (taskId) {
    var that = this
    this.stopPoll()
    this._pollStartTime = Date.now()
    this._pollErrorCount = 0

    this.pollOnce(taskId)
    var timer = setInterval(function () {
      that.pollOnce(taskId)
    }, POLL_INTERVAL)
    this.setData({ pollTimer: timer })
  },
})

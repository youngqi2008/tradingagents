const { request } = require('../../utils/api')
const { ensureLogin } = require('../../utils/auth')

var POLL_INTERVAL = 3000
var MAX_POLL_DURATION_MS = 30 * 60 * 1000
var MAX_CONSECUTIVE_ERRORS = 5
var TERMINAL_STATUSES = ['completed', 'failed', 'cancelled']
var ACTIVE_TASK_KEY = 'mp_active_report_task'

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

function formatElapsed(ms) {
  var totalSec = Math.max(0, Math.floor(ms / 1000))
  var m = Math.floor(totalSec / 60)
  var s = totalSec % 60
  if (m <= 0) return s + ' 秒'
  return m + ' 分 ' + (s < 10 ? '0' + s : s) + ' 秒'
}

function saveActiveTask(task) {
  try {
    wx.setStorageSync(ACTIVE_TASK_KEY, task)
  } catch (e) {}
}

function clearActiveTask() {
  try {
    wx.removeStorageSync(ACTIVE_TASK_KEY)
  } catch (e) {}
}

function readActiveTask() {
  try {
    return wx.getStorageSync(ACTIVE_TASK_KEY) || null
  } catch (e) {
    return null
  }
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
    isRunning: false,
    elapsedText: '',
    waitTip: '深度研报通常需要 5–10 分钟，可先离开，完成后在「投研 → 研报」查看。',
  },

  onLoad: function (options) {
    var that = this
    this.setData({ stockCode: (options && options.code) || '' })
    ensureLogin()
      .then(function () { return that.loadBilling() })
      .then(function () { that.tryRestoreActiveTask() })
      .catch(function () { wx.navigateBack() })
  },

  onShow: function () {
    if (this.data.taskId && isRunningStatus(this.data.status) && !this.data.pollTimer) {
      this.startPoll(this.data.taskId, { resume: true })
    } else if (!this.data.taskId) {
      this.tryRestoreActiveTask()
    }
  },

  onUnload: function () {
    this.stopPoll()
    this.stopElapsedTimer()
  },

  tryRestoreActiveTask: function () {
    var saved = readActiveTask()
    if (!saved || !saved.taskId) return
    if (this.data.stockCode && saved.stockCode && saved.stockCode !== this.data.stockCode) {
      return
    }
    this.setData({
      stockCode: saved.stockCode || this.data.stockCode,
      taskId: saved.taskId,
      status: saved.status || 'processing',
      progress: saved.progress || 0,
      message: saved.message || '正在恢复任务进度…',
      isRunning: true,
    })
    this.updateButtonText(normalizeStatus(saved.status || 'processing'))
    this._pollStartTime = saved.startedAt || Date.now()
    this.refreshElapsed()
    this.startElapsedTimer()
    this.startPoll(saved.taskId, { resume: true })
  },

  updateButtonText: function (status) {
    var buttonText = '确认生成'
    var isRunning = false
    if (this.data.taskId) {
      if (status === 'completed') buttonText = '查看报告'
      else if (status === 'failed' || status === 'cancelled') buttonText = '重新生成'
      else {
        buttonText = '生成中...'
        isRunning = true
      }
    }
    this.setData({
      buttonText: buttonText,
      isFailed: status === 'failed' || status === 'cancelled',
      isRunning: isRunning,
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

  stopElapsedTimer: function () {
    if (this._elapsedTimer) {
      clearInterval(this._elapsedTimer)
      this._elapsedTimer = null
    }
  },

  startElapsedTimer: function () {
    var that = this
    this.stopElapsedTimer()
    this.refreshElapsed()
    this._elapsedTimer = setInterval(function () {
      that.refreshElapsed()
    }, 1000)
  },

  refreshElapsed: function () {
    if (!this._pollStartTime || !this.data.isRunning) {
      this.setData({ elapsedText: '' })
      return
    }
    this.setData({
      elapsedText: '已等待 ' + formatElapsed(Date.now() - this._pollStartTime),
    })
  },

  markTaskFailed: function (message) {
    var msg = message || '生成失败，请重试'
    this.stopPoll()
    this.stopElapsedTimer()
    clearActiveTask()
    this.setData({
      status: 'failed',
      message: msg,
      progress: 0,
      isRunning: false,
      elapsedText: '',
    })
    this.updateButtonText('failed')
    wx.showToast({ title: msg, icon: 'none', duration: 3000 })
  },

  resetTask: function () {
    this.stopPoll()
    this.stopElapsedTimer()
    clearActiveTask()
    this.setData({
      taskId: '',
      status: '',
      progress: 0,
      message: '',
      isFailed: false,
      isRunning: false,
      elapsedText: '',
      buttonText: '确认生成',
    })
    this._pollStartTime = 0
    this._pollErrorCount = 0
  },

  persistActiveTask: function (extra) {
    if (!this.data.taskId || !isRunningStatus(this.data.status)) return
    var payload = {
      taskId: this.data.taskId,
      stockCode: this.data.stockCode,
      status: this.data.status,
      progress: this.data.progress,
      message: this.data.message,
      startedAt: this._pollStartTime || Date.now(),
      updatedAt: Date.now(),
    }
    if (extra) {
      for (var k in extra) {
        if (Object.prototype.hasOwnProperty.call(extra, k)) payload[k] = extra[k]
      }
    }
    saveActiveTask(payload)
  },

  goHomeLater: function () {
    this.persistActiveTask()
    try {
      wx.setStorageSync('research_pane', 'report')
    } catch (e) {}
    wx.showToast({
      title: '可稍后在投研·研报查看',
      icon: 'none',
      duration: 2000,
    })
    setTimeout(function () {
      wx.switchTab({ url: '/pages/chat/chat' })
    }, 400)
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
      clearActiveTask()
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
          that._pollStartTime = Date.now()
          that.setData({
            taskId: taskId,
            status: 'pending',
            message: chargeMsg,
            progress: 0,
            isRunning: true,
          })
          that.updateButtonText('pending')
          that.loadBilling()
          saveActiveTask({
            taskId: taskId,
            stockCode: that.data.stockCode,
            status: 'pending',
            progress: 0,
            message: chargeMsg,
            startedAt: that._pollStartTime,
            updatedAt: Date.now(),
          })
          that.startElapsedTimer()
          that.startPoll(taskId)
          wx.showModal({
            title: '研报生成中',
            content: '深度研报通常需要 5–10 分钟。您可先离开本页，完成后在「投研 → 研报」查看。',
            showCancel: true,
            cancelText: '继续等待',
            confirmText: '稍后查看',
            success: function (r) {
              if (r.confirm) that.goHomeLater()
            },
          })
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
          isRunning: isRunningStatus(status),
        })
        that.updateButtonText(status)
        that.refreshElapsed()

        if (isTerminalStatus(status)) {
          that.stopPoll()
          that.stopElapsedTimer()
          clearActiveTask()
          if (status === 'completed') {
            wx.showToast({ title: '研报生成完成', icon: 'success' })
          } else {
            wx.showToast({ title: message, icon: 'none', duration: 3000 })
          }
        } else {
          saveActiveTask({
            taskId: taskId,
            stockCode: that.data.stockCode,
            status: status,
            progress: d.progress || 0,
            message: message,
            startedAt: that._pollStartTime || Date.now(),
            updatedAt: Date.now(),
          })
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

  startPoll: function (taskId, options) {
    var that = this
    this.stopPoll()
    if (!(options && options.resume) || !this._pollStartTime) {
      this._pollStartTime = this._pollStartTime || Date.now()
    }
    this._pollErrorCount = 0
    if (!this._elapsedTimer) this.startElapsedTimer()

    this.pollOnce(taskId)
    var timer = setInterval(function () {
      that.pollOnce(taskId)
    }, POLL_INTERVAL)
    this.setData({ pollTimer: timer })
  },
})

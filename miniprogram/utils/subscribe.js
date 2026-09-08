const { getPushSubscribeConfig } = require('./api')

var TMPL_KEY = 'signalSubscribeTmplIds'
var STATUS_KEY = 'signalSubscribeStatus'
var KEEP_HINT_KEY = 'signalSubscribeKeepHinted'
var OPENED_KEY = 'signalSubscribeOpened'
var FALLBACK_TMPL_IDS = ['6M6xTb1tszyymlTS2coayXwIgbmuisN6g68rOfWvWX0']
var _inflight = null
var _lastSilentAt = 0

function acceptedFromResult(res) {
  var result = (res && res.result) || {}
  var ids = Object.keys(result)
  for (var i = 0; i < ids.length; i++) {
    if (result[ids[i]] === 'accept') return true
  }
  return false
}

function getCachedTemplateIds() {
  try {
    var ids = wx.getStorageSync(TMPL_KEY)
    return Array.isArray(ids) ? ids.filter(Boolean) : []
  } catch (e) {
    return []
  }
}

function setCachedTemplateIds(ids) {
  try {
    wx.setStorageSync(TMPL_KEY, Array.isArray(ids) ? ids.filter(Boolean) : [])
  } catch (e) {}
}

function getSubscribeTmplIds() {
  var ids = getCachedTemplateIds()
  return ids.length ? ids : FALLBACK_TMPL_IDS.slice()
}

function getCachedStatus() {
  try {
    return wx.getStorageSync(STATUS_KEY) || {}
  } catch (e) {
    return {}
  }
}

function setCachedStatus(status) {
  try {
    wx.setStorageSync(STATUS_KEY, status || {})
  } catch (e) {}
}

function isOpened() {
  try {
    return !!wx.getStorageSync(OPENED_KEY)
  } catch (e) {
    return false
  }
}

function markOpened() {
  try {
    wx.setStorageSync(OPENED_KEY, 1)
  } catch (e) {}
}

function prefetchSubscribeConfig() {
  return getPushSubscribeConfig()
    .then(function (cfg) {
      var ids = (cfg && cfg.template_ids) || []
      if (ids.length) setCachedTemplateIds(ids)
      return cfg || {}
    })
    .catch(function () {
      return {}
    })
}

function refreshSubscribeStatus() {
  return prefetchSubscribeConfig().then(function (cfg) {
    var tmplId = ((cfg && cfg.template_ids) || [])[0] || getSubscribeTmplIds()[0] || ''
    return new Promise(function (resolve) {
      if (!wx.getSetting) {
        resolve(getCachedStatus())
        return
      }
      wx.getSetting({
        withSubscriptions: true,
        success: function (res) {
          var sub = (res && res.subscriptionsSetting) || {}
          var item = ((sub.itemSettings || {})[tmplId] || '').toString()
          var status = {
            enabled: !!(cfg && cfg.enabled) || !!tmplId,
            tmplId: tmplId,
            mainSwitch: sub.mainSwitch !== false,
            always: item,
            opened: isOpened(),
            updatedAt: Date.now(),
          }
          setCachedStatus(status)
          resolve(status)
        },
        fail: function () {
          resolve(getCachedStatus())
        },
      })
    })
  })
}

function isAlwaysAccept(status) {
  var s = status || getCachedStatus()
  return s.mainSwitch !== false && s.always === 'accept'
}

function isAlwaysReject(status) {
  var s = status || getCachedStatus()
  return s.mainSwitch === false || s.always === 'reject' || s.always === 'ban'
}

function subscribeStatusText(status) {
  if (isAlwaysReject(status)) return '已关闭'
  if (isAlwaysAccept(status)) return '已记住选择'
  if (isOpened() || (status && status.opened)) return '已开启'
  return '未开启'
}

function failMessage(err) {
  var msg = (err && (err.errMsg || err.message)) || ''
  if (msg.indexOf('TAP') >= 0 || msg.indexOf('gesture') >= 0 || msg.indexOf('user tap') >= 0) {
    return '请再点一次开启'
  }
  if (msg.indexOf('cancel') >= 0) return '已取消'
  if (msg.indexOf('ban') >= 0 || msg.indexOf('20004') >= 0) {
    return '请在微信设置中打开服务通知'
  }
  if (msg.indexOf('template') >= 0 || msg.indexOf('20001') >= 0) {
    return '订阅模板无效，请稍后重试'
  }
  return msg ? '开启失败' : '开启失败，请重试'
}

function invokeSubscribe(ids) {
  if (_inflight) return _inflight
  var p = new Promise(function (resolve) {
    if (!wx.requestSubscribeMessage) {
      resolve({ skipped: false, fail: true, accepted: false, error: { errMsg: '当前基础库不支持订阅消息' } })
      return
    }
    wx.requestSubscribeMessage({
      tmplIds: ids.slice(0, 3),
      success: function (res) {
        if (_inflight === p) _inflight = null
        var accepted = acceptedFromResult({ result: res })
        if (accepted) markOpened()
        var out = { skipped: false, result: res, accepted: accepted, opened: accepted || isOpened() }
        refreshSubscribeStatus()
          .then(function (status) {
            out.always = isAlwaysAccept(status)
            out.rejected = isAlwaysReject(status)
            out.status = status
            out.opened = isOpened()
            resolve(out)
          })
          .catch(function () {
            resolve(out)
          })
      },
      fail: function (err) {
        if (_inflight === p) _inflight = null
        resolve({ skipped: false, fail: true, error: err, accepted: false })
      },
    })
  })
  _inflight = p
  return p
}

function hintKeepChoiceIfNeeded(res) {
  if (!res || !res.accepted || res.always) return res
  var hinted = false
  try {
    hinted = !!wx.getStorageSync(KEEP_HINT_KEY)
  } catch (e) {}
  if (hinted) return res
  try {
    wx.setStorageSync(KEEP_HINT_KEY, 1)
  } catch (e) {}
  wx.showModal({
    title: '建议勾选「总是保持以上选择」',
    content:
      '已开启。当前是一次性订阅，每勾一次大约只能推 1 条。下次请勾选底部「总是保持以上选择」，之后点开动态会自动续额度。',
    showCancel: false,
    confirmText: '知道了',
  })
  return res
}

function describeSubscribeResult(res) {
  if (!res) return ''
  if (res.skipped) {
    if (res.reason === '未配置模板') return '请先在后台配置订阅消息模板'
    return ''
  }
  if (res.fail) return failMessage(res.error)
  if (res.always) return '已记住选择，点开动态会自动续提醒'
  if (res.accepted || res.opened) return '已开启微信提醒'
  return '未勾选通知，动态只在本页展示'
}

function requestSignalSubscribe(options) {
  var opts = options || {}
  var silent = !!opts.silent
  var ids = getSubscribeTmplIds()
  prefetchSubscribeConfig()

  if (!ids.length) {
    return Promise.resolve({ skipped: true, reason: '未配置模板', accepted: false })
  }
  if (silent) {
    if (isAlwaysReject()) {
      return Promise.resolve({ skipped: true, reason: '已关闭提醒', accepted: false })
    }
    if (!isAlwaysAccept()) {
      return Promise.resolve({ skipped: true, reason: '未记住选择', accepted: false })
    }
    var now = Date.now()
    if (now - _lastSilentAt < 1200) {
      return Promise.resolve({ skipped: true, reason: '节流', accepted: true, always: true })
    }
    _lastSilentAt = now
  }
  return invokeSubscribe(ids).then(function (res) {
    if (!silent) return hintKeepChoiceIfNeeded(res)
    return res
  })
}

function replenishSignalSubscribe() {
  return requestSignalSubscribe({ silent: true })
}

function askSignalSubscribeWithModal(options) {
  var opts = options || {}
  return refreshSubscribeStatus().then(function (status) {
    if (isAlwaysAccept(status)) {
      return requestSignalSubscribe({ silent: true }).then(function (res) {
        return Object.assign({ skipped: false, accepted: true, always: true }, res || {})
      })
    }
    if (isAlwaysReject(status)) {
      return new Promise(function (resolve) {
        wx.showModal({
          title: '微信提醒已关闭',
          content: '请先在微信「设置 → 通知管理」中打开本小程序服务通知，再点开启。',
          confirmText: '再试一次',
          cancelText: '取消',
          success: function (r) {
            if (!r.confirm) {
              resolve({ skipped: true, reason: '用户取消', accepted: false, rejected: true })
              return
            }
            requestSignalSubscribe().then(resolve)
          },
          fail: function () {
            resolve({ skipped: true, reason: '弹窗失败', accepted: false })
          },
        })
      })
    }
    return new Promise(function (resolve) {
      wx.showModal({
        title: opts.title || '开启微信提醒',
        content:
          opts.content ||
          '下一页请勾选通知，并务必勾选底部「总是保持以上选择」。勾选后点开动态会自动续额度，微信才能连续收到。',
        confirmText: opts.confirmText || '立即开启',
        cancelText: '以后再说',
        success: function (r) {
          if (!r.confirm) {
            resolve({ skipped: true, reason: '用户取消', accepted: false })
            return
          }
          requestSignalSubscribe().then(resolve)
        },
        fail: function () {
          resolve({ skipped: true, reason: '弹窗失败', accepted: false })
        },
      })
    })
  })
}

function pickQueryId(opts) {
  if (!opts) return ''
  var q = opts.query || opts
  return q && q.id ? String(q.id) : ''
}

function savePendingSignalId(id) {
  var nid = String(id || '').trim()
  if (!nid) return
  try {
    wx.setStorageSync('pendingSignalId', nid)
  } catch (e) {}
  try {
    var app = getApp()
    if (app && app.globalData) app.globalData.pendingSignalId = nid
  } catch (e) {}
}

function takePendingSignalId() {
  var id = ''
  try {
    var app = getApp()
    if (app && app.globalData && app.globalData.pendingSignalId) {
      id = String(app.globalData.pendingSignalId)
      app.globalData.pendingSignalId = ''
    }
  } catch (e) {}
  if (!id) {
    try {
      id = String(wx.getStorageSync('pendingSignalId') || '')
    } catch (e) {}
  }
  try {
    wx.removeStorageSync('pendingSignalId')
  } catch (e) {}
  return String(id || '').trim()
}

module.exports = {
  requestSignalSubscribe,
  replenishSignalSubscribe,
  askSignalSubscribeWithModal,
  prefetchSubscribeConfig,
  refreshSubscribeStatus,
  getCachedStatus,
  isAlwaysAccept,
  isAlwaysReject,
  isOpened,
  subscribeStatusText,
  describeSubscribeResult,
  hintKeepChoiceIfNeeded,
  acceptedFromResult,
  pickQueryId,
  savePendingSignalId,
  takePendingSignalId,
}

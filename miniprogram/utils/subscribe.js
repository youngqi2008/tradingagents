const { getPushSubscribeConfig } = require('./api')

function acceptedFromResult(res) {
  var result = (res && res.result) || {}
  var ids = Object.keys(result)
  for (var i = 0; i < ids.length; i++) {
    if (result[ids[i]] === 'accept') return true
  }
  return false
}

function requestSignalSubscribe() {
  return getPushSubscribeConfig()
    .then(function (cfg) {
      var ids = (cfg && cfg.template_ids) || []
      if (!ids.length) {
        return { skipped: true, reason: '未配置模板' }
      }
      return new Promise(function (resolve) {
        wx.requestSubscribeMessage({
          tmplIds: ids.slice(0, 3),
          success: function (res) {
            resolve({ skipped: false, result: res, accepted: acceptedFromResult({ result: res }) })
          },
          fail: function (err) {
            resolve({ skipped: false, fail: true, error: err, accepted: false })
          },
        })
      })
    })
    .catch(function () {
      return { skipped: true, reason: '配置拉取失败', accepted: false }
    })
}

function askSignalSubscribeWithModal(options) {
  var opts = options || {}
  return new Promise(function (resolve) {
    wx.showModal({
      title: opts.title || '开启微信提醒',
      content:
        opts.content ||
        '勾选后，关注信号发出时微信会立刻通知你。建议同时勾选「总是保持以上选择」。',
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
  askSignalSubscribeWithModal,
  acceptedFromResult,
  pickQueryId,
  savePendingSignalId,
  takePendingSignalId,
}

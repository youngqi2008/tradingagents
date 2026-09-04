const { getPushSubscribeConfig } = require('./api')

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
            resolve({ skipped: false, result: res })
          },
          fail: function (err) {
            resolve({ skipped: false, fail: true, error: err })
          },
        })
      })
    })
    .catch(function () {
      return { skipped: true, reason: '配置拉取失败' }
    })
}

module.exports = {
  requestSignalSubscribe,
}

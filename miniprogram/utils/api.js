const {
  getToken,
  setAuth,
  clearAuth,
  getUser,
  setUserInfo,
  getUserInfo,
  needsProfileSetup,
  setProfileSetupPending,
} = require('./auth')



// 测试环境（内网 192.168.10.104，nginx :80）
// const BASE_URL = 'http://192.168.10.104'
// 生产经 docker-nginx-1:443 反代（勿写 IP:18888，体验版不可用）
const BASE_URL = 'https://ares.zhystech.cn'

const DEFAULT_TIMEOUT = 30000

const LOGIN_TIMEOUT = 60000

// 问股 Agent 含数据拉取 + LLM，通常需 1~3 分钟
const ASK_TIMEOUT = 300000



// 联调时可设为 'dev:tester'，走后端开发登录；上线前务必清空

const DEV_LOGIN_CODE = ''



function buildHeaders(token, extra) {

  var headers = { 'Content-Type': 'application/json' }

  if (token) {

    headers.Authorization = 'Bearer ' + token

  }

  if (extra) {

    for (var key in extra) {

      if (Object.prototype.hasOwnProperty.call(extra, key)) {

        headers[key] = extra[key]

      }

    }

  }

  return headers

}



function buildImageUrl(path) {

  if (!path) return ''

  if (path.indexOf('http://') === 0 || path.indexOf('https://') === 0) return path

  if (path.indexOf('wxfile://') === 0) return path

  return BASE_URL + (path.charAt(0) === '/' ? path : '/' + path)

}



function prepareRequestData(method, data) {

  if (!data) return data

  var m = (method || 'GET').toUpperCase()

  if (m === 'POST' || m === 'PUT' || m === 'PATCH') {

    if (typeof data === 'object') {

      return JSON.stringify(data)

    }

  }

  return data

}



function formatFailError(err, fullUrl) {

  var msg = (err && err.errMsg) || '网络请求失败'

  if (msg.indexOf('timeout') >= 0) {
    if (fullUrl && (fullUrl.indexOf('/ask') >= 0 || fullUrl.indexOf('/ask/stream') >= 0)) {
      return '问股分析超时，AI 仍在处理中可能需要更久。请稍后重试，或切换网络后再试。'
    }

    return (

      '连接服务器超时\n' +

      fullUrl +

      '\n\n请检查：\n' +

      '1. 开发者工具 → 设置 → 代理 → 不使用代理\n' +

      '2. 详情 → 本地设置 → 不校验合法域名\n' +

      '3. 本机能否访问该地址（浏览器打开 /api/health）\n' +

      '4. 仍失败可试「真机调试」'

    )

  }

  if (msg.indexOf('fail') >= 0) {
    // 体验版常见: url not in domain list / ssl / net::ERR
    return '无法连接服务器\n' + fullUrl + '\n\n原因: ' + msg
  }

  return msg

}



function extractErrorMessage(data, fallback) {

  if (!data) return fallback

  if (typeof data === 'string') {

    var plain = data.replace(/<[^>]+>/g, ' ').trim()

    return plain ? plain.slice(0, 160) : fallback

  }

  if (typeof data.message === 'string') return data.message

  if (data.detail) {

    if (typeof data.detail === 'string') return data.detail

    if (typeof data.detail.message === 'string') return data.detail.message

    if (Array.isArray(data.detail) && data.detail.length) {

      var first = data.detail[0]

      if (typeof first === 'string') return first

      if (first && typeof first.msg === 'string') return first.msg

    }

  }

  return fallback

}



function request(options) {

  var token = getToken()

  var method = options.method || 'GET'

  var fullUrl = BASE_URL + options.url

  var timeout = options.timeout || DEFAULT_TIMEOUT



  return new Promise(function (resolve, reject) {

    console.log('[API]', method, fullUrl)

    wx.request({

      url: fullUrl,

      method: method,

      data: prepareRequestData(method, options.data),

      header: buildHeaders(token, options.header),

      timeout: timeout,

      enableHttp2: false,

      success: function (res) {

        console.log('[API]', res.statusCode, options.url)

        if (res.statusCode === 401) {
          if (token) {
            clearAuth()
            wx.showToast({ title: '请重新登录', icon: 'none' })
          }
          reject(new Error('未登录'))
          return
        }

        if (res.statusCode === 402) {

          var detail = res.data && res.data.detail

          var msg = extractErrorMessage(res.data, '余额不足，请先充值')

          var balance = detail && detail.balance

          var required = detail && detail.required

          var content = msg

          if (balance !== undefined && required !== undefined) {

            content = msg + '\n当前余额 ¥' + balance + '，需要 ¥' + required

          }

          wx.showModal({

            title: '余额不足',

            content: content,

            confirmText: '去充值',

            cancelText: '知道了',

            success: function (r) {

              if (r.confirm) wx.navigateTo({ url: '/pages/recharge/recharge' })

            },

          })

          var err = new Error(msg)

          err.statusCode = 402

          err.detail = detail

          reject(err)

          return

        }

        if (res.statusCode >= 400) {

          var errMsg = extractErrorMessage(res.data, '请求失败')

          console.error('[API] error', res.statusCode, options.url, res.data)

          var httpErr = new Error(errMsg === '请求失败' ? ('请求失败(' + res.statusCode + ')') : errMsg)

          httpErr.statusCode = res.statusCode

          httpErr.data = res.data

          reject(httpErr)

          return

        }

        resolve(res.data)

      },

      fail: function (err) {

        console.error('[API] fail', fullUrl, err)

        reject(new Error(formatFailError(err, fullUrl)))

      },

    })

  })

}



function checkServer() {

  return request({ url: '/api/health', timeout: 10000 })

}



function miniprogramLogin(code, userInfo) {

  var payload = {

    code: code,

    nickname: (userInfo && userInfo.nickName) || '',

    avatar_url: (userInfo && userInfo.avatarUrl) || '',

  }

  return request({

    url: '/api/mp/auth/login',

    method: 'POST',

    data: payload,

    timeout: LOGIN_TIMEOUT,

  }).then(function (data) {

    var token = (data.data && data.data.access_token) || data.access_token

    var user = (data.data && data.data.user) || data.user

    if (!token || !user) {

      throw new Error(data.message || '登录失败')

    }

    setAuth(token, user)

    // 确保本地持久化角色：缺省视为普通，避免误展示风控 Tab
    try {
      var stored = getUser() || user || {}
      if (!stored.role) {
        stored.role = 'normal'
        stored.role_name = stored.role_name || '普通'
        setAuth(token, Object.assign({}, user, stored))
      }
    } catch (e) {}

    var finish = function () {
      try {
        if (needsProfileSetup(user)) {
          setProfileSetupPending(true)
        } else {
          setProfileSetupPending(false)
        }
      } catch (e) {}
      return { access_token: token, user: user }
    }

    if (userInfo && (userInfo.nickName || userInfo.avatarUrl)) {

      setUserInfo(userInfo)
      return finish()

    } else if (user.nickname || user.avatar_url) {

      return applyAvatarDisplay(user.nickname, user.avatar_url).then(function (displayInfo) {

        setUserInfo(displayInfo)

        return finish()

      })

    }

    return finish()

  })

}



function login(userInfo) {

  return new Promise(function (resolve, reject) {

    wx.login({

      success: function (res) {

        if (!res.code) {

          reject(new Error('wx.login 失败'))

          return

        }

        var code = DEV_LOGIN_CODE || res.code

        if (DEV_LOGIN_CODE) {

          console.warn('[DEV] 使用调试登录 code:', DEV_LOGIN_CODE)

        }

        miniprogramLogin(code, userInfo || {})

          .then(resolve)

          .catch(reject)

      },

      fail: function (err) {

        reject(new Error((err && err.errMsg) || 'wx.login 失败'))

      },

    })

  })

}



function getMe() {

  return request({ url: '/api/mp/auth/me' }).then(function (res) {

    return (res && res.data) || res.user

  })

}



function updateMe(patch) {

  return request({

    url: '/api/mp/auth/me',

    method: 'PATCH',

    data: patch,

  })

}



function isLocalImagePath(url) {
  if (!url) return false
  return (
    url.indexOf('wxfile://') === 0 ||
    url.indexOf('http://tmp/') === 0 ||
    url.indexOf('https://tmp/') === 0
  )
}

function downloadImage(url) {
  if (!url) return Promise.resolve('')
  if (isLocalImagePath(url)) return Promise.resolve(url)
  return new Promise(function (resolve) {
    wx.downloadFile({
      url: url,
      success: function (res) {
        if (res.statusCode === 200 && res.tempFilePath) {
          resolve(res.tempFilePath)
        } else {
          resolve('')
        }
      },
      fail: function () {
        resolve('')
      },
    })
  })
}

function applyAvatarDisplay(nickName, avatarPath) {
  var info = { nickName: nickName || '', avatarUrl: '' }
  if (!avatarPath) return Promise.resolve(info)
  if (isLocalImagePath(avatarPath)) {
    info.avatarUrl = avatarPath
    return Promise.resolve(info)
  }
  return downloadImage(buildImageUrl(avatarPath)).then(function (localPath) {
    info.avatarUrl = localPath || ''
    return info
  })
}

function uploadAvatar(filePath) {

  return new Promise(function (resolve, reject) {

    var token = getToken()

    if (!token) return reject(new Error('未登录'))

    wx.uploadFile({

      url: BASE_URL + '/api/mp/auth/me/avatar',

      filePath: filePath,

      name: 'file',

      header: { Authorization: 'Bearer ' + token },

      success: function (res) {

        var data = res.data

        try {

          data = typeof data === 'string' ? JSON.parse(data) : data

        } catch (e) {

          /* ignore */

        }

        if (res.statusCode >= 200 && res.statusCode < 300) {

          resolve(data)

        } else {

          reject(new Error(extractErrorMessage(data, '上传失败')))

        }

      },

      fail: function (err) {

        reject(new Error((err && err.errMsg) || '上传失败'))

      },

    })

  })

}



function listChatStrategies() {
  return request({ url: '/api/mp/chat/strategies' }).then(function (res) {
    return (res.data && res.data.strategies) || []
  })
}

function listChatSessions() {
  return request({ url: '/api/mp/chat/sessions' }).then(function (res) {
    return (res.data && res.data.sessions) || []
  })
}

function createChatSession(data) {
  return request({
    url: '/api/mp/chat/sessions',
    method: 'POST',
    data: data || {},
    timeout: LOGIN_TIMEOUT,
  }).then(function (res) {
    return res.data
  })
}

function listChatMessages(sessionId) {
  return request({ url: '/api/mp/chat/sessions/' + sessionId + '/messages' }).then(function (res) {
    return (res.data && res.data.messages) || []
  })
}

function decodeArrayBuffer(buffer) {
  if (!buffer) return ''
  if (typeof TextDecoder !== 'undefined') {
    try {
      return new TextDecoder('utf-8').decode(buffer)
    } catch (e) {}
  }
  var arr = new Uint8Array(buffer)
  var chunks = []
  var step = 0x8000
  for (var i = 0; i < arr.length; i += step) {
    chunks.push(String.fromCharCode.apply(null, arr.subarray(i, i + step)))
  }
  return chunks.join('')
}

function parseSSEBlock(block, onEvent) {
  if (!block || !block.trim()) return
  var lines = block.split('\n')
  var eventName = 'message'
  var dataLines = []
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i]
    if (line.indexOf('event:') === 0) {
      eventName = line.slice(6).trim()
    } else if (line.indexOf('data:') === 0) {
      dataLines.push(line.slice(5).trim())
    }
  }
  if (!dataLines.length) return
  try {
    onEvent(eventName, JSON.parse(dataLines.join('\n')))
  } catch (e) {
    console.warn('[SSE] parse failed', e, block)
  }
}

function consumeSSEBuffer(buffer, onEvent) {
  var remainder = buffer
  var sep = '\n\n'
  var idx = remainder.indexOf(sep)
  while (idx >= 0) {
    parseSSEBlock(remainder.slice(0, idx), onEvent)
    remainder = remainder.slice(idx + sep.length)
    idx = remainder.indexOf(sep)
  }
  return remainder
}

var ASK_TOOL_LABELS = {
  get_stock_quote: '行情数据',
  get_stock_kline: 'K线数据',
  get_stock_fundamentals: '基本面',
  search_stock_news: '新闻资讯',
  search_web: '网络搜索',
  get_market_overview: '市场概况',
}

function formatAskProgress(data) {
  if (!data) return '分析中…'
  if (data.type === 'thinking') return data.message || '正在思考…'
  if (data.type === 'tool_start') {
    var toolName = ASK_TOOL_LABELS[data.tool] || data.tool || '工具'
    return '正在获取' + toolName + '…'
  }
  if (data.type === 'tool_done') {
    var doneTool = ASK_TOOL_LABELS[data.tool] || data.tool || '工具'
    return '已完成' + doneTool + '，继续分析…'
  }
  if (data.type === 'generating') return data.message || '正在生成最终分析…'
  return '分析中…'
}

function canAskStream() {
  return !!(wx.canIUse && wx.canIUse('request.enableChunked'))
}

function askInSessionStream(sessionId, message, strategyId, handlers) {
  handlers = handlers || {}
  var token = getToken()
  var fullUrl = BASE_URL + '/api/mp/chat/sessions/' + sessionId + '/ask/stream'
  var payload = { message: message }
  if (strategyId) payload.strategy_id = strategyId
  var buffer = ''
  var settled = false

  function dispatch(event, data) {
    if (event === 'connected') {
      if (handlers.onConnected) handlers.onConnected(data)
      return
    }
    if (event === 'user_message') {
      if (handlers.onUserMessage) handlers.onUserMessage(data)
      return
    }
    if (event === 'progress') {
      if (handlers.onProgress) handlers.onProgress(data)
      return
    }
    if (event === 'heartbeat') {
      if (handlers.onHeartbeat) handlers.onHeartbeat(data)
      return
    }
    if (event === 'done') {
      finish(null, data)
      return
    }
    if (event === 'error') {
      var err = new Error((data && data.message) || '问股失败')
      if (data && data.code === 402) err.statusCode = 402
      finish(err)
    }
  }

  function finish(err, data) {
    if (settled) return
    settled = true
    if (err) {
      if (handlers.onError) handlers.onError(err)
      return
    }
    if (handlers.onDone) handlers.onDone(data || {})
  }

  function appendChunk(chunk) {
    if (!chunk) return
    buffer = consumeSSEBuffer(buffer + chunk, dispatch)
  }

  var requestTask = wx.request({
    url: fullUrl,
    method: 'POST',
    enableChunked: true,
    timeout: ASK_TIMEOUT,
    header: buildHeaders(token),
    data: JSON.stringify(payload),
    success: function (res) {
      if (settled) return
      if (res.statusCode === 401) {
        clearAuth()
        wx.showToast({ title: '请重新登录', icon: 'none' })
        finish(new Error('未登录'))
        return
      }
      if (res.statusCode === 402) {
        var detail402 = res.data && res.data.detail
        var msg402 = extractErrorMessage(res.data, '当前无法完成该操作')
        wx.showToast({ title: msg402, icon: 'none' })
        var err402 = new Error(msg402)
        err402.statusCode = 402
        finish(err402)
        return
      }
      if (res.statusCode >= 400) {
        finish(new Error(extractErrorMessage(res.data, '问股失败')))
        return
      }
      if (typeof res.data === 'string') appendChunk(res.data)
    },
    fail: function (err) {
      finish(new Error(formatFailError(err, fullUrl)))
    },
  })

  if (requestTask && requestTask.onChunkReceived) {
    requestTask.onChunkReceived(function (res) {
      appendChunk(decodeArrayBuffer(res.data))
    })
  }

  return {
    abort: function () {
      if (requestTask && requestTask.abort) requestTask.abort()
    },
  }
}

function askInSession(sessionId, message, strategyId) {
  var payload = { message: message }
  if (strategyId) payload.strategy_id = strategyId
  return request({
    url: '/api/mp/chat/sessions/' + sessionId + '/ask',
    method: 'POST',
    data: payload,
    timeout: ASK_TIMEOUT,
  }).then(function (res) {
    return res.data
  })
}

function getFollowUpSuggestions(sessionId) {
  return request({ url: '/api/mp/chat/sessions/' + sessionId + '/follow-ups' }).then(function (res) {
    return (res.data && res.data.follow_up_suggestions) || []
  })
}

function listMembershipLevels() {
  return request({ url: '/api/mp/membership/levels' }).then(function (res) {
    return (res && res.data) || {}
  })
}

function changeMembership(membershipLevelId) {
  return request({
    url: '/api/mp/membership/change',
    method: 'POST',
    data: { membership_level_id: String(membershipLevelId) },
  })
}

function getNotificationUnreadCount() {
  return request({ url: '/api/mp/notifications/unread-count' }).then(function (res) {
    return (res.data && res.data.unread_count) || 0
  })
}

function listNotifications(params) {
  var q = []
  if (params && params.skip) q.push('skip=' + params.skip)
  if (params && params.limit) q.push('limit=' + params.limit)
  if (params && params.notice_types) {
    q.push('notice_types=' + encodeURIComponent(params.notice_types))
  }
  var url = '/api/mp/notifications' + (q.length ? '?' + q.join('&') : '')
  return request({ url: url }).then(function (res) {
    return (res && res.data) || {}
  })
}

function markNotificationRead(notificationId) {
  return request({
    url: '/api/mp/notifications/' + notificationId + '/read',
    method: 'POST',
  })
}

function markAllNotificationsRead() {
  return request({
    url: '/api/mp/notifications/read-all',
    method: 'POST',
  })
}

function createRiskMessage(payload) {
  return request({
    url: '/api/mp/risk-messages',
    method: 'POST',
    data: payload || {},
  })
}

function listRiskMessages(params) {
  var q = []
  if (params && params.skip) q.push('skip=' + params.skip)
  if (params && params.limit) q.push('limit=' + params.limit)
  var url = '/api/mp/risk-messages' + (q.length ? '?' + q.join('&') : '')
  return request({ url: url }).then(function (res) {
    return (res && res.data) || {}
  })
}

function searchStocks(q, limit) {
  var query = 'q=' + encodeURIComponent(q || '')
  if (limit) query += '&limit=' + limit
  return request({ url: '/api/mp/stocks/search?' + query })
}

function getStockQuote(code, forceRefresh) {
  var url = '/api/mp/stocks/' + encodeURIComponent(code) + '/quote'
  if (forceRefresh) url += '?force_refresh=true'
  return request({ url: url })
}

function getStockKline(code, period, limit, adj) {
  period = period || 'day'
  limit = limit || 120
  adj = adj || 'none'
  var url =
    '/api/mp/stocks/' +
    encodeURIComponent(code) +
    '/kline?period=' +
    encodeURIComponent(period) +
    '&limit=' +
    limit +
    '&adj=' +
    encodeURIComponent(adj)
  return request({ url: url })
}

function listFavorites() {
  return request({ url: '/api/mp/favorites' }).then(function (res) {
    return (res.data && res.data.favorites) || []
  })
}

function checkFavorite(stockCode) {
  return request({
    url: '/api/mp/favorites/check/' + encodeURIComponent(stockCode),
  }).then(function (res) {
    return !!(res.data && res.data.is_favorite)
  })
}

function addFavorite(data) {
  return request({
    url: '/api/mp/favorites',
    method: 'POST',
    data: data || {},
  }).then(function (res) {
    return (res.data && res.data.favorites) || []
  })
}

function removeFavorite(stockCode) {
  return request({
    url: '/api/mp/favorites/' + encodeURIComponent(stockCode),
    method: 'DELETE',
  })
}

function listLatestNews(params) {
  var q = []
  params = params || {}
  if (params.hours) q.push('hours=' + params.hours)
  if (params.limit) q.push('limit=' + params.limit)
  if (params.skip) q.push('skip=' + params.skip)
  if (params.favorites_first === false) q.push('favorites_first=false')
  var qs = q.length ? '?' + q.join('&') : ''
  return request({ url: '/api/mp/news/latest' + qs }).then(function (res) {
    return res.data || {}
  })
}

module.exports = {

  request,

  login,

  miniprogramLogin,

  getMe,

  updateMe,

  uploadAvatar,

  downloadImage,

  applyAvatarDisplay,

  listChatStrategies,

  listChatSessions,

  createChatSession,

  listChatMessages,

  askInSession,

  askInSessionStream,

  canAskStream,

  formatAskProgress,

  getFollowUpSuggestions,

  listMembershipLevels,

  changeMembership,

  getNotificationUnreadCount,

  listNotifications,

  markNotificationRead,

  markAllNotificationsRead,

  createRiskMessage,

  listRiskMessages,

  searchStocks,

  getStockQuote,

  getStockKline,

  listFavorites,

  checkFavorite,

  addFavorite,

  removeFavorite,

  listLatestNews,

  checkServer,

  buildImageUrl,

  BASE_URL,

  DEV_LOGIN_CODE,

}



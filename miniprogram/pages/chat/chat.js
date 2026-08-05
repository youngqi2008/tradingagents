var api = require('../../utils/api')
var auth = require('../../utils/auth')
var { syncTabBar } = require('../../utils/tabbar')

Page({
  data: {
    isLoggedIn: false,
    sessionId: '',
    sessions: [],
    currentSessionTitle: '新会话',
    showSessions: false,
    strategies: [],
    strategyNames: [],
    strategyIndex: 0,
    messages: [],
    inputText: '',
    sending: false,
    progressStatus: '',
    scrollIntoView: '',
    userQuota: null,
    quickPrompts: [
      '分析 600519 走势',
      '000001 值得投资吗',
      '今日市场怎么看',
      '帮我选股思路',
    ],
    followUpSuggestions: [],
    waitTip: '智能问股通常需要 1–5 分钟。分析期间可先离开，完成后回本页即可查看结果。',
  },

  onShow() {
    this._pageActive = true
    syncTabBar(this)
    var loggedIn = auth.isLoggedIn()
    this.safeSetData({ isLoggedIn: loggedIn })
    if (!loggedIn) return
    this.loadUserQuota()
    if (this._askRunning || this._needsRefreshOnShow) {
      this.resumeAfterLeave()
      return
    }
    var jump = null
    try {
      jump = wx.getStorageSync('chat_jump') || null
      if (jump) wx.removeStorageSync('chat_jump')
    } catch (e) {
      jump = null
    }
    if (jump && jump.stock_code) {
      this.bootstrapWithJump(jump)
      return
    }
    this.bootstrap()
  },

  onHide() {
    this._pageActive = false
    // 不 abort：后台继续生成，用户可切到其他 Tab
    try { wx.hideLoading() } catch (e) {}
    this.safeSetData({ showSessions: false })
  },

  onUnload() {
    this._pageActive = false
    this.stopMessagePoll()
    // 仅页面卸载时断开，避免泄漏
    if (this._askTask && this._askTask.abort) this._askTask.abort()
  },

  safeSetData(payload, callback) {
    // 页面隐藏时仍允许更新关键状态（sending 等），保证回来时 UI 正确
    if (!this._pageActive) {
      var keys = Object.keys(payload || {})
      var allowWhileHidden = false
      for (var i = 0; i < keys.length; i++) {
        if (keys[i] === 'sending' || keys[i] === 'progressStatus' || keys[i] === 'messages' || keys[i] === 'followUpSuggestions' || keys[i] === 'userQuota') {
          allowWhileHidden = true
          break
        }
      }
      if (!allowWhileHidden) return
    }
    this.setData(payload, callback)
  },

  onLoginTap() {
    var self = this
    wx.showLoading({ title: '登录中...' })
    api.login({})
      .then(function (result) {
        wx.hideLoading()
        wx.showToast({ title: '登录成功', icon: 'success' })
        self.safeSetData({ isLoggedIn: true })
        self.loadUserQuota()
        self.bootstrap()
        auth.promptProfileSetupIfNeeded(result && result.user)
      })
      .catch(function (e) {
        wx.hideLoading()
        wx.showToast({ title: (e && e.message) || '登录失败', icon: 'none' })
      })
  },

  loadUserQuota() {
    var self = this
    api.getMe()
      .then(function (u) {
        if (!u || !self._pageActive) return
        self.safeSetData({
          userQuota: {
            balance: u.balance || 0,
            ask_free_remaining: u.ask_free_remaining || 0,
            ask_free_limit: u.ask_free_limit || 0,
          },
        })
      })
      .catch(function () {})
  },

  bootstrap() {
    var self = this
    Promise.all([api.listChatStrategies(), api.listChatSessions()])
      .then(function (results) {
        if (!self._pageActive) return
        var strategies = results[0] || []
        var sessions = results[1] || []
        var names = strategies.map(function (s) { return s.name })
        self.safeSetData({
          strategies: strategies,
          strategyNames: names,
          strategyIndex: 0,
          sessions: sessions,
        })
        if (sessions.length > 0) {
          return self.openSession(sessions[0].session_id, sessions[0])
        }
        return api.createChatSession({ strategy_id: (strategies[0] && strategies[0].id) || 'bull_trend' })
          .then(function (session) {
            if (!self._pageActive) return
            return self.openSession(session.session_id, session)
          })
      })
      .catch(function (e) {
        if (!self._pageActive) return
        wx.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
      })
  },

  bootstrapWithJump(jump) {
    var self = this
    var code = String(jump.stock_code || '').trim()
    var message = jump.message || (code + ' 请帮我分析')
    var strategyId = jump.strategy_id || ''
    wx.showLoading({ title: '准备问股…' })
    Promise.all([api.listChatStrategies(), api.listChatSessions()])
      .then(function (results) {
        if (!self._pageActive) return
        var strategies = results[0] || []
        var sessions = results[1] || []
        var names = strategies.map(function (s) { return s.name })
        var strategyIndex = 0
        if (strategyId) {
          for (var i = 0; i < strategies.length; i++) {
            if (strategies[i].id === strategyId) {
              strategyIndex = i
              break
            }
          }
        }
        var sid = strategyId || (strategies[0] && strategies[0].id) || 'bull_trend'
        self.safeSetData({
          strategies: strategies,
          strategyNames: names,
          strategyIndex: strategyIndex,
          sessions: sessions,
          inputText: message,
          followUpSuggestions: [],
        })
        return api.createChatSession({
          stock_code: code,
          title: '问股 ' + code,
          strategy_id: sid,
        }).then(function (session) {
          if (!self._pageActive) return
          return api.listChatSessions().then(function (freshSessions) {
            self.safeSetData({ sessions: freshSessions || [] })
            return self.openSession(session.session_id, session).then(function () {
              self.setData({ inputText: message })
              wx.hideLoading()
              wx.showToast({
                title: '已预填问股内容',
                icon: 'none',
                duration: 2000,
              })
              if (jump.auto_send) {
                setTimeout(function () {
                  if (self._pageActive) self.onSend()
                }, 400)
              }
            })
          })
        })
      })
      .catch(function (e) {
        wx.hideLoading()
        if (!self._pageActive) return
        wx.showToast({ title: (e && e.message) || '打开问股失败', icon: 'none' })
        self.bootstrap()
      })
  },

  sessionTitle(session) {
    if (!session) return '新会话'
    return session.title || session.stock_code || '问股会话'
  },

  openSession(sessionId, sessionMeta) {
    var self = this
    var title = this.sessionTitle(sessionMeta)
    return api.listChatMessages(sessionId).then(function (messages) {
      if (!self._pageActive) return
      self.safeSetData({
        sessionId: sessionId,
        messages: messages || [],
        currentSessionTitle: title,
        showSessions: false,
        followUpSuggestions: [],
      })
      self.scrollToBottom()
      return self.loadFollowUpSuggestions(sessionId)
    })
  },

  loadFollowUpSuggestions(sessionId) {
    var self = this
    if (!sessionId) return Promise.resolve()
    return api.getFollowUpSuggestions(sessionId)
      .then(function (suggestions) {
        if (!self._pageActive || self.data.sessionId !== sessionId) return
        self.safeSetData({ followUpSuggestions: suggestions || [] })
      })
      .catch(function () {})
  },

  toggleSessions() {
    this.setData({ showSessions: !this.data.showSessions })
  },

  onSelectSession(e) {
    var id = e.currentTarget.dataset.id
    var session = this.data.sessions.find(function (s) {
      return s.session_id === id
    })
    this.openSession(id, session)
  },

  onStrategyChange(e) {
    this.setData({ strategyIndex: Number(e.detail.value) || 0 })
  },

  onNewSession() {
    this.createNewSession()
  },

  onNewSessionFromDrawer() {
    this.createNewSession()
  },

  createNewSession() {
    var self = this
    var strategy = this.data.strategies[this.data.strategyIndex]
    api.createChatSession({ strategy_id: (strategy && strategy.id) || 'bull_trend' })
      .then(function (session) {
        if (!self._pageActive) return
        return api.listChatSessions().then(function (sessions) {
          self.safeSetData({
            sessionId: session.session_id,
            messages: [],
            inputText: '',
            sessions: sessions || [],
            currentSessionTitle: '新会话',
            showSessions: false,
            followUpSuggestions: [],
          })
          wx.showToast({ title: '新会话', icon: 'success' })
        })
      })
      .catch(function (e) {
        wx.showToast({ title: (e && e.message) || '创建失败', icon: 'none' })
      })
  },

  onQuickPrompt(e) {
    var text = e.currentTarget.dataset.text
    if (text) {
      this.setData({ inputText: text })
      this.onSend()
    }
  },

  onFollowUpTap(e) {
    var text = e.currentTarget.dataset.text
    if (!text || this.data.sending) return
    this.setData({ inputText: text })
    this.onSend()
  },

  onInput(e) {
    this.setData({ inputText: e.detail.value })
  },

  onClearInput() {
    if (this.data.sending) return
    this.setData({ inputText: '' })
  },

  hasMessageId(messages, id) {
    if (!id) return false
    return (messages || []).some(function (m) { return m.id === id })
  },

  stopMessagePoll() {
    if (this._messagePollTimer) {
      clearInterval(this._messagePollTimer)
      this._messagePollTimer = null
    }
  },

  startMessagePoll() {
    var self = this
    if (this._messagePollTimer) return
    this._messagePollTimer = setInterval(function () {
      self.refreshMessagesWhileAsking()
    }, 5000)
  },

  goHomeWhileAsking() {
    try { wx.hideLoading() } catch (e) {}
    wx.showToast({
      title: '分析继续进行中',
      icon: 'none',
      duration: 2000,
    })
    setTimeout(function () {
      wx.switchTab({ url: '/pages/kline/kline' })
    }, 350)
  },

  resumeAfterLeave() {
    var self = this
    this._needsRefreshOnShow = false
    this.loadUserQuota()
    var sessionId = this.data.sessionId
    if (!sessionId) {
      this.bootstrap()
      return
    }
    api.listChatMessages(sessionId)
      .then(function (messages) {
        messages = messages || []
        var done = self.isAskCompletedInMessages(messages)
        if (done) {
          self._askRunning = false
          self.stopMessagePoll()
          self.setData({
            messages: messages,
            sending: false,
            progressStatus: '',
          })
          self.loadFollowUpSuggestions(sessionId)
          self.scrollToBottom()
          if (self._pendingDoneToast) {
            self._pendingDoneToast = false
            wx.showToast({ title: '问股分析已完成', icon: 'success' })
          }
          return
        }
        if (self._askRunning || self.data.sending) {
          self.setData({
            messages: messages,
            sending: true,
            progressStatus: self.data.progressStatus || '分析仍在进行，请稍候…',
          })
          self.startMessagePoll()
          self.scrollToBottom()
          return
        }
        self.setData({ messages: messages })
        self.loadFollowUpSuggestions(sessionId)
      })
      .catch(function () {
        if (!self.data.sessions || !self.data.sessions.length) self.bootstrap()
      })
  },

  isAskCompletedInMessages(messages) {
    if (!messages || !messages.length) return false
    var last = messages[messages.length - 1]
    if (!last || last.role !== 'assistant') return false
    // 若本地还记着待发送的用户问题，确认其后已有助手回复
    if (this._pendingUserText) {
      for (var i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'user' && messages[i].content === this._pendingUserText) {
          return i < messages.length - 1 && messages[messages.length - 1].role === 'assistant'
        }
      }
    }
    return last.status !== 'failed'
  },

  refreshMessagesWhileAsking() {
    var self = this
    var sessionId = this.data.sessionId
    if (!sessionId || !this._askRunning) {
      this.stopMessagePoll()
      return
    }
    api.listChatMessages(sessionId)
      .then(function (messages) {
        messages = messages || []
        if (self.isAskCompletedInMessages(messages)) {
          self._askRunning = false
          self.stopMessagePoll()
          self.setData({
            messages: messages,
            sending: false,
            progressStatus: '',
          })
          self.loadFollowUpSuggestions(sessionId)
          self.scrollToBottom()
          if (self._pageActive) {
            wx.showToast({ title: '问股分析已完成', icon: 'success' })
          } else {
            self._pendingDoneToast = true
            self._needsRefreshOnShow = true
          }
          return
        }
        if (self._pageActive) {
          self.setData({ messages: messages })
        }
      })
      .catch(function () {})
  },

  handleAskError(self, text, err) {
    try { wx.hideLoading() } catch (e) {}
    self._askRunning = false
    self.stopMessagePoll()
    // 主动离开导致的中断不打扰用户
    var errMsg = (err && err.message) || '发送失败'
    if (!self._pageActive && (errMsg.indexOf('abort') >= 0 || errMsg.indexOf('fail') >= 0)) {
      self._needsRefreshOnShow = true
      return
    }
    self.setData({ sending: false, progressStatus: '', inputText: text || self.data.inputText })
    if (err && err.statusCode === 402) return
    if (errMsg.indexOf('超时') >= 0) {
      wx.showModal({
        title: '分析超时',
        content: errMsg + '\n\n可稍后回到本会话查看是否已生成结果。',
        showCancel: false,
        confirmText: '知道了',
      })
      return
    }
    if (self._pageActive) {
      wx.showToast({ title: errMsg, icon: 'none' })
    } else {
      self._needsRefreshOnShow = true
    }
  },

  handleAskDone(self, data) {
    try { wx.hideLoading() } catch (e) {}
    self._askRunning = false
    self.stopMessagePoll()
    self._pendingUserText = ''
    var messages = (self.data.messages || []).slice()
    if (data.message && !self.hasMessageId(messages, data.message.id)) {
      messages.push(data.message)
    }
    if (data.reply && !self.hasMessageId(messages, data.reply.id)) {
      messages.push(data.reply)
    }
    self.setData({
      messages: messages,
      sending: false,
      progressStatus: '',
      followUpSuggestions: data.follow_up_suggestions || [],
    })
    self.loadUserQuota()
    if (self._pageActive) {
      self.scrollToBottom()
    } else {
      self._pendingDoneToast = true
      self._needsRefreshOnShow = true
    }
  },

  onSend() {
    if (this.data.sending) return
    var text = (this.data.inputText || '').trim()
    if (!text) return
    if (!this.data.sessionId) {
      wx.showToast({ title: '会话未就绪', icon: 'none' })
      return
    }
    var self = this
    var strategy = this.data.strategies[this.data.strategyIndex]
    var strategyId = strategy && strategy.id
    if (this._askTask && this._askTask.abort) this._askTask.abort()
    this._askRunning = true
    this._pendingUserText = text
    this._pendingDoneToast = false
    this.setData({
      sending: true,
      inputText: '',
      followUpSuggestions: [],
      progressStatus: '连接中…',
    })
    // 不用 mask，避免挡住用户切 Tab / 离开
    wx.showToast({ title: '分析开始，约需 1–5 分钟', icon: 'none', duration: 2500 })

    if (api.canAskStream && api.canAskStream()) {
      this._askTask = api.askInSessionStream(this.data.sessionId, text, strategyId, {
        onUserMessage: function (data) {
          var messages = (self.data.messages || []).slice()
          if (data.message && !self.hasMessageId(messages, data.message.id)) {
            messages.push(data.message)
            self.setData({ messages: messages, progressStatus: '已收到问题，开始分析…' })
            if (self._pageActive) self.scrollToBottom()
          }
        },
        onProgress: function (data) {
          self.setData({ progressStatus: api.formatAskProgress(data) })
        },
        onDone: function (data) {
          self.handleAskDone(self, data)
        },
        onError: function (err) {
          self.handleAskError(self, text, err)
        },
      })
      this.startMessagePoll()
      return
    }

    api.askInSession(this.data.sessionId, text, strategyId)
      .then(function (data) {
        self.handleAskDone(self, data)
      })
      .catch(function (e) {
        self.handleAskError(self, text, e)
      })
    this.startMessagePoll()
  },

  scrollToBottom() {
    if (!this._pageActive) return
    var self = this
    this.safeSetData({ scrollIntoView: '' })
    wx.nextTick(function () {
      if (!self._pageActive) return
      var messages = self.data.messages || []
      if (messages.length) {
        var last = messages[messages.length - 1]
        if (last && last.id) {
          self.safeSetData({ scrollIntoView: 'msg-' + last.id })
          return
        }
      }
      self.safeSetData({ scrollIntoView: 'scroll-bottom' })
    })
  },
})

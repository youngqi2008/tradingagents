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
  },

  onShow() {
    this._pageActive = true
    syncTabBar(this)
    var loggedIn = auth.isLoggedIn()
    this.safeSetData({ isLoggedIn: loggedIn })
    if (!loggedIn) return
    this.loadUserQuota()
    this.bootstrap()
  },

  onHide() {
    this._pageActive = false
    if (this._askTask && this._askTask.abort) this._askTask.abort()
    this.safeSetData({ showSessions: false })
  },

  onUnload() {
    this._pageActive = false
    if (this._askTask && this._askTask.abort) this._askTask.abort()
  },

  safeSetData(payload, callback) {
    if (!this._pageActive) return
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

  hasMessageId(messages, id) {
    if (!id) return false
    return (messages || []).some(function (m) { return m.id === id })
  },

  handleAskError(self, text, err) {
    wx.hideLoading()
    if (!self._pageActive) return
    self.safeSetData({ sending: false, progressStatus: '', inputText: text })
    if (err && err.statusCode === 402) return
    var errMsg = (err && err.message) || '发送失败'
    if (errMsg.indexOf('超时') >= 0) {
      wx.showModal({
        title: '分析超时',
        content: errMsg,
        showCancel: false,
        confirmText: '知道了',
      })
      return
    }
    wx.showToast({ title: errMsg, icon: 'none' })
  },

  handleAskDone(self, data) {
    wx.hideLoading()
    if (!self._pageActive) return
    var messages = (self.data.messages || []).slice()
    if (data.message && !self.hasMessageId(messages, data.message.id)) {
      messages.push(data.message)
    }
    if (data.reply) messages.push(data.reply)
    self.safeSetData({
      messages: messages,
      sending: false,
      progressStatus: '',
      followUpSuggestions: data.follow_up_suggestions || [],
    })
    self.loadUserQuota()
    self.scrollToBottom()
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
    this.safeSetData({
      sending: true,
      inputText: '',
      followUpSuggestions: [],
      progressStatus: '连接中…',
    })
    wx.showLoading({ title: 'AI 分析中…', mask: true })

    if (api.canAskStream && api.canAskStream()) {
      this._askTask = api.askInSessionStream(this.data.sessionId, text, strategyId, {
        onUserMessage: function (data) {
          if (!self._pageActive) return
          var messages = (self.data.messages || []).slice()
          if (data.message && !self.hasMessageId(messages, data.message.id)) {
            messages.push(data.message)
            self.safeSetData({ messages: messages, progressStatus: '已收到问题，开始分析…' })
            self.scrollToBottom()
          }
        },
        onProgress: function (data) {
          if (!self._pageActive) return
          self.safeSetData({ progressStatus: api.formatAskProgress(data) })
        },
        onDone: function (data) {
          self.handleAskDone(self, data)
        },
        onError: function (err) {
          self.handleAskError(self, text, err)
        },
      })
      return
    }

    api.askInSession(this.data.sessionId, text, strategyId)
      .then(function (data) {
        self.handleAskDone(self, data)
      })
      .catch(function (e) {
        self.handleAskError(self, text, e)
      })
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

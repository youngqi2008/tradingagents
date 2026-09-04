const { request, login } = require('../../utils/api')

function compareVersion(v1, v2) {
  if (typeof v1 !== 'string' || typeof v2 !== 'string') return 0
  const a = v1.split('.')
  const b = v2.split('.')
  const len = Math.max(a.length, b.length)
  while (a.length < len) a.push('0')
  while (b.length < len) b.push('0')
  for (let i = 0; i < len; i++) {
    const n1 = parseInt(a[i], 10)
    const n2 = parseInt(b[i], 10)
    if (n1 > n2) return 1
    if (n1 < n2) return -1
  }
  return 0
}

function canUseVirtualPayment() {
  const sdk = (wx.getSystemInfoSync() || {}).SDKVersion || '0'
  return compareVersion(sdk, '2.19.2') >= 0 || wx.canIUse('requestVirtualPayment')
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

Page({
  data: {
    amounts: [10, 30, 50, 100, 200],
    selected: 50,
    custom: false,
    customAmount: '',
    minAmount: 1,
    maxAmount: 5000,
    paying: false,
    payAmount: 50,
    coinRatio: 1,
  },

  onLoad() {
    request({ url: '/api/mp/payment/recharge-options' }).then((res) => {
      if (!res.success || !res.data) return
      const amounts = res.data.amounts && res.data.amounts.length ? res.data.amounts : this.data.amounts
      const minAmount = Number(res.data.min_amount) || 1
      const maxAmount = Number(res.data.max_amount) || 5000
      const selected = amounts[1] || amounts[0]
      this.setData({
        amounts,
        selected,
        minAmount,
        maxAmount,
        payAmount: selected,
        coinRatio: Number(res.data.coin_ratio) || 1,
      })
    })
  },

  selectAmount(e) {
    const selected = Number(e.currentTarget.dataset.amount)
    this.setData({ custom: false, selected, customAmount: '', payAmount: selected })
  },

  selectCustom() {
    this.setData({ custom: true, selected: 0, payAmount: this._parseCustom(this.data.customAmount) || '' })
  },

  onCustomInput(e) {
    const customAmount = e.detail.value
    this.setData({ customAmount, payAmount: this._parseCustom(customAmount) || '' })
  },

  _parseCustom(raw) {
    const n = Number(String(raw || '').trim())
    if (!Number.isFinite(n) || n <= 0) return 0
    return Math.round(n)
  },

  _resolveAmount() {
    const { custom, selected, customAmount, minAmount, maxAmount } = this.data
    const amount = custom ? this._parseCustom(customAmount) : Number(selected)
    if (!amount) {
      wx.showToast({ title: '请输入充值金额', icon: 'none' })
      return null
    }
    if (amount < minAmount || amount > maxAmount) {
      wx.showToast({ title: `金额须为 ${minAmount}～${maxAmount} 的整数元`, icon: 'none' })
      return null
    }
    return amount
  },

  async pay() {
    const amount = this._resolveAmount()
    if (!amount) return
    if (!canUseVirtualPayment()) {
      wx.showToast({ title: '请升级微信后再支付', icon: 'none' })
      return
    }

    this.setData({ paying: true })
    try {
      await this._payOnce(amount, false)
    } catch (e) {
      const msg = (e && e.message) || '充值失败'
      if (msg.indexOf('重新登录') >= 0 || msg.indexOf('session') >= 0) {
        try {
          await login({})
          await this._payOnce(amount, true)
          return
        } catch (e2) {
          wx.showToast({ title: (e2 && e2.message) || '充值失败', icon: 'none' })
          return
        }
      }
      wx.showToast({ title: msg, icon: 'none' })
    } finally {
      this.setData({ paying: false })
    }
  },

  async _payOnce(amount) {
    const res = await request({
      url: '/api/mp/payment/recharge',
      method: 'POST',
      data: { amount },
    })
    if (!res.success) throw new Error(res.message || '下单失败')

    const data = res.data || {}
    if (data.mock) {
      wx.showToast({ title: '充值成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1500)
      return
    }

    const p = data.pay_params
    if (!p || !p.signData) throw new Error('未返回虚拟支付参数')

    await this._requestVirtualPay(p)
    const paid = await this._pollPaid(data.order_no)
    wx.showToast({
      title: paid ? '充值成功' : '支付成功，余额稍后到账',
      icon: paid ? 'success' : 'none',
    })
    setTimeout(() => wx.navigateBack(), 1500)
  },

  _requestVirtualPay(p) {
    return new Promise((resolve, reject) => {
      wx.requestVirtualPayment({
        signData: p.signData,
        paySig: p.paySig,
        signature: p.signature,
        mode: p.mode || 'short_series_coin',
        success: () => resolve(),
        fail: (err) => {
          const code = err && (err.errCode != null ? err.errCode : err.errno)
          const msg = (err && err.errMsg) || ''
          if (code === -2 || msg.indexOf('cancel') >= 0) {
            reject(new Error('支付取消'))
            return
          }
          if (code === -15007) {
            reject(new Error('登录态已失效，请重新登录后再支付'))
            return
          }
          reject(new Error(msg || `支付失败(${code || ''})`))
        },
      })
    })
  },

  async _pollPaid(orderNo) {
    for (let i = 0; i < 8; i++) {
      await sleep(1500)
      try {
        const res = await request({
          url: '/api/mp/payment/recharge/confirm',
          method: 'POST',
          data: { order_no: orderNo },
        })
        if (res.success && res.data && res.data.status === 'paid') return true
      } catch (e) {}
    }
    return false
  },
})

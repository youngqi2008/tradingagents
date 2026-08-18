const { request } = require('../../utils/api')

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
  },

  onLoad() {
    request({ url: '/api/mp/payment/recharge-options' }).then((res) => {
      if (!res.success || !res.data) return
      const amounts = res.data.amounts?.length ? res.data.amounts : this.data.amounts
      const minAmount = Number(res.data.min_amount) || 1
      const maxAmount = Number(res.data.max_amount) || 5000
      const selected = amounts[1] || amounts[0]
      this.setData({ amounts, selected, minAmount, maxAmount, payAmount: selected })
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
    return Math.round(n * 100) / 100
  },

  _resolveAmount() {
    const { custom, selected, customAmount, minAmount, maxAmount } = this.data
    const amount = custom ? this._parseCustom(customAmount) : Number(selected)
    if (!amount) {
      wx.showToast({ title: '请输入充值金额', icon: 'none' })
      return null
    }
    if (amount < minAmount || amount > maxAmount) {
      wx.showToast({ title: `金额须在 ${minAmount}～${maxAmount} 元`, icon: 'none' })
      return null
    }
    return amount
  },

  async pay() {
    const amount = this._resolveAmount()
    if (!amount) return

    this.setData({ paying: true })
    try {
      const res = await request({
        url: '/api/mp/payment/recharge',
        method: 'POST',
        data: { amount },
      })
      if (!res.success) throw new Error(res.message)

      const data = res.data
      if (data.mock) {
        wx.showToast({ title: '充值成功', icon: 'success' })
        setTimeout(() => wx.navigateBack(), 1500)
        return
      }

      const p = data.pay_params
      wx.requestPayment({
        timeStamp: p.timeStamp,
        nonceStr: p.nonceStr,
        package: p.package,
        signType: p.signType,
        paySign: p.paySign,
        success: () => {
          wx.showToast({ title: '充值成功', icon: 'success' })
          setTimeout(() => wx.navigateBack(), 1500)
        },
        fail: () => wx.showToast({ title: '支付取消', icon: 'none' }),
      })
    } catch (e) {
      wx.showToast({ title: e.message || '充值失败', icon: 'none' })
    } finally {
      this.setData({ paying: false })
    }
  },
})

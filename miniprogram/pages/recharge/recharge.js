const { request } = require('../../utils/api')

Page({
  data: { amounts: [10, 30, 50, 100, 200], selected: 50, paying: false },

  onLoad() {
    request({ url: '/api/mp/payment/recharge-options' }).then((res) => {
      if (res.success && res.data.amounts?.length) {
        this.setData({ amounts: res.data.amounts, selected: res.data.amounts[1] || res.data.amounts[0] })
      }
    })
  },

  selectAmount(e) {
    this.setData({ selected: Number(e.currentTarget.dataset.amount) })
  },

  async pay() {
    this.setData({ paying: true })
    try {
      const res = await request({
        url: '/api/mp/payment/recharge',
        method: 'POST',
        data: { amount: this.data.selected },
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

/** 提审展示用：弱化证券/行情相关用词，不改变业务数据。 */

function softenCopy(text) {
  var s = String(text || '')
  s = s.replace(/不关注信号/g, '服务更新')
  s = s.replace(/关注信号/g, '服务动态')
  s = s.replace(/大盘复盘/g, '服务摘要')
  s = s.replace(/复盘/g, '摘要')
  s = s.replace(/股票代码/g, '编号')
  s = s.replace(/股票/g, '项目')
  s = s.replace(/证券/g, '项目')
  s = s.replace(/期货/g, '项目')
  s = s.replace(/行情/g, '动态')
  s = s.replace(/\[取消关注\]/g, '[更新]')
  s = s.replace(/\[关注\]/g, '[订阅]')
  s = s.replace(/市场:\s*/g, '分类: ')
  return s
}

module.exports = {
  softenCopy,
}

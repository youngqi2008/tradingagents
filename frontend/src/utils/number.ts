/**
 * 数字格式化工具函数
 * 安全地处理各种数字类型，避免 toFixed 错误
 */

/**
 * 安全地将值转换为数字
 */
export function safeNumber(value: any): number {
  if (value === null || value === undefined || value === '') {
    return 0
  }
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

/**
 * 安全地格式化数字为固定小数位
 * @param value 要格式化的值
 * @param decimals 小数位数，默认2位
 * @param fallback 当值无效时的回退值，默认 '-'
 */
export function safeToFixed(value: any, decimals: number = 2, fallback: string = '-'): string {
  if (value === null || value === undefined || value === '') {
    return fallback
  }
  
  const num = Number(value)
  if (!Number.isFinite(num)) {
    return fallback
  }
  
  try {
    return num.toFixed(decimals)
  } catch (error) {
    console.warn('toFixed error:', error, 'value:', value)
    return fallback
  }
}

/**
 * 格式化价格（2位小数）
 */
export function formatPrice(value: any): string {
  return safeToFixed(value, 2, '-')
}

/**
 * 格式化百分比（2位小数，带符号）
 */
export function formatPercent(value: any, showSign: boolean = true): string {
  const num = safeNumber(value)
  if (num === 0) return '0%'
  
  const formatted = safeToFixed(num, 2, '-')
  if (formatted === '-') return '-'
  
  const sign = showSign && num > 0 ? '+' : ''
  return `${sign}${formatted}%`
}

/**
 * 格式化百分比（1位小数，带符号）
 */
export function formatPercent1(value: any, showSign: boolean = true): string {
  const num = safeNumber(value)
  if (num === 0) return '0%'
  
  const formatted = safeToFixed(num, 1, '-')
  if (formatted === '-') return '-'
  
  const sign = showSign && num > 0 ? '+' : ''
  return `${sign}${formatted}%`
}

/**
 * 格式化金额（带千分位）
 */
export function formatMoney(value: any, decimals: number = 2): string {
  const num = safeNumber(value)
  if (num === 0) return '0'
  
  const formatted = safeToFixed(num, decimals, '-')
  if (formatted === '-') return '-'
  
  return formatted.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

/**
 * 格式化大数字（万、亿单位）
 */
export function formatLargeNumber(value: any): string {
  const num = safeNumber(value)
  if (num === 0) return '0'
  
  if (num >= 1e12) {
    return safeToFixed(num / 1e12, 2) + '万亿'
  }
  if (num >= 1e8) {
    return safeToFixed(num / 1e8, 2) + '亿'
  }
  if (num >= 1e4) {
    return safeToFixed(num / 1e4, 2) + '万'
  }
  return safeToFixed(num, 0)
}

/**
 * 格式化成交量（万股、亿股）
 */
export function formatVolume(value: any): string {
  const num = safeNumber(value)
  if (num === 0) return '0股'
  
  if (num >= 1e8) {
    return safeToFixed(num / 1e8, 2) + '亿股'
  }
  if (num >= 1e4) {
    return safeToFixed(num / 1e4, 2) + '万股'
  }
  return safeToFixed(num, 0) + '股'
}

/**
 * 格式化市值
 */
export function formatMarketCap(value: any): string {
  const num = safeNumber(value)
  if (num === 0) return '-'
  
  if (num >= 1e12) {
    return safeToFixed(num / 1e12, 2) + '万亿'
  }
  if (num >= 1e8) {
    return safeToFixed(num / 1e8, 2) + '亿'
  }
  return safeToFixed(num, 2) + '万'
}

/**
 * 格式化数字（K、M单位）
 */
export function formatNumber(value: any): string {
  const num = safeNumber(value)
  if (num === 0) return '0'
  
  if (num >= 1000000) {
    return safeToFixed(num / 1000000, 1) + 'M'
  }
  if (num >= 1000) {
    return safeToFixed(num / 1000, 1) + 'K'
  }
  return safeToFixed(num, 2)
}

/**
 * 格式化变化率（带符号和颜色类）
 */
export function formatChange(value: any): { text: string; class: string } {
  const num = safeNumber(value)
  
  if (num > 0) {
    return {
      text: `+${safeToFixed(num, 2)}%`,
      class: 'text-up'
    }
  }
  if (num < 0) {
    return {
      text: `${safeToFixed(num, 2)}%`,
      class: 'text-down'
    }
  }
  return {
    text: '0%',
    class: ''
  }
}

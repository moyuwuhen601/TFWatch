export const states = {
  open: '开放中', full: '已满员', closed: '已关闭', unknown: '未知',
}

const dateTime = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  hourCycle: 'h23',
})

const shortDate = new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' })

export function dateLabel(value, short = false) {
  return value == null ? '—' : (short ? shortDate : dateTime).format(value * 1000)
}

export function durationLabel(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return '< 1 分钟'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor(seconds / 60) % 60
  return [hours ? hours + ' 小时' : '', minutes ? minutes + ' 分钟' : ''].filter(Boolean).join(' ')
}

export function iconLetter(name) {
  return [...name.trim()][0]?.toUpperCase() || 'T'
}

/**
 * 관리자 화면 표시용 포맷터.
 *
 * 같은 값이 KPI 타일 · 표 · 툴팁 세 군데에 나오는데, 각자 포맷하면 '1시간 20분' 과
 * '80분' 이 한 화면에 같이 뜬다. 그래서 표기는 전부 여기를 거친다.
 */

const MINUTE = 60_000
const HOUR = 60 * MINUTE

/** 1234 → '1,234' */
export function formatCount(value: number): string {
  return Math.round(value).toLocaleString('ko-KR')
}

/** 0.734 → '73%' */
export function formatPercent(ratio: number, digits = 0): string {
  return `${(ratio * 100).toFixed(digits)}%`
}

/** 1.85 → '1.9' — 소수 한 자리 지표(팀당 대여 수 등) */
export function formatDecimal(value: number, digits = 1): string {
  return value.toFixed(digits)
}

/**
 * 분 단위 길이를 사람이 읽는 형태로. 값이 없으면 '—' 를 준다 —
 * 0 으로 표시하면 '평균 0분' 처럼 사실이 아닌 말이 된다.
 */
export function formatDuration(minutes: number | null): string {
  if (minutes === null || Number.isNaN(minutes)) return '—'
  const rounded = Math.round(minutes)
  if (rounded < 60) return `${rounded}분`
  const hours = Math.floor(rounded / 60)
  const rest = rounded % 60
  return rest === 0 ? `${hours}시간` : `${hours}시간 ${rest}분`
}

/** 경과 시간(‘1:23:05’). 진행 중인 이용 시간처럼 초까지 흐르는 값에 쓴다. */
export function formatElapsed(from: number, now: number): string {
  const total = Math.max(0, Math.floor((now - from) / 1000))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${hours}:${pad(minutes)}:${pad(seconds)}`
}

/** '14:05' */
export function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

/** '8/3 14:05' — 오늘이면 시각만 준다 */
export function formatDateTime(timestamp: number, now = Date.now()): string {
  const date = new Date(timestamp)
  const today = new Date(now)
  const sameDay =
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  return sameDay
    ? formatTime(timestamp)
    : `${date.getMonth() + 1}/${date.getDate()} ${formatTime(timestamp)}`
}

/** '3분 전' — 목록에서 최신순 감각을 주는 상대 시각 */
export function formatAgo(timestamp: number | null, now: number): string {
  if (timestamp === null) return '기록 없음'
  const diff = now - timestamp
  if (diff < MINUTE) return '방금'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}분 전`
  if (diff < 24 * HOUR) return `${Math.floor(diff / HOUR)}시간 전`
  return `${Math.floor(diff / (24 * HOUR))}일 전`
}

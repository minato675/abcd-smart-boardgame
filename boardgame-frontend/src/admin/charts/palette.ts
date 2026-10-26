/**
 * 차트 색 배정.
 *
 * 값은 전부 CSS 변수라 다크 모드 전환이 공짜다(style.css 의 `--color-viz-*`).
 * 각 색이 하는 일은 하나뿐이고, 그 일에 맞는 함수를 통해서만 가져다 쓴다.
 *
 * - `seriesColor` — **식별**(어느 계열인가). 8슬롯 고정 순서, 9번째부터는 '기타'.
 * - `stepColor`   — **순서**(퍼널 단계, 난이도처럼 순서가 의미를 갖는 축척). 한 색상 계열의 명도 단계.
 * - 크기(막대 길이·선 높이)는 색이 아니라 기하로만 표현한다. 순서 없는 항목을
 *   값에 따라 진하게 칠하면 막대 길이가 이미 보여 주는 정보를 색으로 한 번 더
 *   칠하는 셈이라, 식별에 써야 할 유일한 채널을 낭비한다.
 *
 * 슬롯 **순서 자체가 색각 이상 안전성의 근거**다. 이 순서로 인접 쌍을 검증했으므로
 * 섞거나 값 순으로 배정하면 검증이 무효가 된다(색은 항목을 따라가야지 순위를 따라가면 안 된다).
 *
 * 라이트 모드에서 3·4·5번 슬롯은 흰 배경 대비 3:1 미만이다. 그 슬롯을 쓰는 차트는
 * 값을 눈으로 읽을 다른 길(직접 라벨 또는 ChartCard 의 '표로 보기')을 반드시 함께 준다.
 */

/** 계열 식별용 8색. 이 배열의 순서를 바꾸지 말 것. */
export const SERIES_COLORS = [
  'var(--color-viz-1)',
  'var(--color-viz-2)',
  'var(--color-viz-3)',
  'var(--color-viz-4)',
  'var(--color-viz-5)',
  'var(--color-viz-6)',
  'var(--color-viz-7)',
  'var(--color-viz-8)',
] as const

/** 9번째부터 접어 넣는 자리. 새 색을 만들지 않는다. */
export const OTHER_COLOR = 'var(--color-viz-other)'

/** 순서가 있는 축척(낮음 → 높음). */
export const STEP_COLORS = [
  'var(--color-viz-step-1)',
  'var(--color-viz-step-2)',
  'var(--color-viz-step-3)',
  'var(--color-viz-step-4)',
] as const

export const GRID_COLOR = 'var(--color-viz-grid)'
export const AXIS_COLOR = 'var(--color-viz-axis)'
/** 강조 대비용. 스파크라인의 지난 구간처럼 '배경 노릇' 하는 마크에만. */
export const MUTE_COLOR = 'var(--color-viz-mute)'
/** 마크 사이를 벌리는 2px 틈에 쓰는 색 — 테두리가 아니라 표면색이다. */
export const SURFACE_COLOR = 'var(--color-surface)'

/** 항목 순서(값 순위가 아니다)로 색을 배정한다. */
export function seriesColor(index: number): string {
  return SERIES_COLORS[index] ?? OTHER_COLOR
}

/**
 * 순서 축척의 n번째 색. 단계 수가 4를 넘으면 양 끝을 유지한 채 균등 배분한다
 * (중간 단계가 서로 붙어 보이면 애초에 단계를 줄여야 한다).
 */
export function stepColor(index: number, total: number): string {
  if (total <= 1) return STEP_COLORS[STEP_COLORS.length - 1] as string
  const position = Math.round((index / (total - 1)) * (STEP_COLORS.length - 1))
  return STEP_COLORS[position] as string
}

/** 축 눈금으로 쓸 '깔끔한' 최댓값 (7 → 8, 23 → 25, 118 → 120) */
export function niceMax(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const rounded = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10
  return rounded * magnitude
}

/** 0 을 포함한 4칸 눈금 */
export function ticksFor(max: number, count = 4): number[] {
  return Array.from({ length: count + 1 }, (_, index) => (max / count) * index)
}

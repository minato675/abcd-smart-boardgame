<script setup lang="ts">
/**
 * 차트 안에 뜨는 읽기용 말풍선.
 *
 * 값이 크고 계열 이름이 작다 — 범례와 일부러 반대다. 범례를 볼 때는 어떤 색이
 * 무엇인지 궁금하지만, 말풍선을 볼 때는 이미 계열을 알고 숫자를 원하기 때문이다.
 *
 * 툴팁은 값을 읽는 **유일한** 통로가 되면 안 된다 — 어떤 차트든 직접 라벨이나
 * ChartCard 의 '표로 보기' 로도 같은 값에 닿을 수 있어야 한다.
 *
 * 계열 이름은 게임 이름처럼 밖에서 온 문자열이라 항상 텍스트 보간으로만 넣는다.
 */

export interface TooltipRow {
  label: string
  value: string
  /** 있으면 계열 색 짧은 선을 앞에 붙인다 */
  color?: string
}

const props = withDefaults(
  defineProps<{
    /** 컨테이너 기준 좌표(px) */
    x: number
    y: number
    title: string
    rows: TooltipRow[]
    /** 컨테이너 너비 — 오른쪽 끝에서 말풍선이 잘리지 않게 접는 데 쓴다 */
    width: number
  }>(),
  {},
)

/** 오른쪽 절반에서는 왼쪽으로 펼친다 */
const flip = () => props.x > props.width * 0.6
</script>

<template>
  <div
    class="pointer-events-none absolute z-20 min-w-[132px] rounded-field border border-line-soft bg-surface px-3 py-2 shadow-[0_6px_24px_rgba(17,17,17,0.16)]"
    :style="{
      left: `${x}px`,
      top: `${y}px`,
      transform: `translate(${flip() ? 'calc(-100% - 12px)' : '12px'}, -50%)`,
    }"
    role="tooltip"
  >
    <p class="text-[11px] font-semibold text-subtle">{{ title }}</p>
    <ul class="mt-1.5 flex flex-col gap-1">
      <li
        v-for="row in rows"
        :key="row.label"
        class="flex items-baseline gap-2 whitespace-nowrap"
      >
        <span
          v-if="row.color"
          class="h-0.5 w-3 shrink-0 self-center rounded-full"
          :style="{ background: row.color }"
        />
        <strong class="text-[15px] font-bold text-ink tabular-nums">
          {{ row.value }}
        </strong>
        <span class="text-[11px] text-subtle">{{ row.label }}</span>
      </li>
    </ul>
  </div>
</template>

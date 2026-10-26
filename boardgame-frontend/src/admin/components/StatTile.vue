<script setup lang="ts">
/**
 * KPI 한 칸: 라벨 · 값 · (선택) 변화량 · (선택) 스파크라인.
 *
 * 값 하나를 보여 주려고 막대 하나짜리 차트를 그리지 않는다 — 숫자가 곧 차트다.
 *
 * 큰 숫자에는 tabular-nums 를 쓰지 않는다. 모든 자릿수를 '0' 폭에 맞추면
 * 큰 글자에서 '121' 같은 값이 헐거워 보인다(세로로 줄맞춤이 필요한 표에서만 쓴다).
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import Sparkline from '../charts/Sparkline.vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: string
    /** 값 뒤에 붙는 작은 단위 */
    unit?: string
    /** 값 밑 한 줄 설명 */
    hint?: string
    /** 직전 같은 기간 대비 변화율. null 이면 표시하지 않는다. */
    delta?: number | null
    /** 변화가 클수록 좋은 지표인지. 반칙 수처럼 적을수록 좋은 값은 false. */
    higherIsBetter?: boolean
    trend?: number[]
    /** 강조 타일(맨 앞의 헤드라인) */
    hero?: boolean
  }>(),
  { higherIsBetter: true, hero: false },
)

const deltaTone = computed(() => {
  if (props.delta === null || props.delta === undefined || props.delta === 0) {
    return 'text-subtle'
  }
  const good = props.delta > 0 === props.higherIsBetter
  return good ? 'text-ok' : 'text-danger'
})

const deltaText = computed(() => {
  if (props.delta === null || props.delta === undefined) return null
  const sign = props.delta > 0 ? '+' : ''
  return `${sign}${(props.delta * 100).toFixed(0)}%`
})
</script>

<template>
  <div
    class="flex min-w-0 flex-col justify-between rounded-card border border-line-soft bg-surface p-4"
  >
    <p class="truncate text-xs font-medium text-subtle">{{ label }}</p>

    <div class="mt-2 flex items-end justify-between gap-2">
      <div class="flex min-w-0 items-baseline gap-1">
        <strong
          class="truncate font-bold tracking-tight text-ink"
          :class="hero ? 'text-[40px] leading-none' : 'text-[26px] leading-none'"
        >
          {{ value }}
        </strong>
        <span v-if="unit" class="shrink-0 text-xs font-semibold text-subtle">
          {{ unit }}
        </span>
      </div>

      <Sparkline v-if="trend && trend.length > 1" :values="trend" />
    </div>

    <div class="mt-2 flex items-center gap-2">
      <span
        v-if="deltaText"
        class="flex items-center gap-1 text-[11px] font-bold"
        :class="deltaTone"
      >
        <AppIcon
          :name="(delta ?? 0) >= 0 ? 'trending-up' : 'trending-down'"
          :size="12"
          :stroke-width="2.2"
        />
        {{ deltaText }}
      </span>
      <span v-if="hint" class="truncate text-[11px] text-muted">{{ hint }}</span>
    </div>
  </div>
</template>

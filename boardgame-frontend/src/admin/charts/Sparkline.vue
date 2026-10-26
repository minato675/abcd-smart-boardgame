<script setup lang="ts">
/**
 * KPI 타일 안의 12점짜리 미니 추이.
 *
 * 축도 눈금도 라벨도 없다 — 모양만 전한다. 정확한 값은 타일의 숫자와
 * 대시보드의 추이 차트가 맡는다. 마지막 점만 점으로 찍어 '지금' 을 표시한다.
 */
import { computed } from 'vue'
import { MUTE_COLOR, SURFACE_COLOR } from './palette'

const props = withDefaults(
  defineProps<{
    values: number[]
    color?: string
    width?: number
    height?: number
  }>(),
  { color: MUTE_COLOR, width: 84, height: 26 },
)

const PAD = 4

const points = computed(() => {
  const values = props.values
  if (values.length === 0) return []
  const max = Math.max(...values)
  const min = Math.min(...values)
  const span = max - min || 1
  const stepX = (props.width - PAD * 2) / Math.max(1, values.length - 1)

  return values.map((value, index) => ({
    x: PAD + stepX * index,
    y: PAD + (props.height - PAD * 2) * (1 - (value - min) / span),
  }))
})

const path = computed(() =>
  points.value
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x} ${point.y}`)
    .join(' '),
)

const last = computed(() => points.value[points.value.length - 1] ?? null)
</script>

<template>
  <svg
    v-if="points.length > 1"
    :width="width"
    :height="height"
    aria-hidden="true"
    class="shrink-0"
  >
    <path
      :d="path"
      fill="none"
      :stroke="color"
      stroke-width="2"
      stroke-linejoin="round"
      stroke-linecap="round"
    />
    <circle
      v-if="last"
      :cx="last.x"
      :cy="last.y"
      r="3"
      :fill="color"
      :stroke="SURFACE_COLOR"
      stroke-width="2"
    />
  </svg>
</template>

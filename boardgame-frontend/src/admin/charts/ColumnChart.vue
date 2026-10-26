<script setup lang="ts">
/**
 * 세로 막대. 시간대처럼 x 축이 자연스러운 순서를 갖고 라벨이 짧을 때 쓴다.
 *
 * 값을 칸마다 적지 않는다 — 12개 칸에 숫자를 다 붙이면 아무도 읽지 않는다.
 * 가장 높은 칸 하나만 직접 라벨을 달고(그게 이 차트가 답하는 질문이다),
 * 나머지는 눈금 · 호버 · 표로 읽는다.
 */
import { computed, ref } from 'vue'
import ChartTooltip from './ChartTooltip.vue'
import { AXIS_COLOR, GRID_COLOR, niceMax, seriesColor, ticksFor } from './palette'

const props = withDefaults(
  defineProps<{
    items: { label: string; value: number }[]
    format?: (value: number) => string
    valueLabel?: string
    /** 플롯 영역 높이(px). x 축 라벨 높이는 여기 포함되지 않는다. */
    height?: number
  }>(),
  {
    format: (value: number) => value.toLocaleString('ko-KR'),
    valueLabel: '팀',
    height: 168,
  },
)

const root = ref<HTMLElement | null>(null)
const hovered = ref<{ index: number; x: number; y: number } | null>(null)

const max = computed(() =>
  niceMax(Math.max(1, ...props.items.map((item) => item.value))),
)
const ticks = computed(() => ticksFor(max.value).reverse())

/** 최댓값이 여러 칸이면 첫 칸만 라벨을 단다 */
const peakIndex = computed(() => {
  let best = -1
  let bestValue = 0
  props.items.forEach((item, index) => {
    if (item.value > bestValue) {
      bestValue = item.value
      best = index
    }
  })
  return best
})

function heightOf(value: number): string {
  return `${(value / max.value) * 100}%`
}

function show(index: number, event: PointerEvent | FocusEvent): void {
  const bounds = root.value?.getBoundingClientRect()
  if (!bounds) return
  const cell = (event.currentTarget as HTMLElement).getBoundingClientRect()
  hovered.value = {
    index,
    x: cell.left + cell.width / 2 - bounds.left,
    y: cell.top + cell.height * 0.35 - bounds.top,
  }
}

const tooltip = computed(() => {
  if (!hovered.value) return null
  const item = props.items[hovered.value.index]
  if (!item) return null
  return {
    title: item.label,
    rows: [
      { label: props.valueLabel, value: props.format(item.value), color: seriesColor(0) },
    ],
  }
})
</script>

<template>
  <div ref="root" class="relative">
    <div class="flex" :style="{ height: `${height}px` }">
      <!-- y 눈금. 값 라벨을 다 붙이지 않는 대신 이 눈금이 값을 읽게 해 준다 -->
      <div
        class="flex w-8 shrink-0 flex-col justify-between pr-2 text-right text-[10px] text-muted tabular-nums"
      >
        <span v-for="tick in ticks" :key="tick">{{ Math.round(tick) }}</span>
      </div>

      <div class="relative min-w-0 flex-1">
        <!-- 가로 격자. 실선 헤어라인 — 점선은 '임계선' 처럼 읽혀서 쓰지 않는다 -->
        <div class="absolute inset-0 flex flex-col justify-between">
          <span
            v-for="(tick, index) in ticks"
            :key="tick"
            class="block h-px w-full"
            :style="{
              background: index === ticks.length - 1 ? AXIS_COLOR : GRID_COLOR,
            }"
          />
        </div>

        <div class="relative flex h-full items-end gap-1">
          <div
            v-for="(item, index) in items"
            :key="item.label"
            class="flex h-full min-w-0 flex-1 cursor-default flex-col justify-end"
            tabindex="0"
            @pointerenter="show(index, $event)"
            @pointerleave="hovered = null"
            @focus="show(index, $event)"
            @blur="hovered = null"
          >
            <span
              v-if="index === peakIndex && item.value > 0"
              class="mb-1 text-center text-[10px] font-bold text-ink tabular-nums"
            >
              {{ format(item.value) }}
            </span>
            <span
              class="mx-auto block w-full max-w-6 transition-[height] duration-300"
              :style="{
                height: heightOf(item.value),
                background: seriesColor(0),
                borderRadius: '4px 4px 0 0',
                opacity: hovered && hovered.index !== index ? 0.55 : 1,
              }"
            />
          </div>
        </div>
      </div>
    </div>

    <div class="mt-1.5 flex pl-8">
      <span
        v-for="item in items"
        :key="item.label"
        class="min-w-0 flex-1 text-center text-[10px] text-muted"
      >
        {{ item.label }}
      </span>
    </div>

    <ChartTooltip
      v-if="hovered && tooltip"
      :x="hovered.x"
      :y="hovered.y"
      :width="root?.clientWidth ?? 0"
      :title="tooltip.title"
      :rows="tooltip.rows"
    />
  </div>
</template>

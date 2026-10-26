<script setup lang="ts">
/**
 * 전체 대비 비중을 한 줄로 보여 주는 누적 막대.
 *
 * 원형(파이·도넛) 대신 쓴다 — 비슷한 크기의 조각을 각도로 비교하는 건 사람이 잘
 * 못하는 일이고, 가로 막대는 카테고리 이름을 그대로 붙일 수 있다.
 *
 * 조각 사이는 테두리가 아니라 **2px 표면색 틈**으로 가른다. 테두리를 두르면
 * 데이터가 아닌 잉크가 늘어나고 조각이 실제보다 두꺼워 보인다.
 *
 * 조각 안의 라벨은 들어갈 자리가 확실할 때만 그린다. 안 들어가는 라벨을 잘라
 * 넣는 것보다 아래 목록에서 읽게 하는 편이 낫다.
 */
import { computed, ref } from 'vue'
import ChartTooltip from './ChartTooltip.vue'

const props = withDefaults(
  defineProps<{
    items: { label: string; value: number; color: string }[]
    format?: (value: number) => string
    valueLabel?: string
  }>(),
  {
    format: (value: number) => value.toLocaleString('ko-KR'),
    valueLabel: '건',
  },
)

const root = ref<HTMLElement | null>(null)
const hovered = ref<{ index: number; x: number; y: number } | null>(null)

const total = computed(() =>
  props.items.reduce((sum, item) => sum + item.value, 0),
)

function share(value: number): number {
  return total.value === 0 ? 0 : value / total.value
}

function percentText(value: number): string {
  return `${Math.round(share(value) * 100)}%`
}

/** 조각 안에 '34%' 정도는 들어가는 최소 폭 */
const INLINE_LABEL_MIN_SHARE = 0.13

function show(index: number, event: PointerEvent | FocusEvent): void {
  const bounds = root.value?.getBoundingClientRect()
  if (!bounds) return
  const segment = (event.currentTarget as HTMLElement).getBoundingClientRect()
  hovered.value = {
    index,
    x: segment.left + segment.width / 2 - bounds.left,
    y: segment.top + segment.height / 2 - bounds.top,
  }
}

const tooltip = computed(() => {
  if (!hovered.value) return null
  const item = props.items[hovered.value.index]
  if (!item) return null
  return {
    title: item.label,
    rows: [
      { label: props.valueLabel, value: props.format(item.value), color: item.color },
      { label: '비중', value: percentText(item.value) },
    ],
  }
})
</script>

<template>
  <div ref="root" class="relative">
    <div class="flex h-8 w-full gap-0.5 overflow-hidden rounded-[6px]">
      <button
        v-for="(item, index) in items"
        :key="item.label"
        type="button"
        class="flex h-full min-w-0 items-center justify-center transition-opacity"
        :style="{
          flex: `${Math.max(share(item.value), 0.001)} 1 0%`,
          background: item.color,
          opacity: hovered && hovered.index !== index ? 0.6 : 1,
        }"
        :aria-label="`${item.label} ${format(item.value)}${valueLabel}, 비중 ${percentText(item.value)}`"
        @pointerenter="show(index, $event)"
        @pointerleave="hovered = null"
        @focus="show(index, $event)"
        @blur="hovered = null"
      >
        <!-- 칠해진 면 위의 글자는 흰색으로 고정한다(슬롯 색 모두 흰 글자가 읽힌다) -->
        <span
          v-if="share(item.value) >= INLINE_LABEL_MIN_SHARE"
          class="text-[11px] font-bold text-white tabular-nums"
        >
          {{ percentText(item.value) }}
        </span>
      </button>
    </div>

    <!-- 조각 안에 못 넣은 값까지 전부 여기서 읽을 수 있다 -->
    <ul class="mt-3.5 flex flex-col gap-2">
      <li
        v-for="item in items"
        :key="item.label"
        class="flex items-center gap-2 text-xs"
      >
        <span class="size-2.5 shrink-0 rounded-[3px]" :style="{ background: item.color }" />
        <span class="min-w-0 flex-1 truncate text-body">{{ item.label }}</span>
        <span class="text-subtle tabular-nums">{{ format(item.value) }}{{ valueLabel }}</span>
        <span class="w-9 text-right font-semibold text-ink tabular-nums">
          {{ percentText(item.value) }}
        </span>
      </li>
    </ul>

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

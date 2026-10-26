<script setup lang="ts">
/**
 * 가로 막대. 항목 이름이 길 때(게임 이름, 방 이름) 세로 막대보다 읽기 쉽다.
 *
 * 값은 막대 끝에 직접 붙는다 — 축 눈금 없이도 읽히고, 라이트 모드에서 대비가
 * 낮은 색 슬롯을 쓰더라도 숫자는 텍스트 색으로 남아 항상 읽을 수 있다.
 */
import { computed, ref } from 'vue'
import ChartTooltip from './ChartTooltip.vue'
import { niceMax, seriesColor } from './palette'

export interface BarItem {
  label: string
  value: number
  /** 없으면 전부 1번 슬롯 한 색. 항목에 순서/구분이 있을 때만 넘긴다. */
  color?: string
}

const props = withDefaults(
  defineProps<{
    items: BarItem[]
    /** 막대 끝과 툴팁에 쓰는 표기 */
    format?: (value: number) => string
    /** 툴팁 제목 뒤에 붙는 단위 설명 */
    valueLabel?: string
    /** 이름 열 너비 */
    labelWidth?: string
  }>(),
  {
    format: (value: number) => value.toLocaleString('ko-KR'),
    valueLabel: '건',
    labelWidth: '104px',
  },
)

const root = ref<HTMLElement | null>(null)
const hovered = ref<{ index: number; x: number; y: number } | null>(null)

/** 축이 없으므로 최댓값은 '깔끔한 수'가 아니라 실제 최댓값이어도 된다 */
const max = computed(() => {
  const highest = Math.max(0, ...props.items.map((item) => item.value))
  return highest === 0 ? 1 : niceMax(highest)
})

function barColor(item: BarItem): string {
  return item.color ?? seriesColor(0)
}

function widthOf(value: number): string {
  return `${Math.max(0, (value / max.value) * 100)}%`
}

function show(index: number, event: PointerEvent | FocusEvent): void {
  const bounds = root.value?.getBoundingClientRect()
  if (!bounds) return

  const target = event.currentTarget as HTMLElement
  const row = target.getBoundingClientRect()
  const x =
    event instanceof PointerEvent
      ? event.clientX - bounds.left
      : row.left + row.width * 0.5 - bounds.left

  hovered.value = { index, x, y: row.top + row.height / 2 - bounds.top }
}

const tooltip = computed(() => {
  if (!hovered.value) return null
  const item = props.items[hovered.value.index]
  if (!item) return null
  return {
    title: item.label,
    rows: [{ label: props.valueLabel, value: props.format(item.value), color: barColor(item) }],
  }
})
</script>

<template>
  <div ref="root" class="relative">
    <ul class="flex flex-col">
      <li
        v-for="(item, index) in items"
        :key="item.label"
        class="grid items-center gap-3 rounded-[6px] py-1.5 transition-colors"
        :class="hovered?.index === index && 'bg-sunken'"
        :style="{ gridTemplateColumns: `${labelWidth} 1fr auto` }"
        tabindex="0"
        @pointermove="show(index, $event)"
        @pointerleave="hovered = null"
        @focus="show(index, $event)"
        @blur="hovered = null"
      >
        <span class="truncate text-xs font-medium text-body" :title="item.label">
          {{ item.label }}
        </span>

        <span class="relative block h-3">
          <span
            class="absolute inset-y-0 left-0 block transition-[width] duration-300"
            :style="{
              width: widthOf(item.value),
              background: barColor(item),
              borderRadius: '0 4px 4px 0',
            }"
          />
        </span>

        <span class="w-12 text-right text-xs font-semibold text-ink tabular-nums">
          {{ format(item.value) }}
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

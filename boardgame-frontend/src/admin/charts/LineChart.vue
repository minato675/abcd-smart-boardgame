<script setup lang="ts">
/**
 * 추이 선 차트. 두 계열까지만 받는다.
 *
 * **한 축만 쓴다.** 단위가 다른 두 값을 좌우 두 축에 나눠 그리면 두 축의 정렬이
 * 임의라서 있지도 않은 상관관계를 만들어 낸다. 여기 올라오는 '이용 팀 수'와
 * '대여 건수'는 둘 다 건수라 같은 축에 놓을 수 있다. 단위가 다른 값을 비교해야
 * 하면 차트를 두 개로 나눌 것.
 *
 * 십자선이 x 를 대신 찾아 준다 — 읽는 사람은 날짜를 겨냥하면 되고, 2px 짜리 선
 * 위에 포인터를 정확히 올릴 필요가 없다. 툴팁은 그 x 의 모든 계열을 한 번에 준다.
 */
import { computed, ref } from 'vue'
import ChartTooltip from './ChartTooltip.vue'
import { AXIS_COLOR, GRID_COLOR, niceMax, SURFACE_COLOR, ticksFor } from './palette'
import { useChartWidth } from './useChartSize'

export interface LineSeries {
  name: string
  color: string
  values: number[]
}

const props = withDefaults(
  defineProps<{
    labels: string[]
    series: LineSeries[]
    format?: (value: number) => string
    height?: number
  }>(),
  {
    format: (value: number) => value.toLocaleString('ko-KR'),
    height: 200,
  },
)

const root = ref<HTMLElement | null>(null)
const width = useChartWidth(root)
const activeIndex = ref<number | null>(null)

const PAD = { top: 14, right: 46, bottom: 24, left: 34 }

const plot = computed(() => ({
  width: Math.max(120, width.value - PAD.left - PAD.right),
  height: props.height - PAD.top - PAD.bottom,
}))

const max = computed(() =>
  niceMax(
    Math.max(1, ...props.series.flatMap((series) => series.values)),
  ),
)
const ticks = computed(() => ticksFor(max.value))

function xOf(index: number): number {
  const count = props.labels.length
  if (count <= 1) return PAD.left + plot.value.width / 2
  return PAD.left + (plot.value.width * index) / (count - 1)
}

function yOf(value: number): number {
  return PAD.top + plot.value.height * (1 - value / max.value)
}

function pathOf(series: LineSeries): string {
  return series.values
    .map((value, index) => `${index === 0 ? 'M' : 'L'}${xOf(index)} ${yOf(value)}`)
    .join(' ')
}

/** 계열이 하나면 아래를 옅게 채워 준다. 둘이면 서로를 가려서 채우지 않는다. */
const areaPath = computed(() => {
  const only = props.series[0]
  if (!only || props.series.length !== 1) return null
  const base = PAD.top + plot.value.height
  return `${pathOf(only)} L${xOf(only.values.length - 1)} ${base} L${xOf(0)} ${base} Z`
})

/** x 라벨은 겹치지 않을 만큼만 남긴다 */
const labelStep = computed(() =>
  Math.max(1, Math.ceil(props.labels.length / Math.max(2, Math.floor(plot.value.width / 46)))),
)

function track(event: PointerEvent): void {
  const bounds = root.value?.getBoundingClientRect()
  if (!bounds || props.labels.length === 0) return

  const relative = event.clientX - bounds.left - PAD.left
  const step = props.labels.length <= 1 ? 1 : plot.value.width / (props.labels.length - 1)
  const index = Math.round(relative / step)
  activeIndex.value = Math.min(props.labels.length - 1, Math.max(0, index))
}

const tooltip = computed(() => {
  const index = activeIndex.value
  if (index === null) return null
  return {
    x: xOf(index),
    y: PAD.top + plot.value.height * 0.35,
    title: props.labels[index] ?? '',
    rows: props.series.map((series) => ({
      label: series.name,
      value: props.format(series.values[index] ?? 0),
      color: series.color,
    })),
  }
})

/**
 * 끝점 라벨. 두 선이 오른쪽에서 붙어 있으면 라벨을 세로로 밀어 떼어 놓는 대신
 * 아예 생략한다 — 밀어 놓은 라벨은 어느 선의 값인지 알 수 없어 노이즈가 된다.
 * 그때는 범례 · 툴팁 · 표가 값을 맡는다.
 */
const endLabels = computed(() => {
  const points = props.series.map((series) => ({
    color: series.color,
    value: series.values[series.values.length - 1] ?? 0,
  }))
  if (points.length === 2) {
    const gap = Math.abs(yOf(points[0]!.value) - yOf(points[1]!.value))
    if (gap < 15) return []
  }
  return points
})
</script>

<template>
  <div ref="root" class="relative">
    <svg
      :width="width"
      :height="height"
      role="img"
      :aria-label="`${series.map((s) => s.name).join(', ')} 추이`"
      @pointermove="track"
      @pointerleave="activeIndex = null"
    >
      <!-- 격자와 눈금 -->
      <g>
        <template v-for="tick in ticks" :key="tick">
          <line
            :x1="PAD.left"
            :x2="PAD.left + plot.width"
            :y1="yOf(tick)"
            :y2="yOf(tick)"
            :stroke="tick === 0 ? AXIS_COLOR : GRID_COLOR"
            stroke-width="1"
          />
          <text
            :x="PAD.left - 8"
            :y="yOf(tick) + 3"
            text-anchor="end"
            class="fill-muted text-[10px] tabular-nums"
          >
            {{ Math.round(tick) }}
          </text>
        </template>
      </g>

      <!-- x 라벨 -->
      <g>
        <text
          v-for="(label, index) in labels"
          v-show="index % labelStep === 0 || index === labels.length - 1"
          :key="label"
          :x="xOf(index)"
          :y="height - 6"
          text-anchor="middle"
          class="fill-muted text-[10px]"
        >
          {{ label }}
        </text>
      </g>

      <path v-if="areaPath" :d="areaPath" :fill="series[0]!.color" opacity="0.1" />

      <path
        v-for="line in series"
        :key="line.name"
        :d="pathOf(line)"
        fill="none"
        :stroke="line.color"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
      />

      <!-- 십자선 + 그 x 의 모든 계열 점 -->
      <g v-if="activeIndex !== null">
        <line
          :x1="xOf(activeIndex)"
          :x2="xOf(activeIndex)"
          :y1="PAD.top"
          :y2="PAD.top + plot.height"
          :stroke="AXIS_COLOR"
          stroke-width="1"
        />
        <circle
          v-for="line in series"
          :key="line.name"
          :cx="xOf(activeIndex)"
          :cy="yOf(line.values[activeIndex] ?? 0)"
          r="4.5"
          :fill="line.color"
          :stroke="SURFACE_COLOR"
          stroke-width="2"
        />
      </g>

      <!-- 끝점 값 -->
      <g v-if="activeIndex === null">
        <template v-for="point in endLabels" :key="point.color">
          <circle
            :cx="xOf(labels.length - 1)"
            :cy="yOf(point.value)"
            r="4"
            :fill="point.color"
            :stroke="SURFACE_COLOR"
            stroke-width="2"
          />
          <text
            :x="xOf(labels.length - 1) + 9"
            :y="yOf(point.value) + 4"
            class="fill-ink text-[11px] font-bold tabular-nums"
          >
            {{ format(point.value) }}
          </text>
        </template>
      </g>
    </svg>

    <ChartTooltip
      v-if="tooltip"
      :x="tooltip.x"
      :y="tooltip.y"
      :width="width"
      :title="tooltip.title"
      :rows="tooltip.rows"
    />
  </div>
</template>

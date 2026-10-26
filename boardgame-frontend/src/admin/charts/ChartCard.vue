<script setup lang="ts">
/**
 * 차트 하나를 감싸는 카드 — 제목 · 범례 · 표 보기 토글.
 *
 * **표 보기는 장식이 아니라 필수 장치다.** 라이트 모드에서 일부 계열 색은 흰 배경
 * 대비가 3:1 에 못 미치고, 색만으로 값을 전달하면 색각 이상이나 저대비 환경에서
 * 읽을 수 없다. 그래서 모든 차트가 같은 값을 담은 표를 함께 갖는다.
 *
 * 범례는 계열이 둘 이상일 때 항상 있다. 하나뿐이면 제목이 곧 그 계열의 이름이라
 * 스와치 한 칸짜리 범례는 제목을 되풀이할 뿐이므로 넣지 않는다.
 */
import { ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'

export interface LegendItem {
  label: string
  color: string
}

withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    /** 2개 이상일 때만 그려진다 */
    legend?: LegendItem[]
    /** 범례 스와치 모양. 마크와 같은 모양이어야 한다(선 차트는 선, 막대는 사각). */
    legendShape?: 'rect' | 'line'
    tableColumns: string[]
    tableRows: (string | number)[][]
  }>(),
  { legendShape: 'rect', legend: () => [] },
)

const showTable = ref(false)
</script>

<template>
  <section
    class="flex min-w-0 flex-col rounded-card border border-line-soft bg-surface p-5"
  >
    <header class="flex items-start gap-3">
      <div class="min-w-0 flex-1">
        <h3 class="text-sm font-bold tracking-tight text-ink">{{ title }}</h3>
        <p v-if="subtitle" class="mt-0.5 text-xs text-subtle">{{ subtitle }}</p>
      </div>

      <button
        type="button"
        class="flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-line px-3 text-[11px] font-semibold text-subtle transition hover:bg-sunken"
        :aria-pressed="showTable"
        @click="showTable = !showTable"
      >
        <AppIcon :name="showTable ? 'gauge' : 'table'" :size="13" :stroke-width="1.9" />
        {{ showTable ? '차트로 보기' : '표로 보기' }}
      </button>
    </header>

    <ul
      v-if="legend.length > 1 && !showTable"
      class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5"
    >
      <li
        v-for="item in legend"
        :key="item.label"
        class="flex items-center gap-1.5 text-[11px] font-medium text-subtle"
      >
        <span
          :class="legendShape === 'line' ? 'h-0.5 w-3.5 rounded-full' : 'size-2.5 rounded-[3px]'"
          :style="{ background: item.color }"
        />
        {{ item.label }}
      </li>
    </ul>

    <div v-if="!showTable" class="mt-4 min-w-0 flex-1">
      <slot />
    </div>

    <div v-else class="custom-scroll mt-4 max-h-[280px] min-w-0 flex-1 overflow-auto">
      <table class="w-full border-collapse text-left text-xs">
        <thead>
          <tr class="border-b border-line">
            <th
              v-for="(column, index) in tableColumns"
              :key="column"
              class="py-2 pr-3 font-semibold text-subtle"
              :class="index > 0 && 'text-right'"
              scope="col"
            >
              {{ column }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, rowIndex) in tableRows"
            :key="rowIndex"
            class="border-b border-line-soft last:border-0"
          >
            <td
              v-for="(cell, cellIndex) in row"
              :key="cellIndex"
              class="py-2 pr-3 text-body"
              :class="cellIndex > 0 ? 'text-right tabular-nums' : 'font-medium'"
            >
              {{ cell }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  QUICK_FILTER_OPTIONS,
  type CategoryFilter,
  type GameCategory,
  type QuickFilter,
} from '@/types/game'

/**
 * 카테고리 칩 한 줄 + 상황별 빠른 칩(처음이에요 / 30분 안에 / 지금 가능).
 * 접히는 필터 패널을 없애고 항상 보이게 두었다 — 태블릿에서 탭 수가 줄어든다.
 */
const category = defineModel<CategoryFilter>('category', { required: true })
const quick = defineModel<QuickFilter>('quick', { required: true })

defineProps<{ options: GameCategory[] }>()

const CHIP = 'h-8.5 shrink-0 rounded-full border px-3.5 text-[13px] font-semibold transition'
const ON = 'border-accent bg-accent-softer text-accent'
const OFF = 'border-line bg-surface text-subtle hover:bg-sunken'
</script>

<template>
  <div class="flex shrink-0 items-center gap-4">
    <div class="custom-scroll flex min-w-0 flex-1 gap-1.5 overflow-x-auto">
      <button
        type="button"
        :class="[CHIP, category === 'all' ? ON : OFF]"
        @click="category = 'all'"
      >
        전체
      </button>
      <button
        v-for="option in options"
        :key="option.id"
        type="button"
        :class="[CHIP, category === option.id ? ON : OFF]"
        @click="category = option.id"
      >
        {{ option.name }}
      </button>
    </div>

    <div class="flex shrink-0 gap-1.5">
      <button
        v-for="option in QUICK_FILTER_OPTIONS"
        :key="option.value"
        type="button"
        :class="[CHIP, quick === option.value ? ON : OFF]"
        @click="quick = quick === option.value ? 'none' : option.value"
      >
        {{ option.label }}
      </button>
    </div>
  </div>
</template>

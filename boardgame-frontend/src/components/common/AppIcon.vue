<script setup lang="ts">
import { computed } from 'vue'
import { ICON_PATHS, type IconName } from './icons'

const props = withDefaults(
  defineProps<{
    name: IconName
    size?: number | string
    strokeWidth?: number
  }>(),
  { size: 20, strokeWidth: 2 },
)

const paths = computed<readonly string[]>(() => ICON_PATHS[props.name])
const dimension = computed(() =>
  typeof props.size === 'number' ? `${props.size}px` : props.size,
)
</script>

<template>
  <svg
    :width="dimension"
    :height="dimension"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class="shrink-0"
  >
    <path v-for="(d, index) in paths" :key="index" :d="d" />
  </svg>
</template>

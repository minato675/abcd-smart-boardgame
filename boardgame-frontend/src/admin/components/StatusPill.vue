<script setup lang="ts">
/**
 * 상태 배지.
 *
 * 색은 아이콘·글자와 **항상 같이** 나온다. 색만으로 상태를 전하면 색각 이상이나
 * 흑백 출력에서 정보가 사라지고, 라이트 모드에서 경고색은 배경 대비가 낮아
 * 글자 없이는 눈에 띄지도 않는다.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import type { IconName } from '@/components/common/icons'

const props = withDefaults(
  defineProps<{
    /** ok=정상/진행, warn=주의, danger=문제, idle=비어 있음 */
    tone: 'ok' | 'warn' | 'danger' | 'idle'
    label: string
    icon?: IconName
    size?: 'sm' | 'md'
  }>(),
  { size: 'sm' },
)

const TONES = {
  ok: 'bg-ok-bg text-ok',
  warn: 'bg-warm-bg text-warm',
  danger: 'bg-danger-bg text-danger',
  idle: 'bg-sunken text-subtle',
} as const

const classes = computed(() => [
  TONES[props.tone],
  props.size === 'md' ? 'h-8 px-3.5 text-xs' : 'h-6 px-2.5 text-[11px]',
])
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center gap-1.5 rounded-full font-bold whitespace-nowrap"
    :class="classes"
  >
    <AppIcon v-if="icon" :name="icon" :size="size === 'md' ? 14 : 12" :stroke-width="2.1" />
    <span v-else class="size-1.5 rounded-full bg-current" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import type { Toast } from '@/composables/useToast'

const props = defineProps<{ toast: Toast }>()

const chip = computed(() =>
  props.toast.tone === 'success' ? 'bg-ok' : 'bg-danger',
)
</script>

<template>
  <div
    class="absolute bottom-5 left-1/2 z-60 flex min-w-[380px] -translate-x-1/2 items-center gap-3 rounded-card bg-ink px-5 py-3.5 text-surface shadow-[0_8px_30px_rgba(17,17,17,0.25)]"
    role="status"
  >
    <span
      :class="[
        'flex size-6.5 shrink-0 items-center justify-center rounded-full text-white',
        chip,
      ]"
    >
      <AppIcon
        :name="toast.tone === 'success' ? 'check' : 'close'"
        :size="15"
        :stroke-width="2.4"
      />
    </span>
    <p class="text-sm font-semibold">{{ toast.message }}</p>
  </div>
</template>

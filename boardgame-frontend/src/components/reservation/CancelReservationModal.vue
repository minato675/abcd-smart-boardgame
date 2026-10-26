<script setup lang="ts">
import BaseOverlay from '@/components/common/BaseOverlay.vue'

defineProps<{ gameName: string; pending?: boolean }>()
defineEmits<{ keep: []; confirm: [] }>()
</script>

<template>
  <BaseOverlay labelledby="cancel-title" @backdrop="$emit('keep')">
    <div
      class="w-[420px] rounded-modal border border-line-soft bg-surface p-6 shadow-[0_12px_40px_rgba(17,17,17,0.18)]"
    >
      <h2 id="cancel-title" class="text-[17px] font-semibold text-ink">
        예약을 취소할까요?
      </h2>
      <p class="mt-1.5 text-[13px] leading-relaxed text-subtle">
        <strong class="text-body">{{ gameName }}</strong> 예약을 취소하면
        대기 순번이 사라집니다.
      </p>

      <div class="mt-5 flex gap-2">
        <button
          type="button"
          class="h-11 flex-1 rounded-full border border-line text-sm font-semibold text-ink transition hover:bg-sunken"
          @click="$emit('keep')"
        >
          그대로 두기
        </button>
        <button
          type="button"
          :disabled="pending"
          class="h-11 flex-1 rounded-full bg-danger text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
          @click="$emit('confirm')"
        >
          예약 취소
        </button>
      </div>
    </div>
  </BaseOverlay>
</template>

<script setup lang="ts">
import BaseOverlay from '@/components/common/BaseOverlay.vue'
import type { ReservationAlert } from '@/types/game'

/**
 * 다른 팀이 반납해서, 예약해둔 게임을 지금 빌릴 수 있게 됐을 때.
 *
 * 두 버튼 다 서버 상태를 바꾼다 — '지금 대여' 는 대여를, '예약 취소' 는 취소를 보낸다.
 * 답하지 않고 두면 서버가 남은 시간이 다 됐을 때 예약을 취소하고 다음 팀에게 넘긴다.
 * 그래서 남은 시간은 안내가 아니라 실제 마감이고, 문구도 그렇게 말해야 한다.
 */
defineProps<{
  alert: ReservationAlert
  remainingSeconds: number
  progress: number
  /** 요청을 보내는 중 (두 번 눌리는 것을 막는다) */
  pending: boolean
}>()

defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
  <BaseOverlay labelledby="reservation-alert-title">
    <div
      class="w-[460px] rounded-modal border border-line-soft bg-surface p-7 text-center shadow-[0_12px_40px_rgba(17,17,17,0.22)]"
    >
      <span
        class="inline-block rounded-full bg-warm-bg px-2.5 py-1 text-[11px] font-semibold tracking-wide text-warm"
      >
        방금 반납됐어요
      </span>

      <h2
        id="reservation-alert-title"
        class="mt-3.5 text-[22px] leading-snug font-bold text-ink"
      >
        {{ alert.gameName }}, 지금 대여할 수 있어요
      </h2>
      <p class="mt-1.5 text-[13px] text-subtle">
        대여하면 카드를 태그해 사물함에서 꺼낼 수 있어요.
      </p>

      <div class="mt-5 flex flex-col gap-1.5 text-left">
        <div class="flex justify-between text-xs">
          <span class="text-subtle">답이 없으면 다음 팀에게 넘어가요</span>
          <strong class="font-semibold text-ink tabular-nums">
            {{ Math.max(remainingSeconds, 0) }}초
          </strong>
        </div>
        <div class="h-1.5 overflow-hidden rounded-full bg-line-soft">
          <div
            class="h-full rounded-full bg-accent transition-[width] duration-1000 ease-linear"
            :style="{ width: `${Math.max(progress, 0)}%` }"
          />
        </div>
      </div>

      <div class="mt-5 flex gap-2">
        <button
          type="button"
          :disabled="pending"
          class="h-12 flex-1 rounded-full border border-line text-[15px] font-semibold text-ink transition hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-50"
          @click="$emit('cancel')"
        >
          예약 취소
        </button>
        <button
          type="button"
          :disabled="pending"
          class="h-12 flex-1 rounded-full bg-ink text-[15px] font-semibold text-surface transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          @click="$emit('confirm')"
        >
          지금 대여
        </button>
      </div>
    </div>
  </BaseOverlay>
</template>

<script setup lang="ts">
/**
 * 되돌리기 어려운 동작 앞에 한 번 묻는 창.
 *
 * 퇴실은 그 방의 대여를 전부 마감하고 대기 예약을 취소한다 — 실수로 눌렀을 때
 * 되돌릴 방법이 없으므로, 무엇이 같이 일어나는지 여기서 다 말해 준다.
 * 손님 화면(CancelReservationModal)과 달리 화면 전체를 덮는다(관리자 화면은
 * 태블릿 프레임 안에 있지 않다).
 */
import { onBeforeUnmount, onMounted } from 'vue'

defineProps<{
  title: string
  message: string
  /** 확인 버튼 문구 */
  confirmLabel: string
  /** 되돌릴 수 없는 동작이면 확인 버튼이 위험색이 된다 */
  danger?: boolean
  pending?: boolean
  /** 결과로 뭐가 같이 바뀌는지 나열한다 */
  effects?: string[]
}>()

const emit = defineEmits<{ cancel: []; confirm: [] }>()

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('cancel')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div
    class="fixed inset-0 z-70 flex items-center justify-center bg-[rgba(17,17,17,0.45)] p-6"
    role="dialog"
    aria-modal="true"
    aria-labelledby="confirm-title"
    @click.self="emit('cancel')"
  >
    <div
      class="w-[440px] rounded-modal border border-line-soft bg-surface p-6 shadow-[0_16px_48px_rgba(17,17,17,0.24)]"
    >
      <h2 id="confirm-title" class="text-[17px] font-bold text-ink">{{ title }}</h2>
      <p class="mt-2 text-[13px] leading-relaxed text-subtle">{{ message }}</p>

      <ul
        v-if="effects && effects.length"
        class="mt-3.5 flex flex-col gap-1.5 rounded-field bg-sunken px-3.5 py-3"
      >
        <li
          v-for="effect in effects"
          :key="effect"
          class="flex gap-2 text-xs leading-relaxed text-body"
        >
          <span class="mt-1.5 size-1 shrink-0 rounded-full bg-muted" />
          {{ effect }}
        </li>
      </ul>

      <div class="mt-5 flex gap-2">
        <button
          type="button"
          class="h-11 flex-1 rounded-full border border-line text-sm font-semibold text-ink transition hover:bg-sunken"
          @click="emit('cancel')"
        >
          취소
        </button>
        <button
          type="button"
          :disabled="pending"
          class="h-11 flex-1 rounded-full text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
          :class="danger ? 'bg-danger' : 'bg-ink text-surface'"
          @click="emit('confirm')"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BaseOverlay from '@/components/common/BaseOverlay.vue'
import type { RoomRent } from '@/types/game'

/**
 * 반납 / 꺼내기 안내.
 *
 * 사물함은 태블릿이 아니라 **카드 태그**로만 열린다(RentService.openCabinetByCard 만
 * MQTT 를 발행한다). 그래서 버튼으로 반납시킬 수가 없고, 손님이 무엇을 해야 하는지
 * 알려주는 것이 화면이 할 수 있는 전부다.
 */
const props = defineProps<{
  /** 안내 대상 대여 */
  rent: RoomRent
  /**
   * 지금 사용 중인 다른 게임. 서버 findActiveRent 가 USING 을 먼저 집으므로
   * 이게 있으면 카드 태그 한 번은 '그 게임 반납'에 쓰인다.
   */
  usingRent: RoomRent | null
}>()

defineEmits<{ close: [] }>()

const isReturn = computed(() => props.rent.status === 'USING')

/** 꺼내려는 게임보다 반납이 먼저 처리되는 경우 */
const blockedBy = computed(() =>
  !isReturn.value && props.usingRent && props.usingRent.id !== props.rent.id
    ? props.usingRent
    : null,
)

const cabinetLabel = computed(() =>
  props.rent.cabinetId !== null ? `${props.rent.cabinetId}번 사물함` : '사물함',
)

const steps = computed<string[]>(() => {
  if (isReturn.value) {
    return [
      '게임 구성물을 상자에 정리해 담습니다.',
      `카드를 사물함 리더에 태그하면 ${cabinetLabel.value}이 열립니다.`,
      '상자를 넣고 문을 닫으면 반납이 완료됩니다.',
    ]
  }

  if (blockedBy.value) {
    return [
      `먼저 사용 중인 '${blockedBy.value.gameName}' 을 정리해 담습니다.`,
      `카드를 태그하면 '${blockedBy.value.gameName}' 사물함이 열립니다 — 넣고 문을 닫으면 반납됩니다.`,
      `카드를 한 번 더 태그하면 ${cabinetLabel.value}이 열려 '${props.rent.gameName}' 을 꺼낼 수 있습니다.`,
    ]
  }

  return [
    `카드를 사물함 리더에 태그하면 ${cabinetLabel.value}이 열립니다.`,
    '게임을 꺼내고 문을 닫으면 대여가 확정됩니다.',
  ]
})
</script>

<template>
  <BaseOverlay labelledby="cabinet-guide-title" @backdrop="$emit('close')">
    <div
      class="w-[460px] rounded-modal border border-line-soft bg-surface p-6 shadow-[0_12px_40px_rgba(17,17,17,0.18)]"
    >
      <strong id="cabinet-guide-title" class="text-[17px] font-semibold text-ink">
        {{ isReturn ? '반납하는 방법' : '게임을 꺼내는 방법' }}
      </strong>
      <p class="mt-1 text-[13px] text-subtle">
        {{ rent.gameName }}
      </p>

      <ol class="mt-4 flex flex-col gap-2">
        <li
          v-for="(step, index) in steps"
          :key="index"
          class="flex gap-2.5 rounded-field bg-sunken px-3 py-2.5"
        >
          <span
            class="flex size-5.5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-white"
          >
            {{ index + 1 }}
          </span>
          <span class="text-[13px] leading-normal text-body">{{ step }}</span>
        </li>
      </ol>

      <p v-if="blockedBy" class="mt-2.5 text-[11px] text-warm">
        사물함은 한 번에 하나만 열립니다. 반납이 먼저 처리되는 이유예요.
      </p>
      <p v-else-if="isReturn" class="mt-2.5 text-[11px] text-muted">
        반납이 확정되면 이 게임을 기다리던 팀에게 순서가 넘어갑니다.
      </p>

      <button
        type="button"
        class="mt-5 h-11 w-full rounded-full bg-ink text-sm font-semibold text-surface transition hover:opacity-90"
        @click="$emit('close')"
      >
        알겠어요
      </button>
    </div>
  </BaseOverlay>
</template>

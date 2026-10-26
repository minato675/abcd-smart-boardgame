<script setup lang="ts">
import AppIcon from '@/components/common/AppIcon.vue'
import {
  reservationWaitLabel,
  type Reservation,
  type RoomRent,
} from '@/types/game'

/**
 * 우리 방 현황 한 줄 (기존 ReservationBanner 를 흡수했다).
 *
 * 사용 중 / 대여 완료 / 예약을 나란히 보여준다 — 목록을 훑기 전에 "우리가 지금
 * 무엇을 들고 있는지" 부터 알려주는 게 예약 버튼을 잘못 누르는 걸 막는 가장 빠른 길이다.
 * 보여줄 게 하나도 없으면 부모가 렌더링하지 않는다.
 */
defineProps<{
  /** 서버가 USING 을 먼저 정렬해서 준다 */
  rents: RoomRent[]
  reservation: Reservation | null
}>()

defineEmits<{ guide: [rent: RoomRent]; cancelReservation: [] }>()

const CHIP =
  'flex min-w-0 flex-1 items-center gap-2.5 rounded-card border px-3 py-2'
const ACTION =
  'ml-auto h-9 shrink-0 rounded-full border px-3.5 text-xs font-semibold transition'
</script>

<template>
  <section class="flex shrink-0 items-stretch gap-2">
    <div
      v-for="rent in rents"
      :key="rent.id"
      :class="[
        CHIP,
        rent.status === 'USING'
          ? 'border-accent bg-accent-softer'
          : 'border-warm bg-warm-bg',
      ]"
    >
      <span
        :class="[
          'flex size-8 shrink-0 items-center justify-center rounded-full',
          rent.status === 'USING'
            ? 'bg-accent text-white'
            : 'bg-surface text-warm',
        ]"
      >
        <AppIcon
          :name="rent.status === 'USING' ? 'users' : 'info'"
          :size="16"
          :stroke-width="1.75"
        />
      </span>

      <div class="flex min-w-0 flex-col">
        <span
          :class="[
            'text-[11px] font-semibold',
            rent.status === 'USING' ? 'text-accent' : 'text-warm',
          ]"
        >
          {{ rent.status === 'USING' ? '사용 중' : '대여 완료' }}
        </span>
        <strong class="truncate text-sm font-bold text-ink">
          {{ rent.gameName }}
        </strong>
      </div>

      <!-- 대여 직후에는 안내할 게 없다 — 게임은 로비에서 받아간다 -->
      <button
        v-if="rent.status === 'USING'"
        type="button"
        :class="[ACTION, 'border-accent bg-surface text-accent hover:bg-accent-soft']"
        @click="$emit('guide', rent)"
      >
        반납 방법
      </button>
      <span
        v-else
        :class="[ACTION, 'flex items-center border-line-soft bg-sunken text-muted']"
      >
        대여 중
      </span>
    </div>

    <div v-if="reservation" :class="[CHIP, 'border-line bg-surface']">
      <span
        class="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
      >
        <AppIcon name="clock" :size="16" :stroke-width="1.75" />
      </span>

      <div class="flex min-w-0 flex-col">
        <span class="text-[11px] font-semibold text-subtle">
          {{ reservationWaitLabel(reservation.waitingRank) }}
        </span>
        <strong class="truncate text-sm font-bold text-ink">
          {{ reservation.gameName }}
        </strong>
      </div>

      <button
        type="button"
        :class="[ACTION, 'border-line text-danger hover:bg-danger-bg']"
        @click="$emit('cancelReservation')"
      >
        예약 취소
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import GameStateBadge from './GameStateBadge.vue'
import GameThumbnail from './GameThumbnail.vue'
import {
  GAME_ACTION_LABELS,
  difficultyLabel,
  isActionable,
  isGuided,
  playTimeLabel,
  playerRangeLabel,
  reservationWaitLabel,
  resolveGameState,
  summaryLine,
  type BoardGame,
  type RoomRent,
} from '@/types/game'

/**
 * 목록 카드 (2열). 정보 우선 — 88px 썸네일 + 이름 + 스펙 + 한 줄 설명 + 상태.
 * 액션 버튼은 44px 로 태블릿 터치 타깃을 맞춘다.
 *
 * 우리 방이 들고 있는 게임(사용 중 / 대여 완료)은 테두리와 배경까지 바꿔서
 * 목록을 훑을 때 남의 게임과 섞이지 않게 한다.
 */
const props = withDefaults(
  defineProps<{
    game: BoardGame
    /** 우리 방이 이 게임을 들고 있으면 그 대여 건 */
    rent?: RoomRent | null
    reserved?: boolean
    /** 예약을 걸었을 때의 대기 순번. 새로고침으로 복원한 예약은 null 이다. */
    waitingRank?: number | null
  }>(),
  { rent: null, reserved: false, waitingRank: null },
)

defineEmits<{
  detail: [game: BoardGame]
  action: [game: BoardGame]
  guide: [rent: RoomRent]
}>()

const state = computed(() =>
  resolveGameState(props.game, props.rent, props.reserved),
)

const meta = computed(
  () =>
    `${playerRangeLabel(props.game)} · ${playTimeLabel(props.game)} · ${difficultyLabel(props.game)}`,
)

const categories = computed(() =>
  props.game.categories.map((category) => category.name).join('/'),
)

/** 배지가 상태를 짧게 말하고, 이 줄이 다음에 할 행동을 알려준다 */
const statusLine = computed(() => {
  switch (state.value) {
    case 'using':
      return '우리 방이 쓰고 있어요'
    case 'pickup':
      return '우리 방이 대여했어요'
    case 'reserved':
      return reservationWaitLabel(props.waitingRank)
    case 'available':
      return `지금 대여 가능 ${props.game.availableCount}개`
    default:
      return '다른 팀이 대여 중'
  }
})

const STATUS_TONES = {
  using: 'text-accent',
  pickup: 'text-warm',
  reserved: 'text-accent',
  available: 'text-ok',
  rentedOut: 'text-warm',
} as const

/** 우리 방 게임은 카드 자체를 물들여 남의 게임과 구분한다 */
const CARD_TONES = {
  using: 'border-accent bg-accent-softer',
  pickup: 'border-warm bg-warm-bg',
  reserved: 'border-accent bg-surface',
  available: 'border-line-soft bg-surface',
  rentedOut: 'border-line-soft bg-surface',
} as const
</script>

<template>
  <article
    :class="[
      'flex gap-3.5 rounded-card border p-4 shadow-[0_1px_2px_rgba(17,17,17,0.04)] transition',
      CARD_TONES[state],
    ]"
  >
    <button
      type="button"
      class="size-22 shrink-0 cursor-pointer"
      :aria-label="`${game.name} 상세정보 보기`"
      @click="$emit('detail', game)"
    >
      <GameThumbnail :url="game.thumbnailUrl" :name="game.name" />
    </button>

    <div class="flex min-w-0 flex-1 flex-col gap-2">
      <button
        type="button"
        class="flex cursor-pointer flex-col gap-1.5 text-left"
        @click="$emit('detail', game)"
      >
        <div class="flex items-center gap-1.5">
          <strong class="truncate text-[17px] font-bold tracking-tight text-ink">
            {{ game.name }}
          </strong>
          <!-- 우리 방 상태만 배지로 띄운다. 남의 게임까지 달면 목록이 시끄러워진다. -->
          <GameStateBadge
            v-if="state === 'using' || state === 'pickup' || state === 'reserved'"
            :state="state"
          />
          <span
            v-else-if="categories"
            class="shrink-0 rounded-full bg-sunken px-2 py-0.5 text-[10px] font-bold tracking-wide text-subtle"
          >
            {{ categories }}
          </span>
        </div>
        <span class="text-xs text-muted">{{ meta }}</span>
        <p class="line-clamp-2 text-[13px] leading-normal text-subtle">
          {{ summaryLine(game) }}
        </p>
      </button>

      <div class="mt-auto flex items-center gap-2">
        <span
          :class="[
            'min-w-0 flex-1 truncate text-xs font-semibold',
            STATUS_TONES[state],
          ]"
        >
          {{ statusLine }}
        </span>

        <button
          type="button"
          class="h-11 shrink-0 rounded-full border border-line px-3.5 text-[13px] font-semibold text-subtle transition hover:bg-sunken"
          @click="$emit('detail', game)"
        >
          자세히
        </button>

        <!-- 대여/예약: 서버에 요청이 나가는 유일한 상태 -->
        <button
          v-if="isActionable(state)"
          type="button"
          :class="[
            'h-11 min-w-28 shrink-0 rounded-full px-4 text-sm font-semibold transition',
            state === 'available'
              ? 'bg-ink text-surface hover:opacity-90'
              : 'border border-line text-ink hover:bg-sunken',
          ]"
          @click="$emit('action', game)"
        >
          {{ GAME_ACTION_LABELS[state] }}
        </button>

        <!-- 사용 중: 반납은 카드 태그로만 되므로 안내만 연다 -->
        <button
          v-else-if="isGuided(state) && rent"
          type="button"
          class="h-11 min-w-28 shrink-0 rounded-full border border-accent px-4 text-sm font-semibold text-accent transition hover:bg-accent-soft"
          @click="$emit('guide', rent)"
        >
          {{ GAME_ACTION_LABELS[state] }}
        </button>

        <button
          v-else
          type="button"
          disabled
          class="h-11 min-w-28 shrink-0 cursor-not-allowed rounded-full border border-line-soft bg-sunken px-4 text-sm font-semibold text-muted"
        >
          {{ GAME_ACTION_LABELS[state] }}
        </button>
      </div>
    </div>
  </article>
</template>

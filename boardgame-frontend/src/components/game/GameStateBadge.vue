<script setup lang="ts">
import { GAME_STATE_LABELS, type GameState } from '@/types/game'

/**
 * 게임 하나의 상태 배지 (기존 AvailabilityBadge 대체).
 *
 * '사용 중' 만 채운 배지다 — 우리 방이 지금 손에 들고 있는 게임이 한눈에 걸려야 한다.
 * 나머지는 옅은 배경으로 두어 목록이 시끄러워지지 않게 한다.
 */
defineProps<{ state: GameState }>()

const TONES: Record<GameState, string> = {
  using: 'bg-accent text-white',
  pickup: 'bg-warm-bg text-warm',
  reserved: 'bg-accent-soft text-accent',
  available: 'bg-ok-bg text-ok',
  rentedOut: 'bg-sunken text-subtle',
}
</script>

<template>
  <span
    :class="[
      'shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide',
      TONES[state],
    ]"
  >
    {{ GAME_STATE_LABELS[state] }}
  </span>
</template>

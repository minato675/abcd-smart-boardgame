<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import TabletFrame from '@/components/layout/TabletFrame.vue'
import ToastMessage from '@/components/common/ToastMessage.vue'
import CabinetGuideModal from '@/components/game/CabinetGuideModal.vue'
import ReservationAlertOverlay from '@/components/reservation/ReservationAlertOverlay.vue'
import GameStateBadge from '@/components/game/GameStateBadge.vue'
import GameThumbnail from '@/components/game/GameThumbnail.vue'
import { fetchGame, rentGame } from '@/api/games'
import { isApiError, toMessage } from '@/api/http'
import { useGames } from '@/composables/useGames'
import { useReservation } from '@/composables/useReservation'
import { useRoomRents } from '@/composables/useRoomRents'
import { useToast } from '@/composables/useToast'
import { ROOM_LABEL } from '@/config/env'
import {
  GAME_ACTION_LABELS,
  difficultyLabel,
  isActionable,
  isGuided,
  playTimeLabel,
  playerRangeLabel,
  reservationWaitLabel,
  resolveGameState,
  type BoardGameDetail,
} from '@/types/game'

const route = useRoute()
const router = useRouter()
const { refresh } = useGames()
const {
  reservation,
  isSubmitting,
  returnAlert,
  remainingSeconds,
  alertProgress,
  expiredGameName,
  reserve,
  restore,
  acceptAlert,
  dismissAlert,
  clearExpired,
  isReserved,
} = useReservation()
const {
  usingRent,
  rentFor,
  remember,
  load: loadRents,
  refresh: refreshRents,
} = useRoomRents()
const { toast, show: showToast } = useToast()

const game = ref<BoardGameDetail | null>(null)
const isLoading = ref(true)
const loadError = ref<string | null>(null)
const isGuideOpen = ref(false)

/** 우리 방이 이 게임을 들고 있으면 그 대여 건 */
const rent = computed(() => (game.value ? rentFor(game.value.id) : null))

const reserved = computed(() =>
  game.value ? isReserved(game.value.id) : false,
)

const state = computed(() =>
  game.value
    ? resolveGameState(game.value, rent.value, reserved.value)
    : 'available',
)

const actionHint = computed(() => {
  switch (state.value) {
    case 'using':
      return '우리 방이 쓰고 있어요. 반납은 카드를 태그해 사물함을 열면 됩니다.'
    case 'pickup':
      return '대여가 완료되었습니다.'
    case 'reserved':
      return `${reservationWaitLabel(reservation.value?.waitingRank ?? null)}. 다른 팀이 반납하면 이 화면에 알려드립니다.`
    case 'available':
      return '대여하면 로비에서 게임을 받아갈 수 있습니다.'
    default:
      return '다른 팀이 쓰고 있어요. 예약해두면 반납되는 순간 알려드립니다.'
  }
})

async function loadGame(): Promise<void> {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) {
    loadError.value = '잘못된 게임 주소입니다.'
    isLoading.value = false
    return
  }

  try {
    game.value = await fetchGame(id)
    loadError.value = null
  } catch (error) {
    loadError.value = toMessage(error, '게임 정보를 찾을 수 없습니다.')
  } finally {
    isLoading.value = false
  }
}

onMounted(async () => {
  await loadGame()
  // 목록을 거치지 않고 /games/3 으로 바로 들어와도 우리 방 대여 상태를 알아야 한다
  void loadRents()
})

function goBack(): void {
  router.push({ name: 'game-list' })
}

/**
 * 반납 알림 팝업. 알림은 모듈 스코프에서 받으므로 어느 화면에 있어도 뜬다 —
 * 상세를 보다가 다른 게임의 반납 알림을 받는 경우도 그대로 처리된다.
 */
async function acceptReservationAlert(): Promise<void> {
  try {
    const created = await acceptAlert()
    if (!created) return

    remember(created)
    showToast(`'${created.gameName}' 대여가 완료되었습니다.`)
  } catch (error) {
    if (isApiError(error) && error.is('BOARD_GAME_OUT_OF_STOCK')) {
      showToast(
        '방금 다른 팀이 먼저 대여했습니다. 예약은 그대로 두었으니 다시 알려드릴게요.',
        'danger',
      )
    } else {
      showToast(toMessage(error, '대여하지 못했습니다.'), 'danger')
    }
    void restore()
  } finally {
    await loadGame()
    void refresh()
    void refreshRents()
  }
}

async function dismissReservationAlert(): Promise<void> {
  const name = returnAlert.value?.gameName ?? ''
  try {
    await dismissAlert()
    showToast(`'${name}' 예약을 취소했습니다.`, 'danger')
  } catch (error) {
    showToast(toMessage(error, '예약을 취소하지 못했습니다.'), 'danger')
    void restore()
  } finally {
    await loadGame()
    void refresh()
  }
}

/** 답하지 않아 서버가 예약을 취소한 경우 (팝업은 스스로 닫힌 뒤다) */
watch(expiredGameName, async (name) => {
  if (!name) return
  showToast(`'${name}' 예약이 시간 초과로 취소되었습니다.`, 'danger')
  clearExpired()
  await loadGame()
  void refresh()
})

/** 목록 화면과 같은 방식으로, 낡은 재고 정보 때문에 실패하면 반대 경로로 한 번 재시도한다 */
async function handleAction(retried = false): Promise<void> {
  const target = game.value
  if (!target || !isActionable(state.value)) return

  try {
    if (target.available) {
      const created = await rentGame(target.id)
      remember(created)
      showToast(`'${target.name}' 대여가 완료되었습니다.`)
      return
    }

    if (reservation.value && reservation.value.gameId !== target.id) {
      showToast('한 방에서는 한 개의 게임만 예약할 수 있습니다.', 'danger')
      return
    }

    const created = await reserve(target)
    showToast(
      created.waitingRank
        ? `'${target.name}' 예약 완료. 대기 ${created.waitingRank}번째입니다.`
        : `'${target.name}' 예약 완료. 다른 팀이 반납하면 알려드립니다.`,
    )
  } catch (error) {
    if (!isApiError(error)) {
      showToast('요청을 처리하지 못했습니다.', 'danger')
      return
    }

    if (!retried && error.is('BOARD_GAME_OUT_OF_STOCK')) {
      target.available = false
      target.availableCount = 0
      await handleAction(true)
      return
    }

    if (!retried && error.is('RESERVATION_NOT_NEEDED')) {
      target.available = true
      target.availableCount = Math.max(target.availableCount, 1)
      await handleAction(true)
      return
    }

    if (error.is('ALREADY_RENTED')) {
      showToast(`'${target.name}' 은 이미 우리 방이 대여한 게임입니다.`, 'danger')
      return
    }

    if (error.is('ROOM_NOT_IN_USE')) {
      showToast(
        `${ROOM_LABEL} 입실 처리가 필요합니다. 카운터에 문의해주세요.`,
        'danger',
      )
      return
    }

    showToast(toMessage(error, '요청을 처리하지 못했습니다.'), 'danger')
  } finally {
    // availableCount / waitingCount 를 서버 기준으로 다시 맞춘다
    await loadGame()
    void refresh()
    void refreshRents()
  }
}
</script>

<template>
  <TabletFrame>
    <AppHeader show-back subtitle="게임 상세" @back="goBack" />

    <div class="custom-scroll min-h-0 flex-1 overflow-y-auto px-5 py-4">
      <p v-if="isLoading" class="py-16 text-center text-[13px] text-muted">
        게임 정보를 불러오는 중입니다...
      </p>

      <div
        v-else-if="!game"
        class="flex flex-col items-center gap-3 rounded-card border border-line-soft bg-surface py-16"
      >
        <p class="text-[13px] font-semibold text-subtle">
          {{ loadError ?? '게임 정보를 찾을 수 없습니다.' }}
        </p>
        <button
          type="button"
          class="h-11 rounded-full border border-line px-5 text-sm font-semibold text-ink transition hover:bg-sunken"
          @click="goBack"
        >
          목록으로
        </button>
      </div>

      <div v-else class="grid grid-cols-[300px_1fr] items-start gap-4">
        <!-- 좌측: 요약 카드 + 스펙 -->
        <section class="flex flex-col gap-3">
          <div
            :class="[
              'flex flex-col gap-3 rounded-card border p-4',
              state === 'using'
                ? 'border-accent bg-accent-softer'
                : state === 'pickup'
                  ? 'border-warm bg-warm-bg'
                  : 'border-line-soft bg-surface',
            ]"
          >
            <div class="flex items-center gap-3">
              <div class="size-16 shrink-0">
                <GameThumbnail
                  :url="game.thumbnailUrl"
                  :name="game.name"
                  text-size="text-xl"
                />
              </div>
              <div class="flex min-w-0 flex-col gap-1">
                <h1 class="text-[22px] font-bold tracking-tight text-ink">
                  {{ game.name }}
                </h1>
                <span class="truncate text-xs text-subtle">
                  {{ game.categories.map((c) => c.name).join(' · ') || '분류 미등록' }}
                </span>
              </div>
            </div>

            <div class="flex flex-col gap-1.5 border-t border-line-soft pt-3">
              <div class="flex items-center justify-between">
                <span class="text-[13px] text-subtle">지금 상태</span>
                <GameStateBadge :state="state" />
              </div>
              <div class="flex items-center justify-between">
                <span class="text-[13px] text-subtle">보유 / 대여 가능</span>
                <strong class="text-[13px] font-bold text-ink">
                  {{ game.totalCount }}개 중 {{ game.availableCount }}개
                </strong>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-[13px] text-subtle">예약 대기</span>
                <strong class="text-[13px] font-bold text-warm">
                  {{ game.waitingCount > 0 ? `${game.waitingCount}팀` : '없음' }}
                </strong>
              </div>
            </div>
          </div>

          <div class="grid grid-cols-3 gap-2">
            <div
              class="flex flex-col gap-1 rounded-field border border-line-soft bg-surface p-3"
            >
              <span class="text-[11px] font-semibold text-muted">인원</span>
              <strong class="text-sm font-bold text-ink">
                {{ playerRangeLabel(game) }}
              </strong>
            </div>
            <div
              class="flex flex-col gap-1 rounded-field border border-line-soft bg-surface p-3"
            >
              <span class="text-[11px] font-semibold text-muted">시간</span>
              <strong class="text-sm font-bold text-ink">
                {{ playTimeLabel(game) }}
              </strong>
            </div>
            <div
              class="flex flex-col gap-1 rounded-field border border-line-soft bg-surface p-3"
            >
              <span class="text-[11px] font-semibold text-muted">난이도</span>
              <strong class="text-sm font-bold text-ink">
                {{ difficultyLabel(game) }}
              </strong>
            </div>
          </div>
        </section>

        <!-- 우측: 소개 / 시작 방법 / 액션 -->
        <section class="flex flex-col gap-3">
          <div
            class="flex flex-col gap-2 rounded-card border border-line-soft bg-surface p-4"
          >
            <h3 class="text-[13px] font-bold text-subtle">어떤 게임인가요</h3>
            <p class="text-sm leading-relaxed text-body">
              {{ game.description ?? '등록된 소개가 없습니다.' }}
            </p>
          </div>

          <div
            class="flex flex-col gap-2.5 rounded-card border border-line-soft bg-surface p-4"
          >
            <div class="flex items-baseline justify-between">
              <h3 class="text-[13px] font-bold text-subtle">
                3분 안에 시작하는 방법
              </h3>
              <span class="text-[11px] text-muted">
                자세한 규칙은 상자 안 설명서에
              </span>
            </div>

            <ol v-if="game.steps.length > 0" class="flex flex-col gap-2">
              <li
                v-for="(step, index) in game.steps"
                :key="index"
                class="flex gap-2.5 rounded-field bg-sunken px-3 py-2.5"
              >
                <span
                  class="flex size-5.5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-white"
                >
                  {{ index + 1 }}
                </span>
                <div class="flex min-w-0 flex-col gap-0.5">
                  <strong v-if="step.title" class="text-[13px] font-bold text-ink">
                    {{ step.title }}
                  </strong>
                  <span class="text-xs leading-normal text-subtle">
                    {{ step.description }}
                  </span>
                </div>
              </li>
            </ol>
            <p v-else class="text-[13px] text-muted">
              등록된 게임 방법이 없습니다. 카운터에 문의해주세요.
            </p>
          </div>

          <div
            class="flex items-center gap-2.5 rounded-card border border-line-soft bg-surface px-4 py-3"
          >
            <span class="flex-1 text-[13px] text-subtle">{{ actionHint }}</span>
            <button
              type="button"
              class="h-11 rounded-full border border-line px-4.5 text-sm font-semibold text-ink transition hover:bg-sunken"
              @click="goBack"
            >
              목록으로
            </button>

            <!-- 대여/예약 -->
            <button
              v-if="isActionable(state)"
              type="button"
              :class="[
                'h-11 min-w-40 rounded-full px-5 text-[15px] font-semibold transition',
                state === 'available'
                  ? 'bg-ink text-surface hover:opacity-90'
                  : 'bg-accent text-white hover:bg-accent-strong',
              ]"
              @click="handleAction()"
            >
              {{ GAME_ACTION_LABELS[state] }}
            </button>

            <!-- 사용 중: 반납 사물함은 카드 태그로만 열린다 -->
            <button
              v-else-if="isGuided(state) && rent"
              type="button"
              class="h-11 min-w-40 rounded-full border border-accent px-5 text-[15px] font-semibold text-accent transition hover:bg-accent-soft"
              @click="isGuideOpen = true"
            >
              {{ GAME_ACTION_LABELS[state] }}
            </button>

            <button
              v-else
              type="button"
              disabled
              class="h-11 min-w-40 cursor-not-allowed rounded-full border border-line-soft bg-sunken px-5 text-[15px] font-semibold text-muted"
            >
              {{ GAME_ACTION_LABELS[state] }}
            </button>
          </div>
        </section>
      </div>
    </div>

    <template #overlay>
      <ToastMessage v-if="toast" :toast="toast" />

      <CabinetGuideModal
        v-if="isGuideOpen && rent"
        :rent="rent"
        :using-rent="usingRent"
        @close="isGuideOpen = false"
      />

      <ReservationAlertOverlay
        v-if="returnAlert"
        :alert="returnAlert"
        :remaining-seconds="remainingSeconds"
        :progress="alertProgress"
        :pending="isSubmitting"
        @confirm="acceptReservationAlert"
        @cancel="dismissReservationAlert"
      />
    </template>
  </TabletFrame>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import TabletFrame from '@/components/layout/TabletFrame.vue'
import ToastMessage from '@/components/common/ToastMessage.vue'
import CabinetGuideModal from '@/components/game/CabinetGuideModal.vue'
import GameCard from '@/components/game/GameCard.vue'
import GameFilterChips from '@/components/game/GameFilterChips.vue'
import GameSearchBar from '@/components/game/GameSearchBar.vue'
import RoomStatusBar from '@/components/game/RoomStatusBar.vue'
import CancelReservationModal from '@/components/reservation/CancelReservationModal.vue'
import ReservationAlertOverlay from '@/components/reservation/ReservationAlertOverlay.vue'
import RuleAssistantOverlay from '@/components/voice/RuleAssistantOverlay.vue'
import AiRefereePanel from '@/components/game/AiRefereePanel.vue'
import AiRefereePrompt from '@/components/game/AiRefereePrompt.vue'
import TurnLogHistoryModal from '@/components/game/TurnLogHistoryModal.vue'
import { useAiReferee } from '@/composables/useAiReferee'
import { useGames } from '@/composables/useGames'
import { useReservation } from '@/composables/useReservation'
import { useRoomRents } from '@/composables/useRoomRents'
import { useRuleAssistant } from '@/composables/useRuleAssistant'
import { useToast } from '@/composables/useToast'
import { rentGame } from '@/api/games'
import { isApiError, toMessage } from '@/api/http'
import { ROOM_LABEL } from '@/config/env'
import { createEmptyFilter, type BoardGame, type RoomRent } from '@/types/game'

const router = useRouter()
const {
  games,
  isLoading,
  loadError,
  categoryOptions,
  load,
  refresh,
  filterGames,
} = useGames()
const {
  reservation,
  isSubmitting,
  returnAlert,
  remainingSeconds,
  alertProgress,
  expiredGameName,
  reserve,
  cancel,
  restore,
  clearLocal,
  acceptAlert,
  dismissAlert,
  clearExpired,
  isReserved,
} = useReservation()
const {
  rents,
  usingRent,
  rentFor,
  remember,
  load: loadRents,
  refresh: refreshRents,
} = useRoomRents()
const { toast, show: showToast } = useToast()
const {
  isPrompting: isRefereePrompting,
  isActive: isRefereeActive,
  promptGameName: refereePromptGameName,
  promptGameId: refereePromptGameId,
  boardGameName: refereeGameName,
  turnCount: refereeTurnCount,
  playerCount: refereePlayerCount,
  currentSeat: refereeCurrentSeat,
  finishedSeats: refereeFinishedSeats,
  latestTurn: refereeLatestTurn,
  isTurnLoading: isRefereeTurnLoading,
  turnLoadError: refereeTurnLoadError,
  violation: refereeViolation,
  dismissViolation: dismissRefereeViolation,
  isSubmitting: isRefereeBusy,
  isCollapsed: isRefereeCollapsed,
  isHistoryOpen: isTurnLogOpen,
  canStart: canStartReferee,
  toggleCollapsed: toggleReferee,
  openHistory: openTurnLog,
  closeHistory: closeTurnLog,
  restoreSession: restoreReferee,
  syncWithRents: syncReferee,
  dismiss: dismissReferee,
  confirm: confirmReferee,
  restart: reopenRefereePrompt,
  passTurn: passRefereeTurn,
  finishCurrentPlayer: finishRefereePlayer,
  stop: stopReferee,
} = useAiReferee()

/**
 * 권유 팝업의 인원 선택 범위. 대여 목록(RoomRent)에는 인원이 없어 게임 목록에서 찾는다.
 * 목록이 아직 안 왔거나 그 사이 사라졌으면 null 이고, 팝업이 기본 범위로 떨어진다.
 */
const refereePromptGame = computed(() =>
  games.value.find((game) => game.id === refereePromptGameId.value) ?? null,
)

/** 플로팅 패널의 표시 형태. 꺼져 있어도 다시 켤 수 있으면 알약을 남긴다. */
const refereePanelMode = computed<'off' | 'collapsed' | 'open' | null>(() => {
  if (isRefereeActive.value) {
    return isRefereeCollapsed.value ? 'collapsed' : 'open'
  }
  return canStartReferee.value ? 'off' : null
})

// 대여 목록은 8초 폴링과 대여 직후 remember() 양쪽에서 바뀐다. 어느 쪽이든
// 지원 게임이 새로 들어오면 권유 팝업이 떠야 하므로 목록 자체를 감시한다.
watch(rents, (current) => syncReferee(current), { immediate: true })

/**
 * AI 심판 켜기. 어떤 게임으로 시작할지는 서버가 대여 목록에서 고른다.
 * 인원만 팝업에서 고른 값을 보낸다 - 카메라가 셀 수 없는 유일한 값이다.
 */
async function startReferee(playerCount: number): Promise<void> {
  try {
    const started = await confirmReferee(playerCount)
    showToast(`'${started}' AI 심판을 켰습니다. ${playerCount}명 기준으로 지켜볼게요.`)
  } catch (error) {
    if (isApiError(error) && error.is('NO_ACTIVE_RENT')) {
      showToast('대여 중인 게임이 없습니다.', 'danger')
      return
    }
    if (isApiError(error) && error.is('INVALID_PLAYER_COUNT')) {
      showToast('이 게임에서 진행할 수 없는 인원입니다.', 'danger')
      return
    }
    showToast(toMessage(error, 'AI 심판을 켜지 못했습니다.'), 'danger')
  }
}

/**
 * '다 냈어요'. 서버가 그 좌석을 차례에서 빼고, 마지막 한 명만 남으면 세션까지 끝낸다.
 * 끝났으면 패널이 이미 닫힌 뒤라 안내만 남긴다.
 */
async function finishRefereeSeat(): Promise<void> {
  const seat = refereeCurrentSeat.value
  try {
    const ended = await finishRefereePlayer()
    showToast(
      ended
        ? `${seat}번님이 마지막 수를 두셨어요. 게임이 끝나 AI 심판을 껐습니다.`
        : `${seat}번님을 차례에서 뺐습니다.`,
    )
  } catch (error) {
    if (isApiError(error) && error.is('MC_SESSION_NOT_FOUND')) {
      showToast('AI 심판이 종료되었습니다. 다시 켜주세요.', 'danger')
      return
    }
    showToast(toMessage(error, '차례를 정리하지 못했습니다.'), 'danger')
  }
}

/** 턴 넘기기. 결과는 mc/event/turn-log 로 따로 올라와 패널의 턴 수가 올라간다. */
async function passTurn(): Promise<void> {
  try {
    await passRefereeTurn()
  } catch (error) {
    if (isApiError(error) && error.is('MC_SESSION_NOT_FOUND')) {
      showToast('AI 심판이 종료되었습니다. 다시 켜주세요.', 'danger')
      return
    }
    showToast(toMessage(error, '턴을 넘기지 못했습니다.'), 'danger')
  }
}

/**
 * 껐다가 다시 켜기 -> 권유 팝업을 다시 연다.
 *
 * 바로 시작하지 않는 이유는 인원을 다시 물어야 하기 때문이다. 판마다 사람이 늘거나
 * 빠지는데 지난 값을 재사용하면 좌석 수가 틀리고, 그러면 진행자의 첫 등록 판정이
 * 통째로 엉뚱한 사람에게 붙는다. 인원을 묻는 UI 를 두 군데 두지 않으려는 이유이기도 하다.
 */
function restartReferee(): void {
  reopenRefereePrompt()
}

/** 심판 끄기. 서버가 거절해도 패널은 이미 닫힌 뒤라 안내만 남긴다. */
async function stopRefereeAndNotify(): Promise<void> {
  try {
    await stopReferee()
    showToast('AI 심판을 껐습니다.')
  } catch (error) {
    showToast(toMessage(error, 'AI 심판 종료를 전달하지 못했습니다.'), 'danger')
  }
}
const {
  isOpen: isAssistantOpen,
  isListening,
  isStarting,
  isThinking,
  statusText,
  answer: ruleAnswer,
  error: assistantError,
  ask: askRule,
  close: closeAssistant,
  clearError: clearAssistantError,
} = useRuleAssistant()

/**
 * 시작 요청은 성공했는데 qna/ready 가 안 온 경우처럼, 호출 시점 이후에 터지는 실패다.
 * (호출 즉시 실패는 askAssistant 의 catch 가 처리한다)
 */
watch(assistantError, (message) => {
  if (!message) return
  showToast(message, 'danger')
  clearAssistantError()
})

/** 룰 설명 시작. 실제 '듣는 중' 전환은 qna/ready 를 받아야 일어난다. */
async function askAssistant(): Promise<void> {
  try {
    await askRule()
  } catch (error) {
    if (isApiError(error) && error.is('NO_ACTIVE_RENT')) {
      showToast(
        '대여 중인 게임이 없습니다. 게임을 먼저 대여해주세요.',
        'danger',
      )
      return
    }
    showToast(toMessage(error, '음성 도우미를 시작하지 못했습니다.'), 'danger')
  }
}

const filter = ref(createEmptyFilter())
const isCancelModalOpen = ref(false)
/** 반납/꺼내기 안내를 띄울 대여 건 */
const guideRent = ref<RoomRent | null>(null)

const visibleGames = computed(() => filterGames(filter.value))

onMounted(async () => {
  // 대여 목록보다 먼저 물어본다. 순서가 뒤집히면 이미 심판이 도는 방에
  // 권유 팝업이 잠깐 떴다 사라진다(useAiReferee 가 isRestored 로 한 번 더 막는다).
  void restoreReferee()
  await load()
  // 새로고침 후에도 서버에 남아 있는 예약·대여 상태를 되살린다
  void restore()
  void loadRents()
})

function openDetail(game: BoardGame): void {
  router.push({ name: 'game-detail', params: { id: game.id } })
}

function resetFilter(): void {
  filter.value = createEmptyFilter()
}

/**
 * 대여 가능 여부는 목록 조회 시점의 스냅샷이라 실제 요청 시점에는 틀릴 수 있다.
 * 서버가 알려준 코드로 반대 경로를 한 번만 다시 시도한다(retried 가드로 핑퐁 방지).
 */
async function handleAction(game: BoardGame, retried = false): Promise<void> {
  try {
    if (game.available) {
      const created = await rentGame(game.id)
      // 폴링을 기다리지 않고 카드를 '대여 완료'로 바꾼다
      remember(created)
      showToast(`'${game.name}' 대여가 완료되었습니다.`)
      return
    }

    if (reservation.value && reservation.value.gameId !== game.id) {
      showToast('한 방에서는 한 개의 게임만 예약할 수 있습니다.', 'danger')
      return
    }

    const created = await reserve(game)
    showToast(
      created.waitingRank
        ? `'${game.name}' 예약 완료. 대기 ${created.waitingRank}번째입니다.`
        : `'${game.name}' 예약 완료. 다른 팀이 반납하면 알려드립니다.`,
    )
  } catch (error) {
    if (!isApiError(error)) {
      showToast('요청을 처리하지 못했습니다.', 'danger')
      return
    }

    if (!retried && error.is('BOARD_GAME_OUT_OF_STOCK')) {
      // 목록이 낡았다. 재고가 없으므로 예약 경로로 재시도한다.
      await handleAction({ ...game, available: false, availableCount: 0 }, true)
      return
    }

    if (!retried && error.is('RESERVATION_NOT_NEEDED')) {
      // 그 사이 재고가 생겼다. 예약이 아니라 대여를 해야 한다.
      await handleAction({ ...game, available: true, availableCount: 1 }, true)
      return
    }

    if (error.is('ALREADY_RENTED')) {
      // 우리 방이 이미 들고 있는 게임이다. 버튼이 안 보여야 정상이라 목록이 낡은 것 —
      // 서버 상태를 다시 받아오면 카드가 '사용 중 / 꺼내기 대기'로 바뀐다.
      showToast(
        `'${game.name}' 은 이미 우리 방이 대여한 게임입니다.`,
        'danger',
      )
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
    void refresh()
    void refreshRents()
  }
}

async function confirmCancel(): Promise<void> {
  const name = reservation.value?.gameName ?? ''

  try {
    await cancel()
    showToast(`'${name}' 예약을 취소했습니다.`, 'danger')
  } catch (error) {
    // 방이 퇴실 처리되면 서버가 예약을 이미 CANCELLED 로 바꿔놓는다.
    if (
      isApiError(error) &&
      error.is('RESERVATION_NOT_CANCELABLE', 'RESERVATION_NOT_FOUND')
    ) {
      clearLocal()
      showToast('예약이 이미 종료되었습니다.', 'danger')
    } else {
      showToast(toMessage(error, '예약을 취소하지 못했습니다.'), 'danger')
    }
  } finally {
    isCancelModalOpen.value = false
    void refresh()
  }
}

/**
 * 반납 알림에서 '지금 대여'.
 *
 * 평범한 대여와 같은 요청이라 handleAction 의 성공 문구를 그대로 쓴다.
 * 알림이 사본을 붙잡아 두지는 않으므로, 답하는 사이 다른 방이 먼저 가져갔을 수 있다 —
 * 그때 예약은 서버에 그대로 남아 있어(다음 반납 때 다시 알림이 온다) 배너를 되살린다.
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
      void restore()
      return
    }
    showToast(toMessage(error, '대여하지 못했습니다.'), 'danger')
    void restore()
  } finally {
    void refresh()
    void refreshRents()
  }
}

/** 반납 알림에서 '예약 취소'. 서버가 곧바로 다음 대기 팀에게 알림을 넘긴다. */
async function dismissReservationAlert(): Promise<void> {
  const name = returnAlert.value?.gameName ?? ''
  try {
    await dismissAlert()
    showToast(`'${name}' 예약을 취소했습니다.`, 'danger')
  } catch (error) {
    showToast(toMessage(error, '예약을 취소하지 못했습니다.'), 'danger')
    void restore()
  } finally {
    void refresh()
  }
}

/** 답하지 않아 서버가 예약을 취소한 경우 (팝업은 스스로 닫힌 뒤다) */
watch(expiredGameName, (name) => {
  if (!name) return
  showToast(`'${name}' 예약이 시간 초과로 취소되었습니다.`, 'danger')
  clearExpired()
  void refresh()
})
</script>

<template>
  <TabletFrame>
    <AppHeader />

    <div class="flex min-h-0 flex-1 flex-col gap-3 px-5 pt-3.5">
      <RoomStatusBar
        v-if="rents.length > 0 || reservation"
        :rents="rents"
        :reservation="reservation"
        @guide="guideRent = $event"
        @cancel-reservation="isCancelModalOpen = true"
      />

      <GameSearchBar
        v-model:keyword="filter.keyword"
        @ask-rule="askAssistant"
      />

      <GameFilterChips
        v-model:category="filter.category"
        v-model:quick="filter.quick"
        :options="categoryOptions"
      />

      <div class="flex shrink-0 items-baseline gap-2">
        <strong class="text-[13px] font-bold text-ink">
          {{ visibleGames.length }}개의 게임
        </strong>
        <span v-if="visibleGames.length" class="text-xs text-muted">
          카드를 누르면 규칙 요약을 볼 수 있어요
        </span>
      </div>

      <div class="custom-scroll min-h-0 flex-1 overflow-y-auto pb-4">
        <p
          v-if="isLoading && games.length === 0"
          class="py-16 text-center text-[13px] text-muted"
        >
          게임 목록을 불러오는 중입니다...
        </p>

        <p
          v-else-if="loadError"
          class="rounded-card border border-line-soft bg-danger-bg py-16 text-center text-[13px] font-semibold text-danger"
        >
          {{ loadError }}
        </p>

        <div
          v-else-if="visibleGames.length === 0"
          class="flex flex-col items-center gap-2.5 rounded-card border border-line-soft bg-surface py-14 text-center"
        >
          <span class="text-[15px] font-semibold text-ink">
            조건에 맞는 게임이 없습니다
          </span>
          <span class="text-[13px] text-subtle">
            필터를 지우면 오늘 대여 가능한 게임 전체를 볼 수 있습니다.
          </span>
          <button
            type="button"
            class="mt-2 h-11 rounded-full bg-ink px-5 text-sm font-semibold text-surface transition hover:opacity-90"
            @click="resetFilter"
          >
            필터 지우기
          </button>
        </div>

        <div v-else class="grid grid-cols-2 gap-3">
          <GameCard
            v-for="game in visibleGames"
            :key="game.id"
            :game="game"
            :rent="rentFor(game.id)"
            :reserved="isReserved(game.id)"
            :waiting-rank="isReserved(game.id) ? (reservation?.waitingRank ?? null) : null"
            @detail="openDetail"
            @action="handleAction"
            @guide="guideRent = $event"
          />
        </div>
      </div>
    </div>

    <template #overlay>
      <ToastMessage v-if="toast" :toast="toast" />

      <CabinetGuideModal
        v-if="guideRent"
        :rent="guideRent"
        :using-rent="usingRent"
        @close="guideRent = null"
      />

      <RuleAssistantOverlay
        v-if="isAssistantOpen"
        :listening="isListening"
        :starting="isStarting"
        :thinking="isThinking"
        :status-text="statusText"
        :answer="ruleAnswer"
        @close="closeAssistant"
        @again="askAssistant"
      />

      <AiRefereePanel
        v-if="refereePanelMode"
        :mode="refereePanelMode"
        :board-game-name="refereeGameName"
        :turn-count="refereeTurnCount"
        :violation="refereeViolation"
        :player-count="refereePlayerCount"
        :current-seat="refereeCurrentSeat"
        :finished-seats="refereeFinishedSeats"
        :pending="isRefereeBusy"
        @start="restartReferee"
        @toggle="toggleReferee"
        @pass-turn="passTurn"
        @finish-player="finishRefereeSeat"
        @open-history="openTurnLog"
        @dismiss-violation="dismissRefereeViolation"
        @stop="stopRefereeAndNotify"
      />

      <TurnLogHistoryModal
        v-if="isTurnLogOpen"
        :log="refereeLatestTurn"
        :loading="isRefereeTurnLoading"
        :error="refereeTurnLoadError"
        @close="closeTurnLog"
      />

      <AiRefereePrompt
        v-if="isRefereePrompting"
        :game-name="refereePromptGameName"
        :min-players="refereePromptGame?.minPlayers ?? null"
        :max-players="refereePromptGame?.maxPlayers ?? null"
        :pending="isRefereeBusy"
        @dismiss="dismissReferee"
        @confirm="startReferee"
      />

      <CancelReservationModal
        v-if="isCancelModalOpen && reservation"
        :game-name="reservation.gameName"
        :pending="isSubmitting"
        @keep="isCancelModalOpen = false"
        @confirm="confirmCancel"
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

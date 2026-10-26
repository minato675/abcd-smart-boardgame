import { computed, ref } from 'vue'
import {
  SHORT_PLAY_MINUTES,
  type BoardGame,
  type GameCategory,
  type GameFilter,
} from '@/types/game'
import { fetchGames } from '@/api/games'
import { toMessage } from '@/api/http'
import { onBoardGameEvent } from '@/mqtt/roomMqtt'

/** 이 시간 안에 다시 부르면 재조회를 건너뛴다 */
const STALE_MS = 10_000

const games = ref<BoardGame[]>([])
const isLoading = ref(false)
const loadError = ref<string | null>(null)
let lastLoadedAt = 0

interface LoadOptions {
  /** 캐시 무시 */
  force?: boolean
  /** 로딩/에러 상태를 건드리지 않는다 (백그라운드 갱신용) */
  silent?: boolean
}

async function load({ force, silent }: LoadOptions = {}): Promise<void> {
  if (!force && lastLoadedAt && Date.now() - lastLoadedAt < STALE_MS) return

  if (!silent) {
    isLoading.value = true
    loadError.value = null
  }

  try {
    games.value = await fetchGames()
    lastLoadedAt = Date.now()
  } catch (error) {
    // silent 갱신이 실패하면 직전 목록을 그대로 유지한다 —
    // 화면이 갑자기 에러 상태로 깜빡이는 것보다 낫다.
    if (!silent) {
      loadError.value = toMessage(error, '게임 목록을 불러오지 못했습니다.')
    }
  } finally {
    if (!silent) isLoading.value = false
  }
}

/** 대여/예약 후 availableCount 를 다시 맞춘다 */
function refresh(): Promise<void> {
  return load({ force: true, silent: true })
}

/**
 * 다른 방의 대여/반납으로 재고가 바뀌었다는 방송. 폴링이 아니라 서버 푸시라
 * 모듈 스코프에 한 번만 등록한다 — 컴포넌트가 몇 개 붙든 갱신은 한 번만 일어나야 한다.
 *
 * force 로 STALE_MS 캐시를 무시한다 — 방금 내가 대여해서 캐시가 갱신된 직후라도
 * 남의 방 이벤트라면 반영해야 한다.
 */
onBoardGameEvent(() => {
  void load({ force: true, silent: true })
})

function matchesKeyword(game: BoardGame, keyword: string): boolean {
  if (!keyword) return true
  const needle = keyword.trim().toLowerCase()
  return (
    game.name.toLowerCase().includes(needle) ||
    game.categories.some((category) =>
      category.name.toLowerCase().includes(needle),
    )
  )
}

/**
 * 상황별 빠른 칩.
 * 값이 없는 게임(difficulty/playTime 이 null)은 숨기지 않는다 —
 * 서버가 아직 null 을 주는 경우가 많아 숨기면 목록이 텅 빈다.
 */
function matchesQuick(game: BoardGame, quick: GameFilter['quick']): boolean {
  if (quick === 'none') return true
  if (quick === 'easy') return game.difficulty === null || game.difficulty === 'EASY'
  if (quick === 'short') {
    return (
      game.playTimeMinutes === null || game.playTimeMinutes <= SHORT_PLAY_MINUTES
    )
  }
  return game.available
}

/** 게임 목록 캐시 + 필터링 */
export function useGames() {
  function filterGames(filter: GameFilter): BoardGame[] {
    return games.value.filter(
      (game) =>
        matchesKeyword(game, filter.keyword) &&
        (filter.category === 'all' ||
          game.categories.some((category) => category.id === filter.category)) &&
        matchesQuick(game, filter.quick),
    )
  }

  function findGame(id: number): BoardGame | undefined {
    return games.value.find((game) => game.id === id)
  }

  /**
   * 필터 칩에 쓸 카테고리 목록.
   * 백엔드에 카테고리 조회 엔드포인트가 없어 로드된 게임에서 역산한다
   * (게임이 하나도 없는 카테고리는 칩에 나타나지 않는다).
   */
  const categoryOptions = computed<GameCategory[]>(() => {
    const unique = new Map<number, GameCategory>()
    for (const game of games.value) {
      for (const category of game.categories) {
        if (!unique.has(category.id)) unique.set(category.id, category)
      }
    }
    return [...unique.values()].sort((a, b) => a.name.localeCompare(b.name))
  })

  return {
    games: computed(() => games.value),
    isLoading: computed(() => isLoading.value),
    loadError: computed(() => loadError.value),
    categoryOptions,
    load,
    refresh,
    filterGames,
    findGame,
  }
}

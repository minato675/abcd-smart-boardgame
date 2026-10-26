import { computed, ref } from 'vue'
import type { RoomRent } from '@/types/game'
import { fetchActiveRents } from '@/api/games'

/**
 * 우리 방이 아직 반납하지 않은 게임.
 *
 * 화면이 '내가 쓰는 중' / '내가 대여했지만 안 꺼냄' / '다른 팀이 대여 중' 을 구분하는
 * 근거다. 서버는 이 목록에 있는 게임의 재대여·예약을 ALREADY_RENTED 로 거절하므로,
 * 여기 있는 게임에는 대여/예약 버튼을 아예 띄우지 않는다.
 *
 * 픽업(RENT→USING)과 반납(USING→RETURNED)은 태블릿이 아니라 **카드 태그 → MQTT →
 * 서버**에서 일어난다. 태블릿은 그 사실을 통보받을 방법이 없으므로, 화면 진입·대여·예약·
 * 반납 알림 등 상태가 바뀔 만한 시점마다 명시적으로 `load`/`refresh` 를 불러 다시 맞춘다.
 */
const rents = ref<RoomRent[]>([])

/**
 * 실패를 조용히 삼킨다 — 대여 목록을 못 불러왔다고 게임 목록 화면을 에러로 덮을 이유가 없다.
 * 이 경우 카드가 예전 상태를 그대로 보여주고, 잘못 누르면 서버가 409 로 막는다.
 */
async function load(): Promise<void> {
  try {
    rents.value = await fetchActiveRents()
  } catch {
    // 무시
  }
}

export function useRoomRents() {
  /** 이 게임을 우리 방이 들고 있는가 */
  function rentFor(gameId: number): RoomRent | null {
    return rents.value.find((rent) => rent.gameId === gameId) ?? null
  }

  /**
   * 대여 직후 응답을 바로 반영한다 — 서버를 다시 묻지 않고 카드가 즉시 바뀐다.
   *
   * 기존 'RENT' 항목은 교체한다. 서버 RentMapper.insert 가 방의 RENT 행을 UPDATE 로
   * 덮어쓰기 때문에, 꺼내지 않은 대여는 방에 하나만 존재한다.
   */
  function remember(created: RoomRent): void {
    rents.value = [
      created,
      ...rents.value.filter(
        (rent) => rent.status !== 'RENT' && rent.gameId !== created.gameId,
      ),
    ]
  }

  return {
    rents: computed(() => rents.value),
    /** 지금 테이블에서 쓰고 있는 게임 (없으면 null) */
    usingRent: computed(
      () => rents.value.find((rent) => rent.status === 'USING') ?? null,
    ),
    rentFor,
    remember,
    load,
    refresh: load,
  }
}

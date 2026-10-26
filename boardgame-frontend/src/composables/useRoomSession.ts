import { computed, onUnmounted, ref } from 'vue'
import { fetchRoomStartedAt } from '@/api/games'
import { CAFE_NAME, ROOM_LABEL } from '@/config/env'

const cafeName = ref(CAFE_NAME)
const roomName = ref(ROOM_LABEL)
/** room_usage 중 이 방의 가장 최근 start_time (epoch ms). 조회 전/이용 이력 없음이면 null. */
const startedAt = ref<number | null>(null)
/** 화면을 1초마다 다시 그리기 위한 트리거. 값 자체는 의미가 없다. */
const tick = ref(0)

let subscriberCount = 0
let timerId: ReturnType<typeof setInterval> | null = null
let startedAtRequested = false

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/**
 * 헤더에 표시되는 방 정보와 이용 시간.
 * 모듈 스코프 상태이므로 화면을 이동해도 타이머와 입실 시각이 이어진다.
 *
 * 이용 시간은 태블릿 가동 시간이 아니라 room_usage 에서 이 방 번호로 가장 최근
 * start_time 을 조회해(GET /admin/room/usage) 그 시각부터 지금까지로 계산한다.
 */
export function useRoomSession() {
  subscriberCount += 1

  if (!timerId) {
    timerId = setInterval(() => {
      tick.value += 1
    }, 1000)
  }

  if (!startedAtRequested) {
    startedAtRequested = true
    fetchRoomStartedAt()
      .then((value) => {
        startedAt.value = value
      })
      .catch(() => {
        // 조회 실패 시 입실 시각을 알 수 없으므로 00:00:00 으로 둔다.
        // 태블릿 가동 시간 같은 임의 값으로 대체하지 않는다.
      })
  }

  onUnmounted(() => {
    subscriberCount -= 1
    if (subscriberCount === 0 && timerId) {
      clearInterval(timerId)
      timerId = null
    }
  })

  const elapsedLabel = computed(() => {
    tick.value

    if (startedAt.value === null) return '00 : 00 : 00'

    const total = Math.max(0, Math.floor((Date.now() - startedAt.value) / 1000))
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    const seconds = total % 60
    return `${pad(hours)} : ${pad(minutes)} : ${pad(seconds)}`
  })

  return { cafeName, roomName, elapsedLabel }
}

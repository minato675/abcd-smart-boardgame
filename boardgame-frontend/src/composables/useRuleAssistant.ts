import { computed, ref } from 'vue'
import { startQna } from '@/api/qna'
import { onRoomEvent } from '@/mqtt/roomMqtt'
import { useTts } from '@/composables/useTts'
import { useNotificationSound } from '@/composables/useNotificationSound'

const { speak } = useTts()
const { playDing } = useNotificationSound()

/**
 * 규칙 도우미.
 *
 * 마이크는 게임을 '검색'하지 않는다 — 규칙·점수 계산·애매한 상황을 물어보고
 * 답을 받는 용도다.
 *
 * 화면 전환은 브로커에서 오는 방 이벤트가 끌고 간다:
 *
 *   버튼 클릭  -> POST /qna/start        -> 'starting'  (준비 중)
 *   호출어 인식 -> (서버가 대신 시작)      -> 'starting' 없이 바로
 *   /room/{room}/qna/ready               -> 'listening' (음성인식 중, 알림음)
 *   /room/{room}/qna/thinking            -> 'thinking'  (답변 분석 중)
 *   /room/{room}/qna/res                 -> 'answer'    (답변 표시 + TTS 로 읽어줌)
 *
 * 호출어로 시작하면 태블릿은 시작 요청의 당사자가 아니라서, ready 를 받는 것이
 * QnA 가 돌기 시작했다는 사실을 아는 유일한 경로다. 그래서 ready 는 phase 와
 * 무관하게 항상 오버레이를 연다. thinking 도 같은 이유로 phase 를 따지지 않는다.
 * ready 알림음도 이 경로 하나로 버튼 클릭·호출어 두 케이스를 모두 커버한다.
 */
export type AssistantPhase =
  | 'idle'
  | 'starting'
  | 'listening'
  | 'thinking'
  | 'answer'

export interface RuleAnswer {
  /** QnA 세션 식별자 */
  transactionId: string
  /** 인식된 질문 (페이로드의 req) */
  question: string
  /** 답변 본문 (페이로드의 res) */
  answer: string
}

/**
 * /room/{roomNumber}/qna/res 페이로드를 화면용으로 바꾼다.
 *
 * 브로커에서 바로 받는 값이라 스키마를 신뢰할 수 없다. res 가 없으면 보여줄 게
 * 없으므로 버린다(req 는 인식이 비어도 답이 나올 수 있어 없어도 통과시킨다).
 */
function toRuleAnswer(payload: unknown): RuleAnswer | null {
  if (typeof payload !== 'object' || payload === null) return null

  const { transactionId, req, res } = payload as Record<string, unknown>
  if (typeof res !== 'string' || !res) return null

  return {
    transactionId: typeof transactionId === 'string' ? transactionId : '',
    question: typeof req === 'string' ? req : '',
    answer: res,
  }
}

/**
 * 시작 요청은 받아들여졌는데 ready 가 이만큼 안 오면 포기한다.
 * QnA 서버가 죽어 있을 때 '준비 중' 화면에 갇히는 것을 막는다.
 */
const READY_TIMEOUT_MS = 5000

const phase = ref<AssistantPhase>('idle')
const answer = ref<RuleAnswer | null>(null)
/** 비동기로 뒤늦게 터진 실패. 화면이 감시하다 토스트로 띄운다. */
const error = ref<string | null>(null)

let readyTimerId: ReturnType<typeof setTimeout> | null = null

function clearReadyTimer(): void {
  if (readyTimerId) clearTimeout(readyTimerId)
  readyTimerId = null
}

function reset(): void {
  clearReadyTimer()
  phase.value = 'idle'
  answer.value = null
}

/**
 * QnA 서버 준비 완료. 여기서부터 실제로 말을 듣는다.
 *
 * 모듈 스코프에 한 번만 등록한다 — 컴포넌트가 몇 개 붙든 전환은 한 번만 일어나야 한다.
 */
onRoomEvent('qna/ready', () => {
  clearReadyTimer()
  error.value = null
  answer.value = null
  phase.value = 'listening'
  playDing()
})

/**
 * 발화 인식 완료, 답변 분석 중. 마이크는 이미 닫혔으니 웨이브 대신
 * '분석 중' 화면으로 넘어간다.
 *
 * ready 와 마찬가지로 phase 와 무관하게 반영한다 — 놓친 이벤트 뒤에도
 * 최신 진행 상태를 보여주는 편이 화면이 멈춰 보이는 것보다 낫다.
 */
onRoomEvent('qna/thinking', () => {
  clearReadyTimer()
  error.value = null
  answer.value = null
  phase.value = 'thinking'
})

/**
 * 답변 도착. 이번 질문은 여기서 끝난다.
 *
 * ready 를 놓친 채(연결이 늦게 붙는 등) res 만 받아도 답은 보여줘야 하므로
 * phase 를 따지지 않는다. 화면을 닫아둔 상태에서 오면 다시 열리는데,
 * 물어본 답이 뒤늦게라도 뜨는 편이 조용히 사라지는 것보다 낫다.
 *
 * wake word 는 서버가 같은 이벤트를 받아 start-listen 으로 되살린다
 * (inte-server QnaService.result). 태블릿이 할 일은 표시뿐이다.
 */
onRoomEvent('qna/res', (payload) => {
  const received = toRuleAnswer(payload)
  if (!received) {
    console.warn('[qna] res 페이로드를 해석할 수 없다', payload)
    return
  }

  clearReadyTimer()
  error.value = null
  answer.value = received
  phase.value = 'answer'
  speak(received.answer)
})

export function useRuleAssistant() {
  /**
   * 룰 설명 시작 요청.
   *
   * 성공해도 아직 듣는 중이 아니다 — ready 가 와야 'listening' 이 된다.
   *
   * @throws ApiError 서버가 거절한 경우(NO_ACTIVE_RENT 등). 화면이 문구를 정한다.
   */
  async function ask(): Promise<void> {
    clearReadyTimer()
    error.value = null
    answer.value = null
    phase.value = 'starting'

    try {
      await startQna()
    } catch (requestError) {
      reset()
      throw requestError
    }

    readyTimerId = setTimeout(() => {
      readyTimerId = null
      if (phase.value !== 'starting') return
      reset()
      error.value = '음성 도우미를 시작하지 못했습니다. 잠시 후 다시 시도해주세요.'
    }, READY_TIMEOUT_MS)
  }

  function close(): void {
    reset()
    error.value = null
  }

  /** 화면이 토스트로 띄운 뒤 호출한다 */
  function clearError(): void {
    error.value = null
  }

  return {
    phase: computed(() => phase.value),
    answer: computed(() => answer.value),
    error: computed(() => error.value),
    isOpen: computed(() => phase.value !== 'idle'),
    // 준비 중에도 웨이브를 보여준다. 오버레이는 listening / thinking / answer
    // 세 갈래뿐이라 여기서 false 를 주면 본문이 빈 채로 뜬다.
    isListening: computed(
      () => phase.value === 'starting' || phase.value === 'listening',
    ),
    /** ready 를 아직 못 받은 상태. 타이틀은 이걸로 '듣고 있어요' 와 구분한다. */
    isStarting: computed(() => phase.value === 'starting'),
    isThinking: computed(() => phase.value === 'thinking'),
    statusText: computed(() => {
      if (phase.value === 'starting') return '음성 도우미를 준비하고 있어요'
      if (phase.value === 'thinking') return '답변을 분석하고 있어요'
      return '궁금한 규칙을 편하게 말해보세요'
    }),
    ask,
    close,
    clearError,
  }
}

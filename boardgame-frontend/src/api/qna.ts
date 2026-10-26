import { ROOM_NUMBER } from '@/config/env'
import { request } from './http'

/**
 * 룰 설명(QnA) API.
 *
 * 시작 요청만 REST 다. 그 뒤 진행 상황(qna/ready 등)은 브로커에서 직접 받는다 —
 * src/mqtt/roomMqtt.ts 참고.
 */

export interface QnaStartResult {
  /** 서버가 발급한 QnA 세션 식별자 */
  transactionId: string
  roomNumber: string
}

/**
 * QnA 서버를 깨운다. 서버가 방이 대여 중인 게임을 찾아 /room/{roomNumber}/qna/start 로
 * 넘기고, QnA 서버가 준비되면 /room/{roomNumber}/qna/ready 가 올라온다.
 *
 * **이 응답은 '요청을 받았다' 까지다.** 실제로 들을 준비가 됐는지는 qna/ready 로만 알 수 있다.
 *
 * 실패 코드: NO_ACTIVE_RENT(대여 중인 게임이 없어 설명할 대상이 없다)
 */
export function startQna(): Promise<QnaStartResult> {
  return request<QnaStartResult>('/qna/start', {
    method: 'POST',
    query: { roomNumber: ROOM_NUMBER },
  })
}

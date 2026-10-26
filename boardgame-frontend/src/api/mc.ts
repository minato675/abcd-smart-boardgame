import { ROOM_NUMBER } from '@/config/env'
import { request } from './http'

/**
 * AI 심판(진행자) API.
 *
 * 시작 요청만 REST 다. 이후 진행 상황(mc/event/turn-log, mc/event/violation)은
 * 브로커에서 직접 받는다 - src/mqtt/roomMqtt.ts 참고.
 */

export interface McStartResult {
  /** 서버가 발급한 게임 세션 식별자 */
  sessionId: string
  /** 서버가 대여 목록에서 고른 게임. 태블릿이 고른 것과 다를 수 있다. */
  boardGameName: string
  roomNumber: string
  /** 세션에 실제로 잡힌 인원. 이미 켜져 있었으면 요청한 값과 다를 수 있다. */
  playerCount: number
  /** 지금 차례인 좌석 */
  currentSeat: number
}

/**
 * AI 심판을 켠다. 어떤 게임인지는 서버가 방의 대여 목록에서 고른다
 * (태블릿이 보내지 않는다 - 낡은 목록으로 엉뚱한 게임을 지정하지 않도록).
 *
 * 인원만은 태블릿이 보낸다. 카메라는 테이블만 보고 사람은 못 세는데, 진행자가
 * 루미큐브 첫 등록 30점처럼 사람마다 갈리는 규칙을 보려면 좌석 수를 알아야 한다.
 *
 * 실패 코드: NO_ACTIVE_RENT(대여 중인 게임이 없어 심판할 대상이 없다),
 *           INVALID_PLAYER_COUNT(이 게임의 인원 범위 밖)
 */
export function startMc(playerCount: number): Promise<McStartResult> {
  return request<McStartResult>('/mc/start', {
    method: 'POST',
    query: { roomNumber: ROOM_NUMBER, playerCount },
  })
}

/** 차례가 한 번 넘어간 결과 (턴 넘기기 / 다 냈어요 공통) */
export interface McTurnResult {
  /** 방금 차례를 마친 좌석 */
  seat: number
  /** 다음 차례 좌석. 세션이 끝났으면 0 */
  currentSeat: number
  /** 아직 손패를 다 내지 않은 인원 */
  remainingPlayers: number
  /** 남은 사람이 하나뿐이라 서버가 세션까지 끝냈는지 */
  sessionEnded: boolean
}

/**
 * 턴 넘기기. 진행자에게 테이블을 다시 읽으라고 지시한다.
 *
 * sessionId 도 좌석도 보내지 않는다 - 서버가 둘 다 들고 있다.
 * 분석 결과는 mc/event/turn-log 로 따로 올라오고, 이 응답은 좌석 회전 결과만 준다.
 *
 * 좌석을 화면에서 따로 굴리지 않는 이유: 끝난 사람 건너뛰기 같은 규칙을 양쪽에
 * 두면 언젠가 어긋나고, 그러면 진행자에게 가는 좌석과 화면의 좌석이 달라진다.
 *
 * 실패 코드: MC_SESSION_NOT_FOUND(진행 중인 심판이 없다 - 서버 재배포 등)
 */
export function analyzeMc(): Promise<McTurnResult> {
  return request<McTurnResult>('/mc/analyze', {
    method: 'POST',
    query: { roomNumber: ROOM_NUMBER },
  })
}

/**
 * 지금 차례인 사람이 손패를 다 냈다. 그 좌석을 차례에서 빼고 다음 사람에게 넘긴다.
 *
 * 카메라는 손패를 못 보므로 이건 사람이 알려주는 수밖에 없다.
 * 남은 사람이 하나뿐이 되면 서버가 세션까지 끝내고 sessionEnded=true 로 알려준다.
 *
 * 실패 코드: MC_SESSION_NOT_FOUND
 */
export function finishPlayerMc(): Promise<McTurnResult> {
  return request<McTurnResult>('/mc/player-finish', {
    method: 'POST',
    query: { roomNumber: ROOM_NUMBER },
  })
}

/**
 * 심판 끄기.
 *
 * 진행 중인 세션이 없어도 성공한다 - 끄는 요청은 "꺼진 상태로 만들어라" 라는 뜻이라
 * 이미 꺼져 있으면 목적이 달성된 것이다. 화면은 결과와 무관하게 패널을 닫으면 된다.
 */
export function finishMc(): Promise<void> {
  return request<void>('/mc/finish', {
    method: 'POST',
    query: { roomNumber: ROOM_NUMBER },
  })
}

/** 진행 중인 AI 심판 세션 */
export interface McSession {
  sessionId: string
  boardGameName: string
  /** 지금까지 기록된 마지막 턴 번호. 아직 없으면 0. */
  turnNo: number
  /** 이 판을 하는 사람 수 */
  playerCount: number
  /** 지금 차례인 좌석 */
  currentSeat: number
  /** 손패를 다 낸 좌석 (완료 순서) */
  finishedSeats: number[]
}

/**
 * 이 방에 진행 중인 심판이 있는지 묻는다.
 *
 * sessionId 를 태블릿이 보관하지 않는 이유이기도 하다 - 새로고침에 잃고,
 * localStorage 에 넣어도 서버가 재배포되면 죽은 값을 들고 있게 된다.
 * 서버가 유일한 근거라 매번 묻는다.
 *
 * 진행 중인 세션이 없으면 본문이 비어 undefined 가 온다.
 */
export function fetchMcSession(): Promise<McSession | undefined> {
  return request<McSession | undefined>('/mc/session', {
    query: { roomNumber: ROOM_NUMBER },
  })
}

/** 마지막으로 기록된 테이블 상태 한 턴 */
export interface LatestTurnLog {
  turnNo: number
  tileCount: number
  /** 바깥이 세트, 안쪽이 세트 안 타일. 둘 다 순서가 의미를 갖는다. */
  table: { color: string; number: number }[][]
}

/**
 * '이전 화면 보기'. 진행 중인 세션에서 turn_no 가 가장 큰 턴을 가져온다.
 *
 * MQTT 로 받아 들고 있는 목록이 아니라 서버 DB 를 읽는다 - 새로고침한 뒤에도 복원돼야 한다.
 * 아직 기록된 턴이 없으면 본문이 비어 undefined 가 온다.
 *
 * 실패 코드: MC_SESSION_NOT_FOUND(진행 중인 심판이 없다)
 */
export function fetchLatestTurnLog(): Promise<LatestTurnLog | undefined> {
  return request<LatestTurnLog | undefined>('/mc/turn-log', {
    query: { roomNumber: ROOM_NUMBER },
  })
}

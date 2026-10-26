import { API_BASE_URL } from '@/config/env'
import type {
  ActiveRentDto,
  BoardGameDetailDto,
  BoardGameListDto,
  RentDto,
  ReservationDto,
  RoomUsageDto,
} from './dto'
import {
  DIFFICULTIES,
  type BoardGame,
  type BoardGameDetail,
  type Difficulty,
  type GameStep,
  type RentStatus,
  type Reservation,
  type ReservationStatus,
  type RoomRent,
} from '@/types/game'

/**
 * 서버 DTO → 도메인 타입 변환.
 *
 * 필드명이 어긋나는 지점(boardGameId→id, imageUrl→thumbnailUrl,
 * playTime→playTimeMinutes, availableCount→available)을 한곳에 모아둔다.
 */

/**
 * DB 가 VARCHAR 이라 enum 밖의 값이 올 수 있고, 현재 서버는 아예 null 을 준다.
 * 임의로 'NORMAL' 로 채우면 화면이 '보통'이라고 거짓말을 하므로 null 로 둔다
 * (difficultyLabel 이 '정보 없음'으로 표시한다).
 */
function toDifficulty(raw: string | null): Difficulty | null {
  if (!raw) return null
  return (DIFFICULTIES as readonly string[]).includes(raw)
    ? (raw as Difficulty)
    : null
}

const RESERVATION_STATUSES: readonly string[] = [
  'WAITING',
  'FULFILLED',
  'CANCELLED',
]

function toReservationStatus(raw: string): ReservationStatus {
  return RESERVATION_STATUSES.includes(raw)
    ? (raw as ReservationStatus)
    : 'CANCELLED'
}

/**
 * board_game.image_url 은 관리되지 않는 자유 텍스트다.
 * 상대경로면 프론트 오리진이 아니라 API 오리진 기준으로 붙여야 한다.
 *
 * 참고: 현재 백엔드에는 이미지 업로드/서빙 핸들러가 아예 없어서
 * 상대경로 값은 어차피 404 가 된다 — GameThumbnail 의 플레이스홀더로 폴백된다.
 */
function resolveImageUrl(raw: string | null): string | null {
  if (!raw) return null
  if (/^(https?:)?\/\//.test(raw) || raw.startsWith('data:')) return raw
  return `${API_BASE_URL}${raw.startsWith('/') ? '' : '/'}${raw}`
}

/** 줄머리의 '1.', '2)', '-', '•', '*' 같은 장식 제거 */
const BULLET_PREFIX = /^\s*(?:\d+\s*[.)]|[-•*·])\s*/

/** '제목: 설명' 으로 분리할 때 제목이 이보다 길면 그냥 본문으로 본다 */
const MAX_TITLE_LENGTH = 24

/**
 * howToPlay 를 '게임 방법' 단계 목록으로 쪼갠다.
 *
 * 서버 컬럼이 포맷 합의 없는 free-form TEXT 라 관용적으로 파싱한다:
 * 줄바꿈으로 나누고, 줄머리 장식을 떼고, 앞부분에 콜론이 있으면 제목으로 본다.
 * 백엔드에서 포맷이 확정되면 이 함수가 추측이 아니라 규격이 된다.
 */
export function parseHowToPlay(raw: string | null): GameStep[] {
  if (!raw) return []

  return raw
    .split(/\r?\n/)
    .map((line) => line.replace(BULLET_PREFIX, '').trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const separator = Math.min(
        ...[line.indexOf(':'), line.indexOf('：')]
          .filter((index) => index > 0)
          .concat(Number.POSITIVE_INFINITY),
      )

      if (separator <= MAX_TITLE_LENGTH) {
        const description = line.slice(separator + 1).trim()
        // 콜론 뒤가 비어 있으면 제목만 있는 줄이므로 본문으로 취급한다
        if (description) {
          return { title: line.slice(0, separator).trim(), description }
        }
      }

      return { title: null, description: line }
    })
}

/**
 * 서버가 이름을 주지 않을 때 쓰는 표시값.
 * 도메인의 name 을 string 으로 유지해 모든 화면/토스트/aria-label 에서
 * null 검사를 반복하지 않아도 되게 한다.
 */
const UNNAMED_GAME = '이름 미등록'

export function toBoardGame(dto: BoardGameListDto): BoardGame {
  return {
    id: dto.boardGameId,
    name: dto.name ?? UNNAMED_GAME,
    categories: (dto.categories ?? []).map((category) => ({
      id: category.categoryId,
      name: category.name,
    })),
    minPlayers: dto.minPlayers,
    maxPlayers: dto.maxPlayers,
    playTimeMinutes: dto.playTime,
    difficulty: toDifficulty(dto.difficulty),
    description: dto.description ?? null,
    thumbnailUrl: resolveImageUrl(dto.imageUrl),
    totalCount: dto.totalCount,
    availableCount: dto.availableCount,
    available: dto.availableCount > 0,
  }
}

export function toBoardGameDetail(dto: BoardGameDetailDto): BoardGameDetail {
  return {
    // description 은 toBoardGame 이 이미 채운다 (목록/상세 공통 필드)
    ...toBoardGame(dto),
    howToPlay: dto.howToPlay,
    steps: parseHowToPlay(dto.howToPlay),
    waitingCount: dto.waitingCount,
  }
}

const RENT_STATUSES: readonly string[] = ['RENT', 'USING']

/**
 * 모르는 값이면 'RENT'(꺼내기 대기)로 본다.
 * 안 꺼낸 것으로 취급하는 쪽이 안전하다 — 반납 안내를 잘못 띄우지 않는다.
 */
function toRentStatus(raw: string): RentStatus {
  return RENT_STATUSES.includes(raw) ? (raw as RentStatus) : 'RENT'
}

export function toRoomRent(dto: ActiveRentDto): RoomRent {
  return {
    id: dto.rentId,
    gameId: dto.boardGameId,
    gameName: dto.boardGameName ?? UNNAMED_GAME,
    cabinetId: dto.cabinetId,
    status: toRentStatus(dto.status),
  }
}

/**
 * POST /rent 응답 → 방금 생긴 대여.
 * 대여 직후는 언제나 '꺼내기 대기'다 — 사물함은 카드를 태그해야 열린다.
 */
export function toCreatedRent(dto: RentDto): RoomRent {
  return {
    id: dto.rentId,
    gameId: dto.boardGameId,
    gameName: dto.boardGameName,
    cabinetId: dto.cabinetId,
    status: 'RENT',
  }
}

export function toReservation(dto: ReservationDto): Reservation {
  return {
    id: dto.reservationId,
    gameId: dto.boardGameId,
    gameName: dto.boardGameName ?? UNNAMED_GAME,
    status: toReservationStatus(dto.status),
    waitingRank: dto.waitingRank,
  }
}

/** LocalDateTime 문자열(타임존 표기 없음, KST) → epoch ms. 파싱 실패하면 null. */
function parseServerTime(raw: string | null): number | null {
  if (!raw) return null
  const parsed = Date.parse(raw)
  return Number.isNaN(parsed) ? null : parsed
}

/** GET /admin/room/usage 응답 → 이 방의 가장 최근 입실 시각(epoch ms). 없으면 null. */
export function toRoomStartedAt(dto: RoomUsageDto): number | null {
  return parseServerTime(dto.startTime)
}

/**
 * inte-server 응답 원본 shape. Java DTO 와 1:1 로 맞춘다.
 *
 * 화면 코드는 이 타입을 절대 직접 쓰지 않는다 — src/api/mappers.ts 가
 * src/types/game.ts 의 도메인 타입으로 변환한다. 서버가 필드명을 바꾸면
 * 여기와 mappers.ts 두 곳만 고치면 된다.
 *
 * MyBatis 의 map-underscore-to-camel-case 설정 때문에 응답은 모두 camelCase 다.
 * difficulty / status 는 DB VARCHAR 이므로 enum 이 아닌 string 으로 받고,
 * 좁히기는 mappers.ts 에서 방어적으로 처리한다.
 */

/** dto/CategoryResponse.java */
export interface CategoryDto {
  categoryId: number
  name: string
}

/**
 * dto/BoardGameListResponse.java
 *
 * 주의: 현재 서버는 boardGameId 와 categories 를 뺀 모든 필드를 null/0 으로 준다.
 * BoardGameMapper.xml 의 resultMap 이 nested <collection> 을 포함하는데
 * MyBatis 기본 autoMappingBehavior=PARTIAL 은 그런 resultMap 의 자동 매핑을
 * 끄기 때문이다(= 백엔드 버그). 그래서 nullable 범위를 넓게 잡아둔다.
 */
export interface BoardGameListDto {
  boardGameId: number
  name: string | null
  minPlayers: number | null
  maxPlayers: number | null
  /** 'EASY' | 'NORMAL' | 'HARD' */
  difficulty: string | null
  /** 분 단위 */
  playTime: number | null
  imageUrl: string | null
  /** 보유 사본 수 */
  totalCount: number
  /** status = 'AVAILABLE' 인 사본 수 */
  availableCount: number
  categories: CategoryDto[]
  description: string | null
}

/** dto/BoardGameDetailResponse.java */
export interface BoardGameDetailDto extends BoardGameListDto {
  howToPlay: string | null
  /** 이 게임을 기다리는 WAITING 예약 수 (방 무관, 전체) */
  waitingCount: number
}

/** dto/RentResponse.java */
export interface RentDto {
  rentId: number
  boardGameId: number
  boardGameName: string
  /** 실제로 배정된 물리 사본 id */
  boardGameItemId: number
  /** 열어야 하는 사물함 id */
  cabinetId: number
  roomNumber: string
  /** LocalDateTime ISO 문자열 */
  rentedAt: string
}

/**
 * dto/ActiveRentResponse.java — GET /rent 의 한 건.
 *
 * 방이 아직 반납하지 않은 대여다. RentDto 와 달리 status 가 있어서 '꺼내기 대기(RENT)'
 * 와 '사용 중(USING)' 을 구분할 수 있다.
 */
export interface ActiveRentDto {
  rentId: number
  boardGameId: number
  boardGameName: string | null
  boardGameItemId: number
  /** rent.board_game_item_id 를 LEFT JOIN 하므로 이론상 null 이 될 수 있다 */
  cabinetId: number | null
  /** 'RENT' | 'USING' */
  status: string
  rentedAt: string
}

/** dto/ReservationResponse.java */
export interface ReservationDto {
  reservationId: number
  boardGameId: number
  boardGameName: string | null
  roomNumber: string
  /** 'WAITING' | 'FULFILLED' | 'CANCELLED' */
  status: string
  reservedAt: string
  fulfilledAt: string | null
  cancelledAt: string | null
  /** 예약 생성 응답에만 채워지고 목록 조회에서는 항상 null */
  waitingRank: number | null
}

/** dto/RoomResponse.java */
export interface RoomDto {
  roomNumber: string
  capacity: number
  /** 'EMPTY' | 'USE' */
  status: string
}

/**
 * dto/RoomUsageResponse.java — GET /admin/room/usage 응답.
 *
 * startTime / endTime 은 Java LocalDateTime 이 그대로 직렬화된 값이라
 * 타임존 표기가 없는 `2026-08-03T14:05:12.482` 형태다(서버·태블릿이 같은 KST 라서
 * `new Date()`/`Date.parse` 로도 결과가 맞아떨어진다).
 */
export interface RoomUsageDto {
  roomUsageId: number | null
  roomNumber: string
  /** 이 방의 이용 이력이 한 건도 없으면 null */
  startTime: string | null
  /** null 이면 아직 이용 중 */
  endTime: string | null
  /** 'EMPTY' | 'USE' */
  roomStatus: string
}

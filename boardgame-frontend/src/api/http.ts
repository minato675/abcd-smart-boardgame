import { API_BASE_URL } from '@/config/env'

/**
 * inte-server 호출용 fetch 래퍼.
 *
 * 서버는 인증이 없고(요청 본문의 roomNumber 가 곧 신원), 성공 응답은 DTO 를
 * 그대로 돌려주며 실패 응답은 { code, message } 봉투로 돌려준다.
 * 참고: inte-server/src/main/java/com/ssafy/boardgame/common/GlobalExceptionHandler.java
 */

/**
 * 서버가 돌려주는 에러 코드.
 * inte-server/src/main/java/com/ssafy/boardgame/common/ErrorCode.java 와 1:1.
 */
export const API_ERROR_CODES = [
  'BOARD_GAME_NOT_FOUND',
  'ROOM_NOT_FOUND',
  'RESERVATION_NOT_FOUND',
  'RESERVATION_FORBIDDEN',
  'BOARD_GAME_OUT_OF_STOCK',
  'ALREADY_RENTED',
  'DUPLICATE_RESERVATION',
  'RESERVATION_NOT_NEEDED',
  'RESERVATION_NOT_CANCELABLE',
  'ROOM_NOT_IN_USE',
  'NO_ACTIVE_RENT',
  'MC_SESSION_NOT_FOUND',
  'INVALID_INPUT',
  'INVALID_PLAYER_RANGE',
  'INVALID_PLAYER_COUNT',
  'CATEGORY_NOT_FOUND',
  'INTERNAL_ERROR',
] as const

export type ApiErrorCode = (typeof API_ERROR_CODES)[number]

/** 서버가 응답 자체를 못 준 경우 (태블릿 Wi-Fi 끊김 등) */
export type ClientErrorCode = 'NETWORK_ERROR' | 'BAD_RESPONSE'

export type ErrorCode = ApiErrorCode | ClientErrorCode

export class ApiError extends Error {
  readonly status: number
  /** 서버가 준 code. 위 목록에 없는 값이 와도 문자열로 보존한다. */
  readonly code: ErrorCode | string

  constructor(status: number, code: ErrorCode | string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }

  /** 여러 코드 중 하나인지 확인. 화면에서 분기용으로 쓴다. */
  is(...codes: ErrorCode[]): boolean {
    return codes.some((code) => code === this.code)
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

/** 화면에 그대로 노출할 문구. 서버가 준 한국어 메시지를 우선한다. */
export function toMessage(error: unknown, fallback: string): string {
  if (isApiError(error)) return error.message || fallback
  return fallback
}

export type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  /** JSON 으로 직렬화해서 보낼 본문 */
  body?: unknown
  query?: Record<string, QueryValue>
  signal?: AbortSignal
}

/**
 * 빈 값은 아예 빼고 쿼리를 만든다.
 * 예: keyword 없이 부른 목록 조회가 순수 /boardgame 이 되어야
 * 서버가 조건 없는 '전체 목록'으로 처리한다.
 */
function buildQuery(query?: Record<string, QueryValue>): string {
  if (!query) return ''

  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }

  const serialized = params.toString()
  return serialized ? `?${serialized}` : ''
}

function parseErrorBody(
  status: number,
  raw: string,
): { code: string; message: string } {
  try {
    const parsed = JSON.parse(raw) as { code?: string; message?: string }
    if (parsed && typeof parsed.code === 'string') {
      return {
        code: parsed.code,
        message: parsed.message ?? '요청을 처리하지 못했습니다.',
      }
    }
  } catch {
    // JSON 이 아닌 에러 본문(프록시/nginx 오류 페이지 등)은 그대로 흘린다
  }
  return {
    code: 'BAD_RESPONSE',
    message: raw.trim() || `요청이 실패했습니다. (HTTP ${status})`,
  }
}

export async function request<T>(
  path: string,
  { method = 'GET', body, query, signal }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  // 본문이 있을 때만 Content-Type 을 붙인다 — 순수 GET 은 preflight 없이 나간다.
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}${buildQuery(query)}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(
      0,
      'NETWORK_ERROR',
      '서버에 연결할 수 없습니다. 네트워크 상태를 확인해주세요.',
    )
  }

  // /health 처럼 text/plain 을 주거나 빈 본문으로 성공하는 경우가 있어
  // 먼저 문자열로 읽고 나서 분기한다.
  const raw = await response.text()

  if (!response.ok) {
    const { code, message } = parseErrorBody(response.status, raw)
    throw new ApiError(response.status, code, message)
  }

  if (!raw) return undefined as T

  try {
    return JSON.parse(raw) as T
  } catch {
    throw new ApiError(
      response.status,
      'BAD_RESPONSE',
      '서버 응답을 해석할 수 없습니다.',
    )
  }
}

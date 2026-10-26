import { ROOM_NUMBER } from '@/config/env'
import type { RoomDto } from './dto'
import { request } from './http'

/**
 * 관리자용 입/퇴실 처리.
 *
 * 손님용 화면에 있을 기능이 아니지만, 방이 EMPTY 상태면 대여/예약이 전부
 * 409 ROOM_NOT_IN_USE 로 막혀서 개발 환경에서 앱을 쓸 수가 없다.
 * GameListView 의 dev 전용 버튼에서만 호출한다(import.meta.env.DEV 가드).
 *
 * 주의: status='EMPTY' 는 단순 상태 변경이 아니라 퇴실 처리다 —
 * 이 방이 대여한 모든 사본이 AVAILABLE 로 돌아가고 WAITING 예약이 취소된다.
 */
export function updateRoomStatus(status: 'EMPTY' | 'USE'): Promise<RoomDto> {
  return request<RoomDto>('/admin/room/update', {
    method: 'POST',
    body: { roomNumber: ROOM_NUMBER, status },
  })
}

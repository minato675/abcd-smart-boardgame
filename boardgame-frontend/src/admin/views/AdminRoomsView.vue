<script setup lang="ts">
/**
 * 실시간 방 현황 + 입·퇴실 처리.
 *
 * 카운터에서 가장 오래 켜 두는 화면이라 한눈에 다 보이는 카드 보드로 만든다.
 * 방 하나를 처리하러 다른 화면으로 넘어갈 일이 없도록, 그 방의 대여·예약까지
 * 카드 안에서 보여 준다.
 *
 * 입·퇴실은 데모 데이터(src/admin/store.ts)에만 반영된다. 특히 퇴실은 그 방의
 * 대여 사본을 전부 available 로 되돌리고 대기 예약을 취소하는 정리 작업까지
 * 같이 돈다 — 확인 창에서 그 사실을 미리 알려 준다.
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useToast } from '@/composables/useToast'
import AdminShell from '../components/AdminShell.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatusPill from '../components/StatusPill.vue'
import { formatAgo, formatDuration, formatElapsed, formatTime } from '../format'
import { useAdminStore } from '../store'
import type { AdminRoom } from '../types'

// 이 화면에는 기간 선택이 없으므로 항상 '오늘' 로 고정된 집계를 쓴다
const { rooms, activeRents, reservations, todayStats, now, checkIn, checkOut } =
  useAdminStore()
const { show: showToast } = useToast()

/** 입실 인원을 고르는 중인 방 */
const checkingIn = ref<string | null>(null)
const partySize = ref(2)
/** 퇴실 확인 중인 방 */
const checkingOut = ref<AdminRoom | null>(null)
const pending = ref(false)

/** 이보다 오래 앉아 있으면 카드에 주의 표시를 띄운다 */
const LONG_STAY_MINUTES = 180

function rentsOf(roomNumber: string) {
  return activeRents.value.filter((rent) => rent.roomNumber === roomNumber)
}

function waitingOf(roomNumber: string) {
  return reservations.value.filter(
    (reservation) =>
      reservation.roomNumber === roomNumber && reservation.status === 'WAITING',
  )
}

function stayMinutes(room: AdminRoom): number {
  return room.startedAt === null ? 0 : (now.value - room.startedAt) / 60_000
}

function openCheckIn(room: AdminRoom): void {
  checkingIn.value = room.roomNumber
  partySize.value = Math.min(4, room.capacity)
}

/** 서버 반영 여부를 그대로 말해 준다 — 화면만 바뀐 걸 성공이라고 하면 안 된다. */
function reportResult(
  ok: string,
  result: { synced: boolean; error: string | null },
): void {
  if (result.synced) {
    showToast(ok)
    return
  }
  showToast(`${ok} (서버 반영 실패: ${result.error})`, 'danger')
}

async function confirmCheckIn(room: AdminRoom): Promise<void> {
  pending.value = true
  try {
    const result = await checkIn(room.roomNumber, partySize.value)
    reportResult(`${room.label} 입실 처리했습니다. (${partySize.value}명)`, result)
  } finally {
    pending.value = false
    checkingIn.value = null
  }
}

async function confirmCheckOut(): Promise<void> {
  const room = checkingOut.value
  if (!room) return

  pending.value = true
  try {
    const returning = rentsOf(room.roomNumber).length
    const result = await checkOut(room.roomNumber)
    reportResult(
      returning > 0
        ? `${room.label} 퇴실 처리했습니다. 게임 ${returning}개를 반납 처리했습니다.`
        : `${room.label} 퇴실 처리했습니다.`,
      result,
    )
  } finally {
    pending.value = false
    checkingOut.value = null
  }
}

const checkoutEffects = computed(() => {
  const room = checkingOut.value
  if (!room) return []

  const rents = rentsOf(room.roomNumber)
  const waiting = waitingOf(room.roomNumber)
  const effects = [
    `이용 이력(room_usage)이 마감되고 방 상태가 EMPTY 로 바뀝니다.`,
  ]
  if (rents.length > 0) {
    effects.push(
      `대여 중인 ${rents.map((rent) => rent.gameName).join(', ')} (${rents.length}개)가 반납 처리되어 재고로 돌아갑니다.`,
    )
  }
  if (waiting.length > 0) {
    effects.push(`대기 중인 예약 ${waiting.length}건이 취소됩니다.`)
  }
  effects.push('되돌릴 수 없습니다. 다시 입실 처리하면 새 이용 건이 생깁니다.')
  return effects
})

const inUse = computed(() => rooms.value.filter((room) => room.status === 'USE'))
</script>

<template>
  <AdminShell
    title="방 현황"
    description="입실 · 퇴실 처리와 방별 실시간 상태"
  >
    <!-- 요약 -->
    <div class="flex flex-wrap items-center gap-3 rounded-card border border-line-soft bg-surface px-5 py-4">
      <div class="flex items-baseline gap-1.5">
        <strong class="text-2xl font-bold text-ink">{{ inUse.length }}</strong>
        <span class="text-sm text-subtle">/ {{ rooms.length }}개 방 이용 중</span>
      </div>
      <span class="h-5 w-px bg-line" />
      <span class="text-xs text-subtle">
        오늘 누적 <strong class="text-ink">{{ todayStats.teams }}팀</strong>
      </span>
      <span class="text-xs text-subtle">
        오늘 평균 체류
        <strong class="text-ink">{{ formatDuration(todayStats.avgStayMinutes) }}</strong>
      </span>
      <span class="text-xs text-subtle">
        대여 중 <strong class="text-ink">{{ activeRents.length }}건</strong>
      </span>

      <p class="ml-auto text-[11px] text-muted">
        데모 데이터입니다
      </p>
    </div>

    <!-- 방 카드 -->
    <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <article
        v-for="room in rooms"
        :key="room.roomNumber"
        class="flex flex-col rounded-card border bg-surface p-5"
        :class="room.status === 'USE' ? 'border-line' : 'border-line-soft'"
      >
        <header class="flex items-center gap-2">
          <h2 class="text-base font-bold tracking-tight text-ink">
            {{ room.label }}
          </h2>
          <span class="text-[11px] text-muted">정원 {{ room.capacity }}명</span>
          <span
            v-if="room.isLocal"
            class="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-bold text-accent-strong"
            title="이 방의 태블릿 화면이 현재 브라우저에 연결돼 있습니다"
          >
            연결된 태블릿
          </span>

          <StatusPill
            class="ml-auto"
            :tone="room.status === 'USE' ? 'ok' : 'idle'"
            :label="room.status === 'USE' ? '이용 중' : '빈 방'"
          />
        </header>

        <!-- 이용 중 -->
        <div v-if="room.status === 'USE'" class="mt-4 flex flex-col gap-3">
          <div class="flex items-end gap-3">
            <div>
              <p class="text-[11px] text-muted">이용 시간</p>
              <strong class="font-mono text-2xl font-bold text-ink tabular-nums">
                {{ formatElapsed(room.startedAt ?? 0, now) }}
              </strong>
            </div>
            <div class="mb-1 flex flex-col gap-0.5 text-[11px] text-subtle">
              <span>{{ formatTime(room.startedAt ?? 0) }} 입실</span>
              <span>{{ room.partySize }}명</span>
            </div>
            <StatusPill
              v-if="stayMinutes(room) > LONG_STAY_MINUTES"
              class="mb-1 ml-auto"
              tone="warn"
              icon="clock"
              label="장시간 이용"
            />
          </div>

          <div class="rounded-field bg-sunken px-3.5 py-3">
            <p class="text-[11px] font-semibold text-subtle">대여 중인 게임</p>
            <ul
              v-if="rentsOf(room.roomNumber).length"
              class="mt-1.5 flex flex-col gap-1"
            >
              <li
                v-for="rent in rentsOf(room.roomNumber)"
                :key="rent.rentId"
                class="flex items-center gap-2 text-xs"
              >
                <span class="min-w-0 flex-1 truncate font-medium text-body">
                  {{ rent.gameName }}
                </span>
                <span class="text-[10px] text-muted">{{ rent.cabinetId }}번 함</span>
                <StatusPill
                  :tone="rent.status === 'USING' ? 'ok' : 'warn'"
                  :label="rent.status === 'USING' ? '사용 중' : '미수령'"
                />
              </li>
            </ul>
            <p v-else class="mt-1.5 text-xs text-muted">없음</p>

            <p
              v-if="waitingOf(room.roomNumber).length"
              class="mt-2 flex items-center gap-1.5 text-[11px] font-semibold text-warm"
            >
              <AppIcon name="clock" :size="12" :stroke-width="2" />
              예약 대기 {{ waitingOf(room.roomNumber).length }}건
            </p>
          </div>

          <button
            type="button"
            class="h-11 rounded-full bg-danger text-sm font-semibold text-white transition hover:opacity-90"
            @click="checkingOut = room"
          >
            <span class="flex items-center justify-center gap-1.5">
              <AppIcon name="log-out" :size="15" :stroke-width="2" />
              퇴실 처리
            </span>
          </button>
        </div>

        <!-- 빈 방 -->
        <div v-else class="mt-4 flex flex-1 flex-col gap-3">
          <p class="text-xs text-subtle">
            {{
              room.lastEndedAt
                ? `${formatAgo(room.lastEndedAt, now)} 퇴실 · 정리 완료`
                : '오늘 이용 기록 없음'
            }}
          </p>

          <!-- 인원은 서버 스키마에 없지만 통계(방문 인원)에 필요해서 여기서 받는다 -->
          <div v-if="checkingIn === room.roomNumber" class="flex flex-col gap-2.5">
            <p class="text-[11px] font-semibold text-subtle">인원 선택</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="count in room.capacity - 1"
                :key="count"
                type="button"
                class="size-9 rounded-full border text-xs font-bold transition"
                :class="
                  partySize === count + 1
                    ? 'border-ink bg-ink text-surface'
                    : 'border-line text-subtle hover:bg-sunken'
                "
                @click="partySize = count + 1"
              >
                {{ count + 1 }}
              </button>
            </div>
            <div class="flex gap-2">
              <button
                type="button"
                class="h-11 flex-1 rounded-full border border-line text-sm font-semibold text-ink transition hover:bg-sunken"
                @click="checkingIn = null"
              >
                취소
              </button>
              <button
                type="button"
                :disabled="pending"
                class="h-11 flex-1 rounded-full bg-ink text-sm font-semibold text-surface transition hover:opacity-90 disabled:opacity-60"
                @click="confirmCheckIn(room)"
              >
                {{ partySize }}명 입실
              </button>
            </div>
          </div>

          <button
            v-else
            type="button"
            class="mt-auto h-11 rounded-full bg-ink text-sm font-semibold text-surface transition hover:opacity-90"
            @click="openCheckIn(room)"
          >
            <span class="flex items-center justify-center gap-1.5">
              <AppIcon name="log-in" :size="15" :stroke-width="2" />
              입실 처리
            </span>
          </button>
        </div>
      </article>
    </div>

    <ConfirmDialog
      v-if="checkingOut"
      :title="`${checkingOut.label}을 퇴실 처리할까요?`"
      message="이 방의 이용 이력을 마감하면서 남은 대여와 예약까지 함께 정리합니다."
      confirm-label="퇴실 처리"
      danger
      :pending="pending"
      :effects="checkoutEffects"
      @cancel="checkingOut = null"
      @confirm="confirmCheckOut"
    />
  </AdminShell>
</template>

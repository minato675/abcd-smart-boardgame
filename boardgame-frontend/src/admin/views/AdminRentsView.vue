<script setup lang="ts">
/**
 * 대여 현황과 강제 반납.
 *
 * 두 가지 이상 상태를 잡아내려고 만든 화면이다.
 * - **미수령**: 태블릿에서 대여는 눌렀는데 카드 태그를 안 해 사물함이 안 열린 건.
 *   사본은 이미 RENTED 로 묶여 있어서 다른 팀이 못 빌린다.
 * - **장시간 미반납**: 손님이 반납 없이 나간 건. 퇴실 처리를 안 하면 사본이 영영 묶인다.
 *
 * ⚠️ 서버에는 **개별 반납 엔드포인트가 없다** — 재고 복구는 퇴실(cleanUpRoom)에서만
 * 일어난다. 그래서 여기 '강제 반납' 은 화면 상태만 정리하고, 실제 DB 를 되돌리려면
 * 그 방을 퇴실 처리해야 한다. 확인 창에서 그대로 말해 준다.
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useToast } from '@/composables/useToast'
import { isCabinetMqttConfigured } from '../cabinetMqtt'
import AdminShell from '../components/AdminShell.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatTile from '../components/StatTile.vue'
import StatusPill from '../components/StatusPill.vue'
import { formatCount, formatDuration, formatDateTime } from '../format'
import { useAdminStore } from '../store'
import type { AdminRent } from '../types'

const { activeRents, cabinets, rooms, now, forceReturn, openCabinet } = useAdminStore()
const { show: showToast } = useToast()

/** 이 시간이 지나도록 카드 태그가 없으면 '미수령' 으로 본다 */
const UNPICKED_MINUTES = 10
/** 이 시간을 넘긴 대여는 손님이 그냥 나갔을 가능성이 크다 */
const OVERDUE_MINUTES = 240

type Filter = 'all' | 'unpicked' | 'overdue'

const filter = ref<Filter>('all')
const returning = ref<AdminRent | null>(null)
const mqttReady = isCabinetMqttConfigured()

function minutesSince(timestamp: number): number {
  return (now.value - timestamp) / 60_000
}

function isUnpicked(rent: AdminRent): boolean {
  return rent.status === 'RENT' && minutesSince(rent.rentedAt) > UNPICKED_MINUTES
}

function isOverdue(rent: AdminRent): boolean {
  return minutesSince(rent.rentedAt) > OVERDUE_MINUTES
}

const unpicked = computed(() => activeRents.value.filter(isUnpicked))
const overdue = computed(() => activeRents.value.filter(isOverdue))

/**
 * 지금 한 벌도 안 남은 게임 수. 미반납 건수와 달리 '손님이 지금 빌리려다 못 빌리는
 * 게임이 몇 종인가' 를 말해 준다 — 강제 반납이 실제로 재고를 풀어 주는지 보는 값이다.
 */
const soldOutGames = computed(() => {
  const free = new Map<number, number>()
  for (const slot of cabinets.value) {
    const available = slot.itemStatus === 'AVAILABLE' ? 1 : 0
    free.set(slot.gameId, (free.get(slot.gameId) ?? 0) + available)
  }
  return [...free.values()].filter((count) => count === 0).length
})

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'unpicked', label: '미수령' },
  { value: 'overdue', label: '장시간 미반납' },
]

const visibleRents = computed(() => {
  if (filter.value === 'unpicked') return unpicked.value
  if (filter.value === 'overdue') return overdue.value
  return activeRents.value
})

/** 방이 이미 퇴실한 상태인데 대여가 남아 있으면 데이터가 어긋난 것이다 */
function isOrphan(rent: AdminRent): boolean {
  return (
    rooms.value.find((room) => room.roomNumber === rent.roomNumber)?.status ===
    'EMPTY'
  )
}

function confirmReturn(): void {
  const rent = returning.value
  if (!rent) return
  forceReturn(rent.rentId)
  showToast(
    `'${rent.gameName}' 를 반납 처리했습니다. 실제 재고 복구는 ${rent.roomNumber}번 방 퇴실 처리가 필요합니다.`,
  )
  returning.value = null
}

/** 반납할 게임을 넣어야 하므로 'return' 으로 연다 */
function open(rent: AdminRent): void {
  const sent = openCabinet(rent.cabinetId, 'return')
  if (!sent) {
    showToast('VITE_MQTT_URL 이 없어 사물함 명령을 보낼 수 없습니다.', 'danger')
    return
  }
  showToast(
    `${rent.cabinetId}번 사물함에 열기 명령을 보냈습니다. 결과는 재고 · 사물함 화면에서 확인하세요.`,
  )
}

const returnEffects = computed(() => {
  const rent = returning.value
  if (!rent) return []
  return [
    `${rent.cabinetId}번 사물함의 사본이 화면상 재고로 돌아갑니다.`,
    '서버에는 개별 반납 API 가 없어 DB 는 바뀌지 않습니다 — 실제 재고를 되돌리려면 방 현황에서 그 방을 퇴실 처리하세요.',
    '사물함 문은 열리지 않습니다. 게임을 실제로 넣어야 한다면 옆의 사물함 열기를 먼저 쓰세요.',
  ]
})
</script>

<template>
  <AdminShell title="대여 현황" description="미반납 대여와 강제 반납 처리">
    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatTile
        label="미반납 대여"
        :value="formatCount(activeRents.length)"
        unit="건"
        hint="카페 전체 기준"
      />
      <StatTile
        label="미수령"
        :value="formatCount(unpicked.length)"
        unit="건"
        :higher-is-better="false"
        :hint="`대여 후 ${UNPICKED_MINUTES}분 넘게 카드 태그 없음`"
      />
      <StatTile
        label="장시간 미반납"
        :value="formatCount(overdue.length)"
        unit="건"
        :higher-is-better="false"
        :hint="`${formatDuration(OVERDUE_MINUTES)} 초과`"
      />
      <StatTile
        label="재고 0인 게임"
        :value="formatCount(soldOutGames)"
        unit="종"
        :higher-is-better="false"
        hint="지금 예약만 걸 수 있는 게임"
      />
    </div>

    <div class="flex flex-wrap items-center gap-3">
      <div class="flex items-center gap-1 rounded-full border border-line bg-surface p-1">
        <button
          v-for="option in FILTERS"
          :key="option.value"
          type="button"
          class="h-8 rounded-full px-4 text-xs font-semibold transition"
          :class="
            filter === option.value ? 'bg-ink text-surface' : 'text-subtle hover:bg-sunken'
          "
          @click="filter = option.value"
        >
          {{ option.label }}
        </button>
      </div>
      <p class="text-xs text-muted">{{ visibleRents.length }}건</p>
    </div>

    <section class="rounded-card border border-line-soft bg-surface">
      <table class="w-full border-collapse text-left text-xs">
        <thead>
          <tr class="border-b border-line">
            <th scope="col" class="py-3 pl-5 pr-3 font-semibold text-subtle">방</th>
            <th scope="col" class="py-3 pr-3 font-semibold text-subtle">게임</th>
            <th scope="col" class="py-3 pr-3 font-semibold text-subtle">사물함</th>
            <th scope="col" class="py-3 pr-3 font-semibold text-subtle">상태</th>
            <th scope="col" class="py-3 pr-3 text-right font-semibold text-subtle">
              대여 시각
            </th>
            <th scope="col" class="py-3 pr-3 text-right font-semibold text-subtle">
              경과
            </th>
            <th scope="col" class="py-3 pr-5 text-right font-semibold text-subtle">
              처리
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="visibleRents.length === 0">
            <td colspan="7" class="py-14 text-center text-[13px] text-muted">
              해당하는 대여가 없습니다.
            </td>
          </tr>

          <tr
            v-for="rent in visibleRents"
            :key="rent.rentId"
            class="border-b border-line-soft last:border-0"
            :class="isOverdue(rent) && 'bg-danger-bg/40'"
          >
            <td class="py-3 pl-5 pr-3 font-semibold text-ink">
              {{ rent.roomNumber }}번 방
            </td>
            <td class="py-3 pr-3 text-body">{{ rent.gameName }}</td>
            <td class="py-3 pr-3 text-subtle tabular-nums">
              {{ rent.cabinetId }}번 · 사본 {{ rent.itemId }}
            </td>
            <td class="py-3 pr-3">
              <div class="flex flex-wrap items-center gap-1.5">
                <StatusPill
                  :tone="rent.status === 'USING' ? 'ok' : 'warn'"
                  :label="rent.status === 'USING' ? '사용 중' : '수령 대기'"
                />
                <StatusPill
                  v-if="isUnpicked(rent)"
                  tone="warn"
                  icon="warning"
                  label="미수령"
                />
                <StatusPill
                  v-if="isOverdue(rent)"
                  tone="danger"
                  icon="clock"
                  label="장시간"
                />
                <StatusPill
                  v-if="isOrphan(rent)"
                  tone="danger"
                  icon="warning"
                  label="빈 방인데 대여 남음"
                />
              </div>
            </td>
            <td class="py-3 pr-3 text-right text-subtle tabular-nums">
              {{ formatDateTime(rent.rentedAt, now) }}
            </td>
            <td
              class="py-3 pr-3 text-right font-semibold tabular-nums"
              :class="isOverdue(rent) ? 'text-danger' : 'text-body'"
            >
              {{ formatDuration(minutesSince(rent.rentedAt)) }}
            </td>
            <td class="py-3 pr-5">
              <div class="flex justify-end gap-1.5">
                <button
                  type="button"
                  :disabled="!mqttReady"
                  class="flex h-8 items-center gap-1.5 rounded-full border border-line px-3 text-[11px] font-semibold text-subtle transition hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
                  @click="open(rent)"
                >
                  <AppIcon name="unlock" :size="12" :stroke-width="2" />
                  사물함 열기
                </button>
                <button
                  type="button"
                  class="flex h-8 items-center gap-1.5 rounded-full border border-line px-3 text-[11px] font-semibold text-danger transition hover:bg-danger-bg"
                  @click="returning = rent"
                >
                  <AppIcon name="undo" :size="12" :stroke-width="2" />
                  강제 반납
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <ConfirmDialog
      v-if="returning"
      :title="`'${returning.gameName}' 를 강제 반납할까요?`"
      :message="`${returning.roomNumber}번 방이 들고 있는 대여를 관리자가 대신 마감합니다.`"
      confirm-label="강제 반납"
      danger
      :effects="returnEffects"
      @cancel="returning = null"
      @confirm="confirmReturn"
    />
  </AdminShell>
</template>

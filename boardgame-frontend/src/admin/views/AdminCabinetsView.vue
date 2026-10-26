<script setup lang="ts">
/**
 * 재고 · 사물함 관리와 강제 오픈.
 *
 * 사물함 한 칸 = 사본 한 개다(board_game_item.cabinet_id). 그래서 '재고' 와
 * '사물함' 은 같은 표의 앞뒷면이고, 한 화면에서 위쪽은 게임 기준, 아래쪽은
 * 사물함 기준으로 같은 데이터를 보여 준다.
 *
 * ⚠️ 강제 오픈은 서버를 거치지 않고 브로커에 직접 명령을 던진다(REST 엔드포인트가
 * 없다). 컨트롤러는 카드 태그로 열린 거래가 없으면 그 명령을 무시하므로,
 * 화면은 '보냈다' 가 아니라 컨트롤러의 status 보고를 받아야 '열렸다' 고 말한다.
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useToast } from '@/composables/useToast'
import { CABINET_CONTROLLER_ID } from '@/config/env'
import AdminShell from '../components/AdminShell.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatTile from '../components/StatTile.vue'
import StatusPill from '../components/StatusPill.vue'
import { isCabinetMqttConfigured } from '../cabinetMqtt'
import { formatAgo, formatCount } from '../format'
import { useAdminStore } from '../store'
import type { CabinetSlot } from '../types'

const { cabinets, games, now, openAttempts, openCabinet, clearOpenAttempt } =
  useAdminStore()
const { show: showToast } = useToast()

type Filter = 'all' | 'available' | 'rented' | 'attention'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'available', label: '대여 가능' },
  { value: 'rented', label: '대여 중' },
  { value: 'attention', label: '확인 필요' },
]

const filter = ref<Filter>('all')
const keyword = ref('')
const opening = ref<CabinetSlot | null>(null)

const mqttReady = isCabinetMqttConfigured()

/** 문이 열린 채이거나 컨트롤러가 오류를 보고한 칸 */
function needsAttention(slot: CabinetSlot): boolean {
  return slot.doorState !== 'CLOSED'
}

const visible = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return cabinets.value.filter((slot) => {
    if (query && !slot.gameName.toLowerCase().includes(query)) return false
    if (filter.value === 'available') return slot.itemStatus === 'AVAILABLE'
    if (filter.value === 'rented') return slot.itemStatus === 'RENTED'
    if (filter.value === 'attention') return needsAttention(slot)
    return true
  })
})

const available = computed(
  () => cabinets.value.filter((slot) => slot.itemStatus === 'AVAILABLE').length,
)
const attention = computed(() => cabinets.value.filter(needsAttention).length)

/** 게임 기준 재고 요약. 품절인 게임을 먼저 올린다. */
const inventory = computed(() =>
  games.value
    .map((game) => {
      const slots = cabinets.value.filter((slot) => slot.gameId === game.id)
      const free = slots.filter((slot) => slot.itemStatus === 'AVAILABLE').length
      return {
        id: game.id,
        name: game.name,
        category: game.category,
        total: slots.length,
        free,
        rented: slots.length - free,
        cabinetIds: slots.map((slot) => slot.cabinetId),
      }
    })
    .sort((a, b) => a.free / a.total - b.free / b.total),
)

/**
 * 어떤 명령으로 열지. 비어 있는 칸은 '꺼내기', 사본이 나가 있는 칸은 '넣기' 다 —
 * 컨트롤러가 아두이노에 서로 다른 명령(RECEIVE / RETURN)으로 번역해 보낸다.
 */
function modeFor(slot: CabinetSlot): 'receive' | 'return' {
  return slot.itemStatus === 'AVAILABLE' ? 'receive' : 'return'
}

function confirmOpen(): void {
  const slot = opening.value
  if (!slot) return
  const sent = openCabinet(slot.cabinetId, modeFor(slot))
  showToast(
    sent
      ? `${slot.cabinetId}번 사물함에 열기 명령을 보냈습니다. 컨트롤러 응답을 기다립니다.`
      : 'VITE_MQTT_URL 이 없어 명령을 보내지 못했습니다.',
    sent ? 'success' : 'danger',
  )
  opening.value = null
}

const openEffects = computed(() => {
  const slot = opening.value
  if (!slot) return []
  return [
    `토픽 /cabinet/${CABINET_CONTROLLER_ID}/${slot.cabinetId}/open 으로 mode=${modeFor(slot)} 명령을 발행합니다.`,
    '컨트롤러는 카드 태그로 시작된 거래가 없으면 이 명령을 무시합니다. 그때는 응답이 오지 않고 실패로 표시됩니다.',
    '서버를 거치지 않으므로 이 개폐는 cabinet_history 에 기록되지 않습니다.',
  ]
})
</script>

<template>
  <AdminShell
    title="재고 · 사물함"
    :description="`컨트롤러 ${CABINET_CONTROLLER_ID} · 사물함 ${cabinets.length}칸`"
  >
    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatTile
        label="전체 사본"
        :value="formatCount(cabinets.length)"
        unit="개"
        :hint="`${games.length}종 보유`"
      />
      <StatTile label="대여 가능" :value="formatCount(available)" unit="개" />
      <StatTile
        label="대여 중"
        :value="formatCount(cabinets.length - available)"
        unit="개"
      />
      <StatTile
        label="확인 필요"
        :value="formatCount(attention)"
        unit="칸"
        :higher-is-better="false"
        hint="문이 열려 있거나 오류를 보고한 칸"
      />
    </div>

    <p
      v-if="!mqttReady"
      class="flex items-center gap-2 rounded-card border border-line-soft bg-warm-bg px-4 py-3 text-xs font-semibold text-warm"
    >
      <AppIcon name="warning" :size="14" :stroke-width="2" />
      VITE_MQTT_URL 이 비어 있어 강제 오픈을 보낼 수 없습니다. .env 에 브로커 주소를 넣어주세요.
    </p>

    <!-- 게임 기준 재고 -->
    <section class="rounded-card border border-line-soft bg-surface p-5">
      <h2 class="text-sm font-bold tracking-tight text-ink">게임별 재고</h2>
      <p class="mt-0.5 text-xs text-subtle">
        남은 사본이 적은 순서입니다. 0개인 게임은 지금 예약만 걸 수 있습니다.
      </p>

      <ul class="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        <li
          v-for="game in inventory"
          :key="game.id"
          class="flex items-center gap-3 rounded-field border border-line-soft px-3.5 py-2.5"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate text-xs font-semibold text-ink">{{ game.name }}</p>
            <p class="text-[10px] text-muted">
              {{ game.category }} · {{ game.cabinetIds.join(', ') }}번 함
            </p>
          </div>

          <!-- 사본 상태를 점으로. 개수가 적어서 막대보다 이쪽이 바로 읽힌다. -->
          <div class="flex shrink-0 gap-1" :aria-label="`${game.total}개 중 ${game.free}개 대여 가능`">
            <span
              v-for="index in game.total"
              :key="index"
              class="size-2.5 rounded-full"
              :class="index <= game.free ? 'bg-ok' : 'bg-line'"
            />
          </div>

          <StatusPill
            :tone="game.free === 0 ? 'danger' : game.free === game.total ? 'idle' : 'ok'"
            :label="game.free === 0 ? '전량 대여' : `${game.free}/${game.total}`"
          />
        </li>
      </ul>
    </section>

    <!-- 사물함 기준 -->
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

      <label class="relative flex h-10 min-w-[220px] items-center">
        <span class="absolute left-3.5 text-muted">
          <AppIcon name="search" :size="15" :stroke-width="1.9" />
        </span>
        <input
          v-model="keyword"
          type="search"
          placeholder="게임 이름으로 찾기"
          class="h-full w-full rounded-full border border-line bg-surface pl-10 pr-4 text-xs text-ink outline-none placeholder:text-muted focus:border-accent"
        />
      </label>

      <p class="text-xs text-muted">{{ visible.length }}칸</p>
    </div>

    <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
      <article
        v-for="slot in visible"
        :key="slot.cabinetId"
        class="flex flex-col gap-2.5 rounded-card border bg-surface p-4"
        :class="needsAttention(slot) ? 'border-danger' : 'border-line-soft'"
      >
        <header class="flex items-center gap-2">
          <span
            class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sunken text-xs font-bold text-ink tabular-nums"
          >
            {{ slot.cabinetId }}
          </span>
          <div class="min-w-0 flex-1">
            <p class="truncate text-xs font-semibold text-ink">{{ slot.gameName }}</p>
            <p class="text-[10px] text-muted">사본 {{ slot.itemId }}</p>
          </div>
        </header>

        <div class="flex flex-wrap items-center gap-1.5">
          <StatusPill
            :tone="slot.itemStatus === 'AVAILABLE' ? 'ok' : 'idle'"
            :label="slot.itemStatus === 'AVAILABLE' ? '대여 가능' : `${slot.heldBy}번 방`"
          />
          <StatusPill
            v-if="slot.doorState === 'OPEN'"
            tone="warn"
            icon="unlock"
            label="문 열림"
          />
          <StatusPill
            v-else-if="slot.doorState === 'FAULT'"
            tone="danger"
            icon="warning"
            label="컨트롤러 오류"
          />
        </div>

        <p class="text-[10px] text-muted">
          마지막 개폐 {{ formatAgo(slot.lastOpenedAt, now) }}
        </p>

        <!-- 강제 오픈 결과. 보낸 직후에는 '대기' 로 남는다. -->
        <p
          v-if="openAttempts.get(slot.cabinetId)"
          class="rounded-field px-2.5 py-2 text-[10px] leading-relaxed font-semibold"
          :class="{
            'bg-sunken text-subtle': openAttempts.get(slot.cabinetId)!.phase === 'waiting',
            'bg-ok-bg text-ok': openAttempts.get(slot.cabinetId)!.phase === 'opened',
            'bg-danger-bg text-danger': openAttempts.get(slot.cabinetId)!.phase === 'failed',
          }"
        >
          <template v-if="openAttempts.get(slot.cabinetId)!.phase === 'waiting'">
            명령 발행 · 컨트롤러 응답 대기 중
          </template>
          <template v-else-if="openAttempts.get(slot.cabinetId)!.phase === 'opened'">
            열림 확인됨
          </template>
          <template v-else>
            {{ openAttempts.get(slot.cabinetId)!.reason }}
          </template>
          <button
            type="button"
            class="ml-1 underline"
            @click="clearOpenAttempt(slot.cabinetId)"
          >
            지우기
          </button>
        </p>

        <button
          type="button"
          :disabled="!mqttReady"
          class="mt-auto flex h-9 items-center justify-center gap-1.5 rounded-full border border-line text-[11px] font-semibold text-ink transition hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45"
          @click="opening = slot"
        >
          <AppIcon name="unlock" :size="13" :stroke-width="2" />
          {{ modeFor(slot) === 'receive' ? '꺼내기로 열기' : '넣기로 열기' }}
        </button>
      </article>
    </div>

    <ConfirmDialog
      v-if="opening"
      :title="`${opening.cabinetId}번 사물함을 강제로 열까요?`"
      :message="`'${opening.gameName}' 사본이 들어 있는 칸입니다. 손님 확인 없이 열립니다.`"
      confirm-label="열기 명령 보내기"
      danger
      :effects="openEffects"
      @cancel="opening = null"
      @confirm="confirmOpen"
    />
  </AdminShell>
</template>

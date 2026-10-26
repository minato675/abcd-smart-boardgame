<script setup lang="ts">
/**
 * AI 기능 사용 로그 — 음성 규칙 도우미(qna_log)와 AI 심판(mc_turn_log,
 * mc_violation_log)을 한 타임라인으로 합쳐 본다.
 *
 * 세 테이블을 따로 보여 주면 "한 판에서 무슨 일이 있었나" 를 사람이 머릿속에서
 * 합쳐야 한다. 방·게임·시각이 모두 같은 축이라 한 줄로 세우는 편이 읽기 쉽다.
 *
 * 턴 판정은 한 판에 수십 건씩 쌓여서 기본 필터에서는 접어 둔다 — 켜지 않으면
 * 정작 봐야 할 반칙과 질문이 묻힌다.
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import AdminShell from '../components/AdminShell.vue'
import StatTile from '../components/StatTile.vue'
import StatusPill from '../components/StatusPill.vue'
import ChartCard from '../charts/ChartCard.vue'
import StackedBar from '../charts/StackedBar.vue'
import { seriesColor } from '../charts/palette'
import { formatCount, formatDateTime, formatDecimal } from '../format'
import { useAdminStore } from '../store'
import { AI_LOG_LABELS, STATS_RANGE_OPTIONS, type AiLogKind } from '../types'

const { aiLogs, stats, range, rooms, now } = useAdminStore()

/** 기본은 '판정 로그 제외' — 건수가 압도적이라 켜야 보이게 한다 */
const kinds = ref<Set<AiLogKind>>(new Set(['QNA', 'MC_VIOLATION']))
const room = ref<string>('all')
const expanded = ref<number | null>(null)

const KIND_TONE: Record<AiLogKind, 'ok' | 'warn' | 'idle'> = {
  QNA: 'ok',
  MC_TURN: 'idle',
  MC_VIOLATION: 'warn',
}

function toggleKind(kind: AiLogKind): void {
  const next = new Set(kinds.value)
  if (next.has(kind)) next.delete(kind)
  else next.add(kind)
  // 전부 끄면 빈 목록만 남아 쓸모가 없다
  if (next.size > 0) kinds.value = next
}

/**
 * 위쪽 KPI 는 기간 집계(stats)를 쓰므로 목록도 **같은 구간**으로 잘라야 한다.
 * 그러지 않으면 '오늘 규칙 질문 17건' 위에 지난주 기록이 줄줄이 붙는다.
 */
const visible = computed(() =>
  aiLogs.value.filter(
    (log) =>
      log.at >= stats.value.from &&
      kinds.value.has(log.kind) &&
      (room.value === 'all' || log.roomNumber === room.value),
  ),
)

/** 판당 몇 번 반칙이 나오는지 — 심판이 실제로 일하고 있는지 보는 값 */
const violationsPerSession = computed(() =>
  stats.value.mcSessions === 0
    ? null
    : stats.value.mcViolations / stats.value.mcSessions,
)

// 세 값 모두 같은 구간 집계에서 가져온다 — 하나만 목록(최근 N건 제한)에서
// 세면 비중이 실제와 어긋난다
const usageMix = computed(() =>
  (
    [
      ['QNA', stats.value.qnaQuestions],
      ['MC_VIOLATION', stats.value.mcViolations],
      ['MC_TURN', stats.value.mcTurns],
    ] as [AiLogKind, number][]
  ).map(([kind, value], index) => ({
    label: AI_LOG_LABELS[kind],
    value,
    color: seriesColor(index),
  })),
)
</script>

<template>
  <AdminShell
    title="AI 사용 로그"
    description="음성 규칙 도우미와 AI 심판이 남긴 기록"
  >
    <!-- 대시보드와 같은 기간 필터를 공유한다. 지표와 목록이 같은 구간을 본다. -->
    <div class="flex items-center gap-1 self-start rounded-full border border-line bg-surface p-1">
      <button
        v-for="option in STATS_RANGE_OPTIONS"
        :key="option.value"
        type="button"
        class="h-8 rounded-full px-4 text-xs font-semibold transition"
        :class="
          range === option.value ? 'bg-ink text-surface' : 'text-subtle hover:bg-sunken'
        "
        @click="range = option.value"
      >
        {{ option.label }}
      </button>
    </div>

    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatTile
        label="규칙 질문"
        :value="formatCount(stats.qnaQuestions)"
        unit="건"
        hint="손님이 음성으로 물어본 횟수"
      />
      <StatTile
        label="AI 심판 세션"
        :value="formatCount(stats.mcSessions)"
        unit="판"
        hint="카메라 판정이 돌아간 판 수"
      />
      <StatTile
        label="반칙 감지"
        :value="formatCount(stats.mcViolations)"
        unit="건"
        :higher-is-better="false"
      />
      <StatTile
        label="판당 반칙"
        :value="violationsPerSession === null ? '—' : formatDecimal(violationsPerSession)"
        unit="건"
        :higher-is-better="false"
        hint="심판이 실제로 잡아내고 있는지"
      />
    </div>

    <ChartCard
      title="AI 기능 사용 구성"
      subtitle="턴 판정은 한 판에 수십 건이라 항상 가장 큽니다"
      :legend="usageMix.map((item) => ({ label: item.label, color: item.color }))"
      :table-columns="['기능', '건수']"
      :table-rows="usageMix.map((item) => [item.label, item.value])"
    >
      <StackedBar :items="usageMix" value-label="건" />
    </ChartCard>

    <!-- 필터 -->
    <div class="flex flex-wrap items-center gap-3">
      <div class="flex items-center gap-1 rounded-full border border-line bg-surface p-1">
        <button
          v-for="(label, kind) in AI_LOG_LABELS"
          :key="kind"
          type="button"
          class="h-8 rounded-full px-4 text-xs font-semibold transition"
          :class="
            kinds.has(kind as AiLogKind)
              ? 'bg-ink text-surface'
              : 'text-subtle hover:bg-sunken'
          "
          :aria-pressed="kinds.has(kind as AiLogKind)"
          @click="toggleKind(kind as AiLogKind)"
        >
          {{ label }}
        </button>
      </div>

      <select
        v-model="room"
        class="h-10 rounded-full border border-line bg-surface px-4 text-xs font-semibold text-ink outline-none focus:border-accent"
      >
        <option value="all">전체 방</option>
        <option v-for="item in rooms" :key="item.roomNumber" :value="item.roomNumber">
          {{ item.label }}
        </option>
      </select>

      <!-- 목록은 최신 기록만 들고 있다. 위 지표는 구간 전체를 세므로 숫자가 다를 수 있다. -->
      <p class="text-xs text-muted">
        {{ visible.length }}건 · 최신 {{ aiLogs.length }}건까지만 보관
      </p>
    </div>

    <section class="rounded-card border border-line-soft bg-surface">
      <p v-if="visible.length === 0" class="py-14 text-center text-[13px] text-muted">
        조건에 맞는 기록이 없습니다.
      </p>

      <ul v-else class="flex flex-col">
        <li
          v-for="log in visible"
          :key="log.id"
          class="border-b border-line-soft last:border-0"
        >
          <button
            type="button"
            class="flex w-full items-center gap-3 px-5 py-3 text-left transition hover:bg-sunken"
            :aria-expanded="expanded === log.id"
            @click="expanded = expanded === log.id ? null : log.id"
          >
            <StatusPill
              :tone="KIND_TONE[log.kind]"
              :label="AI_LOG_LABELS[log.kind]"
            />
            <span class="w-14 shrink-0 text-[11px] font-semibold text-subtle">
              {{ log.roomNumber }}번 방
            </span>
            <span class="w-28 shrink-0 truncate text-[11px] text-muted">
              {{ log.gameName }}
            </span>
            <span class="min-w-0 flex-1 truncate text-xs text-body">
              {{ log.summary }}
            </span>
            <span class="shrink-0 text-[11px] text-muted tabular-nums">
              {{ formatDateTime(log.at, now) }}
            </span>
            <AppIcon
              v-if="log.detail"
              name="chevron-down"
              :size="14"
              :stroke-width="2"
              class="shrink-0 text-muted transition"
              :class="expanded === log.id && 'rotate-180'"
            />
            <span v-else class="w-3.5 shrink-0" />
          </button>

          <p
            v-if="expanded === log.id && log.detail"
            class="border-t border-line-soft bg-sunken px-5 py-3 text-xs leading-relaxed text-body"
          >
            {{ log.detail }}
          </p>
        </li>
      </ul>
    </section>
  </AdminShell>
</template>

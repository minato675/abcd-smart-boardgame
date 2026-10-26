<script setup lang="ts">
/**
 * 통계 대시보드.
 *
 * 필터(기간)는 맨 위 한 줄에만 있고 아래 전부를 같은 구간으로 묶는다 — 카드마다
 * 기간이 다르면 나란히 놓인 숫자끼리 말이 안 맞게 된다.
 *
 * 여기 있는 수치는 전부 원자료를 집계한 값이다(src/admin/stats.ts). 그래서
 * 방 현황에서 퇴실을 누르면 '현재 이용 중' 과 '평균 체류 시간' 이 실제로 따라 움직인다.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import AdminShell from '../components/AdminShell.vue'
import StatTile from '../components/StatTile.vue'
import BarChart from '../charts/BarChart.vue'
import ChartCard from '../charts/ChartCard.vue'
import ColumnChart from '../charts/ColumnChart.vue'
import LineChart from '../charts/LineChart.vue'
import StackedBar from '../charts/StackedBar.vue'
import { OTHER_COLOR, seriesColor, stepColor } from '../charts/palette'
import {
  formatCount,
  formatDecimal,
  formatDuration,
  formatPercent,
} from '../format'
import { useAdminStore } from '../store'
import { STATS_RANGE_OPTIONS } from '../types'

const { stats, range, regenerate } = useAdminStore()

const rangeOption = computed(
  () =>
    STATS_RANGE_OPTIONS.find((option) => option.value === range.value) ??
    STATS_RANGE_OPTIONS[0]!,
)
const rangeLabel = computed(() => rangeOption.value.label)

/** 증감 배지가 무엇과 비교한 값인지. '직전 최근 7일' 처럼 읽히지 않게 따로 만든다. */
const comparedTo = computed(() =>
  rangeOption.value.days === 1 ? '어제 같은 시각 대비' : `직전 ${rangeOption.value.days}일 대비`,
)

/** 하루짜리 구간에서는 '일자별 추이' 가 점 하나라 의미가 없다 */
const isSingleDay = computed(() => stats.value.teamsByDay.length <= 1)

const trendSeries = computed(() => [
  { name: '이용 팀', color: seriesColor(0), values: stats.value.teamsByDay.map((b) => b.value) },
  { name: '대여 건수', color: seriesColor(1), values: stats.value.rentsByDay.map((b) => b.value) },
])

/** 카테고리는 순서가 없는 항목이라 슬롯 순서대로 색을 준다(값 크기와 무관). */
const categoryItems = computed(() =>
  stats.value.byCategory.map((bucket, index) => ({
    ...bucket,
    color: bucket.label === '기타' ? OTHER_COLOR : seriesColor(index),
  })),
)

/** 난이도는 쉬움 → 어려움 순서가 의미를 가지므로 한 색상 계열의 명도 단계를 쓴다 */
const difficultyItems = computed(() =>
  stats.value.byDifficulty.map((bucket, index) => ({
    ...bucket,
    color: stepColor(index, stats.value.byDifficulty.length),
  })),
)

/** 퍼널도 단계 순서가 의미를 갖는다 */
const funnelItems = computed(() =>
  stats.value.reservationFunnel.map((stage, index) => ({
    ...stage,
    color: stepColor(index, stats.value.reservationFunnel.length),
  })),
)

const utilizationItems = computed(() =>
  stats.value.roomUtilization.map((bucket) => ({
    ...bucket,
    color: seriesColor(0),
  })),
)

/**
 * 실측 플레이 시간이 상자 표기보다 얼마나 긴지. 규칙 설명 시간이 붙기 때문에
 * 늘 더 걸리는데, 이 배수가 크면 그 게임은 회전이 안 도는 게임이라는 뜻이다.
 */
const overrun = computed(() => {
  const rows = stats.value.gameRows.filter(
    (row) => row.avgPlayMinutes !== null && row.boxPlayMinutes,
  )
  if (rows.length === 0) return null
  const ratios = rows.map(
    (row) => (row.avgPlayMinutes as number) / (row.boxPlayMinutes as number),
  )
  return ratios.reduce((sum, value) => sum + value, 0) / ratios.length
})
</script>

<template>
  <AdminShell
    title="통계 대시보드"
    :description="`${rangeLabel} 기준 · 모든 카드가 같은 구간을 봅니다`"
  >
    <template #actions>
      <button
        type="button"
        class="flex h-9 items-center gap-1.5 rounded-full border border-line px-3.5 text-xs font-semibold text-subtle transition hover:bg-sunken"
        @click="regenerate()"
      >
        <AppIcon name="refresh" :size="14" :stroke-width="1.9" />
        데모 데이터 재생성
      </button>
    </template>

    <!-- 필터 한 줄. 아래 모든 카드가 이 값을 따른다. -->
    <div class="flex flex-wrap items-center gap-3">
      <div class="flex items-center gap-1 rounded-full border border-line bg-surface p-1">
        <button
          v-for="option in STATS_RANGE_OPTIONS"
          :key="option.value"
          type="button"
          class="h-8 rounded-full px-4 text-xs font-semibold transition"
          :class="
            range === option.value
              ? 'bg-ink text-surface'
              : 'text-subtle hover:bg-sunken'
          "
          @click="range = option.value"
        >
          {{ option.label }}
        </button>
      </div>

      <p
        class="flex items-center gap-1.5 rounded-full bg-warm-bg px-3.5 py-2 text-[11px] font-semibold text-warm"
      >
        <AppIcon name="info" :size="13" :stroke-width="2" />
        데모 데이터 — 서버에 통계 API 가 아직 없어 프론트에서 생성한 이용 이력을 집계합니다
      </p>
    </div>

    <!-- 헤드라인 + 핵심 지표 -->
    <div
      class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.3fr)_repeat(3,minmax(0,1fr))]"
    >
      <StatTile
        hero
        label="이용 팀"
        :value="formatCount(stats.teams)"
        unit="팀"
        :delta="stats.delta.teams"
        :trend="stats.teamsByDay.map((bucket) => bucket.value)"
        :hint="comparedTo"
      />
      <StatTile
        label="방문 인원"
        :value="formatCount(stats.visitors)"
        unit="명"
        :delta="stats.delta.visitors"
      />
      <StatTile
        label="대여 건수"
        :value="formatCount(stats.rents)"
        unit="건"
        :delta="stats.delta.rents"
        :trend="stats.rentsByDay.map((bucket) => bucket.value)"
      />
      <StatTile
        label="현재 이용 중"
        :value="`${stats.roomsInUse} / ${stats.roomsTotal}`"
        unit="방"
        :hint="`빈 방 ${stats.roomsTotal - stats.roomsInUse}개`"
      />
    </div>

    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatTile
        label="평균 체류 시간"
        :value="formatDuration(stats.avgStayMinutes)"
        hint="퇴실 완료된 팀 기준"
      />
      <StatTile
        label="평균 플레이 시간"
        :value="formatDuration(stats.avgPlayMinutes)"
        :hint="overrun ? `상자 표기의 ${formatDecimal(overrun)}배` : undefined"
      />
      <StatTile
        label="팀당 대여 게임"
        :value="formatDecimal(stats.rentsPerTeam)"
        unit="개"
      />
      <StatTile
        label="방당 회전"
        :value="formatDecimal(stats.turnsPerRoom)"
        unit="팀"
        :hint="`${rangeLabel} 동안`"
      />
      <StatTile
        label="예약 이행률"
        :value="stats.fulfillRate === null ? '—' : formatPercent(stats.fulfillRate)"
        :hint="`발생 ${stats.reservations}건 · 대기 ${stats.reservationsWaiting}건`"
      />
      <StatTile
        label="사물함 개폐"
        :value="formatCount(stats.cabinetOpens)"
        unit="회"
      />
      <StatTile
        label="AI 심판 · 규칙 질문"
        :value="`${stats.mcSessions} · ${stats.qnaQuestions}`"
        hint="세션 · 질문"
      />
      <StatTile
        label="반칙 감지"
        :value="formatCount(stats.mcViolations)"
        unit="건"
        :higher-is-better="false"
        hint="AI 심판이 잡아낸 규칙 위반"
      />
    </div>

    <!-- 시간축 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <ChartCard
        title="시간대별 입실 팀 수"
        subtitle="피크 타임에 맞춰 인력을 배치하는 데 씁니다"
        :table-columns="['시간대', '입실 팀']"
        :table-rows="stats.byHour.map((bucket) => [bucket.label, bucket.value])"
      >
        <ColumnChart :items="stats.byHour" value-label="팀" />
      </ChartCard>

      <ChartCard
        v-if="!isSingleDay"
        title="일자별 이용 팀 · 대여 건수"
        subtitle="둘 다 '건수' 라 같은 축에 놓았습니다"
        legend-shape="line"
        :legend="[
          { label: '이용 팀', color: seriesColor(0) },
          { label: '대여 건수', color: seriesColor(1) },
        ]"
        :table-columns="['날짜', '이용 팀', '대여 건수']"
        :table-rows="
          stats.teamsByDay.map((bucket, index) => [
            bucket.label,
            bucket.value,
            stats.rentsByDay[index]?.value ?? 0,
          ])
        "
      >
        <LineChart
          :labels="stats.teamsByDay.map((bucket) => bucket.label)"
          :series="trendSeries"
        />
      </ChartCard>

      <ChartCard
        v-else
        title="시간대별 대여 건수"
        subtitle="오늘 하루라 일자별 추이 대신 시간대로 봅니다"
        :table-columns="['시간대', '대여 건수']"
        :table-rows="stats.rentsByHour.map((bucket) => [bucket.label, bucket.value])"
      >
        <ColumnChart :items="stats.rentsByHour" value-label="건" />
      </ChartCard>
    </div>

    <!-- 게임 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <ChartCard
        title="많이 나간 게임"
        subtitle="상위 8종의 대여 건수"
        :table-columns="['게임', '대여 건수']"
        :table-rows="stats.topGames.map((bucket) => [bucket.label, bucket.value])"
      >
        <BarChart :items="stats.topGames" label-width="112px" value-label="건" />
      </ChartCard>

      <ChartCard
        title="카테고리별 대여 비중"
        subtitle="어떤 성격의 게임이 팔리는지"
        :legend="categoryItems.map((item) => ({ label: item.label, color: item.color }))"
        :table-columns="['카테고리', '대여 건수']"
        :table-rows="categoryItems.map((item) => [item.label, item.value])"
      >
        <StackedBar :items="categoryItems" value-label="건" />
      </ChartCard>
    </div>

    <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <ChartCard
        title="난이도별 대여"
        subtitle="쉬움 → 어려움 순서"
        :table-columns="['난이도', '대여 건수']"
        :table-rows="difficultyItems.map((item) => [item.label, item.value])"
      >
        <BarChart :items="difficultyItems" label-width="56px" value-label="건" />
      </ChartCard>

      <ChartCard
        title="방별 가동률"
        subtitle="영업시간(11~23시) 대비 손님이 앉아 있던 시간"
        :table-columns="['방', '가동률']"
        :table-rows="
          utilizationItems.map((item) => [item.label, formatPercent(item.value)])
        "
      >
        <BarChart
          :items="utilizationItems"
          label-width="64px"
          value-label="가동률"
          :format="(value) => formatPercent(value)"
        />
      </ChartCard>

      <ChartCard
        title="예약 퍼널"
        subtitle="예약 → 반납 알림 → 실제 대여"
        :table-columns="['단계', '건수']"
        :table-rows="funnelItems.map((item) => [item.label, item.value])"
      >
        <BarChart :items="funnelItems" label-width="72px" value-label="건" />
      </ChartCard>
    </div>

    <!-- 이미 표 자체라 ChartCard 의 차트/표 토글은 맞지 않는다 -->
    <section class="rounded-card border border-line-soft bg-surface p-5">
      <h3 class="text-sm font-bold tracking-tight text-ink">게임별 상세</h3>
      <p class="mt-0.5 text-xs text-subtle">
        사본당 회전이 높고 대기가 걸리는 게임이 추가 구매 후보입니다
      </p>

      <div class="custom-scroll mt-4 max-h-[420px] overflow-auto">
        <table class="w-full border-collapse text-left text-xs">
          <thead class="sticky top-0 bg-surface">
            <tr class="border-b border-line">
              <th scope="col" class="py-2 pr-3 font-semibold text-subtle">게임</th>
              <th scope="col" class="py-2 pr-3 font-semibold text-subtle">카테고리</th>
              <th scope="col" class="py-2 pr-3 text-right font-semibold text-subtle">보유</th>
              <th scope="col" class="py-2 pr-3 text-right font-semibold text-subtle">대여</th>
              <th scope="col" class="py-2 pr-3 text-right font-semibold text-subtle">사본당 회전</th>
              <th scope="col" class="py-2 pr-3 text-right font-semibold text-subtle">실측 평균</th>
              <th scope="col" class="py-2 pr-3 text-right font-semibold text-subtle">상자 표기</th>
              <th scope="col" class="py-2 text-right font-semibold text-subtle">예약</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in stats.gameRows"
              :key="row.gameId"
              class="border-b border-line-soft last:border-0"
            >
              <td class="py-2 pr-3 font-semibold text-ink">{{ row.name }}</td>
              <td class="py-2 pr-3 text-subtle">{{ row.category }}</td>
              <td class="py-2 pr-3 text-right text-body tabular-nums">
                {{ row.totalCount }}
              </td>
              <td class="py-2 pr-3 text-right text-body tabular-nums">
                {{ row.rentCount }}
              </td>
              <td class="py-2 pr-3 text-right text-body tabular-nums">
                {{ formatDecimal(row.turnsPerCopy) }}
              </td>
              <td class="py-2 pr-3 text-right text-body tabular-nums">
                {{ formatDuration(row.avgPlayMinutes) }}
              </td>
              <td class="py-2 pr-3 text-right text-muted tabular-nums">
                {{ formatDuration(row.boxPlayMinutes) }}
              </td>
              <td class="py-2 text-right text-body tabular-nums">
                {{ row.reservationCount }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </AdminShell>
</template>

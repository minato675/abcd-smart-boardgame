<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import BaseOverlay from '@/components/common/BaseOverlay.vue'
import { tileColorClass, tileLabel, type Violation } from '@/composables/useAiReferee'

/**
 * AI 심판 패널.
 *
 *   off       꺼짐. 지원 게임을 들고 있어 다시 켤 수 있다 (오른쪽 아래 알약)
 *   collapsed 켜짐 + 접힘 (오른쪽 아래 알약)
 *   open      켜짐 + 펼침 (화면 가운데 팝업)
 *
 * 펼친 상태는 오른쪽 아래 작은 패널이 아니라 팝업이다. 태블릿을 서서 손가락으로
 * 누르는데 300px 패널 안의 버튼은 조준이 어렵다 - 매 턴 누르는 버튼이라
 * 한 번 빗나갈 때마다 판이 끊긴다.
 *
 * 그 대신 게임 목록을 가리므로 접기가 더 중요해졌다. 바깥을 누르거나 X 를 누르면
 * 알약으로 줄어들고, 그 상태에서도 지금 몇 번 차례인지는 계속 보인다.
 */
const props = defineProps<{
  mode: 'off' | 'collapsed' | 'open'
  boardGameName: string
  turnCount: number
  violation: Violation | null
  /** 이 판을 하는 사람 수. 좌석은 1..playerCount */
  playerCount: number
  /** 지금 차례인 좌석 */
  currentSeat: number
  /** 손패를 다 낸 좌석 */
  finishedSeats: number[]
  pending?: boolean
}>()

defineEmits<{
  start: []
  toggle: []
  passTurn: []
  finishPlayer: []
  openHistory: []
  dismissViolation: []
  stop: []
}>()

/** 좌석 칩. 지금 차례를 강조하고 끝난 사람은 흐리게 둔다. */
const seats = computed(() =>
  Array.from({ length: props.playerCount }, (_, i) => i + 1).map((seat) => ({
    seat,
    isCurrent: seat === props.currentSeat,
    isFinished: props.finishedSeats.includes(seat),
  })),
)
</script>

<template>
  <!--
    접힘/꺼짐은 알약으로 남긴다. 이 상태의 목적이 "게임 목록을 보게 비켜 주는 것"
    이라 팝업으로 만들면 접는 의미가 없다.
  -->
  <div
    v-if="mode !== 'open'"
    class="pointer-events-none absolute inset-0 z-40 flex items-end justify-end p-4"
  >
    <!-- 꺼짐: 다시 켜기 진입점. 이게 없으면 한 번 끈 뒤 되돌릴 방법이 없다 -->
    <button
      v-if="mode === 'off'"
      type="button"
      :disabled="pending"
      class="pointer-events-auto flex h-14 items-center gap-2.5 rounded-full border border-line bg-surface px-6 text-[15px] font-semibold text-ink shadow-[0_8px_24px_rgba(17,17,17,0.12)] transition hover:bg-sunken disabled:opacity-60"
      @click="$emit('start')"
    >
      <AppIcon name="check" :size="18" :stroke-width="1.75" />
      <span>{{ pending ? '켜는 중…' : 'AI 심판 켜기' }}</span>
    </button>

    <!-- 접힘 -->
    <button
      v-else
      type="button"
      class="pointer-events-auto flex h-14 items-center gap-2.5 rounded-full bg-ink px-6 text-[15px] font-semibold text-surface shadow-[0_8px_24px_rgba(17,17,17,0.24)] transition hover:opacity-90"
      @click="$emit('toggle')"
    >
      <!-- 접은 뒤에 위반이 남아 있으면 알약에서도 드러나야 한다 -->
      <span
        class="size-2.5 shrink-0 rounded-full"
        :class="violation ? 'bg-danger' : 'bg-emerald-400'"
      />
      <!--
        접힌 상태에도 차례를 남긴다. 여기가 "지금 누구 차례인가" 를 알려주는
        유일한 표시라, 알약으로 줄였다고 사라지면 순서를 놓친다.
      -->
      <span>{{ currentSeat }}번 차례 · {{ turnCount }}턴</span>
    </button>
  </div>

  <!-- 펼침: 바깥을 누르면 닫지 않고 접는다. 판이 도는 중에 세션이 끊기면 안 된다. -->
  <BaseOverlay v-else labelledby="referee-panel-title" @backdrop="$emit('toggle')">
    <div
      class="flex max-h-full w-[600px] flex-col rounded-modal border border-line-soft bg-surface p-6 shadow-[0_12px_40px_rgba(17,17,17,0.18)]"
    >
      <div class="flex shrink-0 items-center gap-3">
        <span class="size-2.5 shrink-0 rounded-full bg-emerald-500" />
        <div class="flex min-w-0 flex-1 flex-col">
          <strong id="referee-panel-title" class="text-[17px] font-semibold text-ink">
            AI 심판 진행 중
          </strong>
          <span class="truncate text-[13px] text-muted">
            {{ boardGameName }} · {{ turnCount }}턴 기록됨
          </span>
        </div>
        <button
          type="button"
          class="flex size-11 shrink-0 items-center justify-center rounded-full text-muted transition hover:bg-sunken"
          aria-label="심판 패널 접기"
          @click="$emit('toggle')"
        >
          <AppIcon name="close" :size="20" :stroke-width="1.75" />
        </button>
      </div>

      <!--
        좌석과 위반은 길이가 변한다(인원 수, 문구 길이). 600px 프레임 안에서
        아래 버튼들이 밀려 잘리지 않도록 이 영역만 줄어들고 넘치면 스크롤한다.
      -->
      <div class="my-5 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
        <!--
          좌석 줄. 차례가 자리 번호로 도는 건 서버가 정하고 화면은 받아 적기만 한다
          (여기서 같이 굴리면 언젠가 서버와 어긋나고, 그러면 진행자에게 가는 좌석과
          화면의 좌석이 달라져 남의 첫 등록 여부로 판정이 난다).
        -->
        <div class="flex flex-col gap-2.5">
          <span class="text-[13px] font-semibold text-ink">지금 차례</span>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="item in seats"
              :key="item.seat"
              class="flex h-14 min-w-16 items-center justify-center rounded-field px-4 text-[15px] font-semibold transition"
              :class="[
                item.isFinished
                  ? 'bg-sunken text-muted line-through'
                  : item.isCurrent
                    ? 'bg-ink text-surface'
                    : 'border border-line text-subtle',
              ]"
            >
              {{ item.seat }}번
            </span>
          </div>
        </div>

        <!--
          규칙 위반. 손님이 수를 고쳐야 하는 상황이라 버튼 위에 둔다 -
          턴 넘기기를 먼저 보고 누르면 지적을 놓친 채 진행된다.
        -->
        <div
          v-if="violation"
          class="flex flex-col gap-2 rounded-field border border-danger/30 bg-danger-bg p-4"
        >
          <div class="flex items-center gap-2">
            <AppIcon name="warning" :size="16" :stroke-width="2" class="shrink-0 text-danger" />
            <strong class="min-w-0 flex-1 truncate text-[13px] font-semibold text-danger">
              {{ violation.code }}
            </strong>
            <button
              type="button"
              class="-mr-1.5 flex size-9 shrink-0 items-center justify-center rounded-full text-muted transition hover:bg-surface"
              aria-label="위반 안내 닫기"
              @click="$emit('dismissViolation')"
            >
              <AppIcon name="close" :size="16" :stroke-width="1.75" />
            </button>
          </div>
          <p class="text-[15px] leading-relaxed text-body">{{ violation.message }}</p>

          <!-- 문제가 된 세트. '이전 화면 보기' 와 같은 방식으로 타일을 그린다 -->
          <div v-if="violation.table.length > 0" class="flex flex-col gap-1.5">
            <div
              v-for="(tileSet, setIndex) in violation.table"
              :key="setIndex"
              class="flex flex-col gap-1.5 rounded-field border border-line-soft bg-surface p-2.5"
            >
              <span class="text-[11px] font-semibold text-muted">
                {{ setIndex + 1 }}번 세트 · {{ tileSet.length }}장
              </span>
              <div class="flex flex-wrap items-center gap-1.5">
                <span
                  v-for="(tile, tileIndex) in tileSet"
                  :key="tileIndex"
                  class="flex h-10 min-w-8 items-center justify-center rounded-md border border-line-soft bg-sunken px-1.5 text-sm font-bold tabular-nums"
                  :class="tileColorClass(tile.color)"
                  :title="tile.color"
                >
                  {{ tileLabel(tile) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="flex shrink-0 flex-col gap-3">
        <button
          type="button"
          :disabled="pending"
          class="h-16 w-full rounded-full bg-ink text-[17px] font-semibold text-surface transition hover:opacity-90 disabled:opacity-60"
          @click="$emit('passTurn')"
        >
          {{ pending ? '읽는 중…' : `${currentSeat}번 턴 넘기기` }}
        </button>

        <div class="flex gap-3">
          <!--
            turnCount 로 막지 않는다. 그 값은 이번 세션에서 브로커로 받은 개수라
            새로고침하면 0 이 되는데, 실제 기록은 서버에 남아 있어 열면 나온다.
          -->
          <button
            type="button"
            class="h-14 flex-1 rounded-full border border-line text-[15px] font-semibold text-ink transition hover:bg-sunken"
            @click="$emit('openHistory')"
          >
            이전 화면 보기
          </button>

          <!--
            손패를 다 낸 사람을 차례에서 뺀다. 카메라는 테이블만 보고 손패는 못 보므로
            이건 사람이 눌러 줘야 알 수 있다.

            턴 넘기기와 나란히 두지 않고 한 단 아래 보조 버튼으로 둔다 - 판마다 한 번씩만
            누르는 버튼이라, 매 턴 누르는 버튼과 같은 무게로 보이면 잘못 누른다.
          -->
          <button
            type="button"
            :disabled="pending"
            class="h-14 flex-1 rounded-full border border-line text-[15px] font-semibold text-ink transition hover:bg-sunken disabled:opacity-60"
            @click="$emit('finishPlayer')"
          >
            {{ currentSeat }}번 다 냈어요
          </button>
        </div>

        <p class="text-[12px] leading-relaxed text-muted">
          수를 두고 나면 턴 넘기기를 눌러주세요. 테이블을 다시 읽고 규칙에 어긋나면
          알려드립니다. 손패를 다 내신 분이 있으면 '다 냈어요' 를 눌러 차례에서 빼주세요.
          게임 목록을 보시려면 바깥을 눌러 접어두세요.
        </p>

        <!--
          끄기는 접기(X)와 헷갈리면 안 되고, 접힌 알약에는 두지 않는다.
          게임 중에 잘못 눌러 세션이 끊기는 것을 막으려면 한 단계 안쪽에 있어야 한다.
          팝업이 커진 만큼 다른 버튼과 거리를 더 벌린다.
        -->
        <button
          type="button"
          :disabled="pending"
          class="-mb-1 mt-1 h-11 w-full rounded-full text-[13px] font-semibold text-danger transition hover:bg-sunken disabled:opacity-60"
          @click="$emit('stop')"
        >
          AI 심판 끄기
        </button>
      </div>
    </div>
  </BaseOverlay>
</template>

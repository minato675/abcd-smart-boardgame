<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import BaseOverlay from '@/components/common/BaseOverlay.vue'

/**
 * AI 심판 권유 팝업. 지원 게임을 대여하면 한 번 뜬다.
 * 확인하면 서버가 진행자에게 시작 명령을 보낸다.
 *
 * 인원을 여기서 묻는다. 카메라는 테이블만 보고 사람은 못 세는데, 진행자가 루미큐브
 * 첫 등록 30점처럼 사람마다 갈리는 규칙을 판정하려면 좌석 수를 알아야 한다.
 * 인원을 묻는 자리는 이 팝업 하나뿐이다 - 껐다 켤 때도 이 팝업이 다시 열린다.
 */
const props = withDefaults(
  defineProps<{
    gameName: string
    /** 게임의 추천 인원. 서버 board_game 값이라 비어 있을 수 있다. */
    minPlayers?: number | null
    maxPlayers?: number | null
    pending?: boolean
  }>(),
  { minPlayers: null, maxPlayers: null, pending: false },
)

const emit = defineEmits<{ dismiss: []; confirm: [playerCount: number] }>()

/**
 * 고를 수 있는 인원. 게임에 범위가 없으면 2~4 로 둔다.
 *
 * 서버도 board_game 의 min/max 로 한 번 더 막으므로 여기 값이 넓어도 틀린 인원이
 * 들어가지는 않는다. 이 목록은 "누르기 좋게" 좁혀 주는 역할이다.
 */
const options = computed<number[]>(() => {
  const min = Math.max(1, props.minPlayers ?? 2)
  const max = Math.max(min, props.maxPlayers ?? 4)
  return Array.from({ length: max - min + 1 }, (_, i) => min + i)
})

/** 기본값은 하한이다. 대부분 그대로 확인만 누르면 되도록 미리 골라 둔다. */
const selected = ref(options.value[0])
</script>

<template>
  <BaseOverlay labelledby="referee-title" @backdrop="emit('dismiss')">
    <div
      class="w-[440px] rounded-modal border border-line-soft bg-surface p-6 shadow-[0_12px_40px_rgba(17,17,17,0.18)]"
    >
      <div class="flex items-center gap-3">
        <span
          class="flex size-11 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
        >
          <AppIcon name="check" :size="20" :stroke-width="1.75" />
        </span>
        <div class="flex min-w-0 flex-col">
          <h2 id="referee-title" class="text-[17px] font-semibold text-ink">
            AI 심판을 켤까요?
          </h2>
          <span class="text-xs text-muted">
            <strong class="text-body">{{ gameName }}</strong> 은 AI 심판이
            봐줄 수 있어요
          </span>
        </div>
      </div>

      <p class="my-5 text-[13px] leading-relaxed text-subtle">
        테이블을 카메라로 지켜보면서 차례를 기록하고, 규칙에 어긋나는 수가 나오면
        알려드립니다. 게임 중에 언제든 끌 수 있어요.
      </p>

      <!--
        인원은 판이 시작되면 못 바꾼다(서버가 시작 요청의 값만 받는다).
        좌석 수가 틀리면 진행자가 들고 있는 좌석별 상태가 통째로 어긋나기 때문이다.
      -->
      <fieldset class="mb-5 flex flex-col gap-2.5">
        <legend class="mb-2.5 text-[13px] font-semibold text-ink">
          몇 분이서 하시나요?
        </legend>
        <div class="flex gap-2">
          <button
            v-for="count in options"
            :key="count"
            type="button"
            :aria-pressed="selected === count"
            class="h-11 flex-1 rounded-field border text-sm font-semibold transition"
            :class="
              selected === count
                ? 'border-ink bg-ink text-surface'
                : 'border-line text-ink hover:bg-sunken'
            "
            @click="selected = count"
          >
            {{ count }}명
          </button>
        </div>
        <p class="text-[11px] leading-relaxed text-muted">
          차례를 자리 번호로 세기 때문에 실제 인원과 같아야 해요. 게임 중에는 바꿀 수 없어요.
        </p>
      </fieldset>

      <div class="flex gap-2">
        <button
          type="button"
          class="h-11 flex-1 rounded-full border border-line text-sm font-semibold text-ink transition hover:bg-sunken"
          @click="emit('dismiss')"
        >
          나중에 하기
        </button>
        <button
          type="button"
          :disabled="pending"
          class="h-11 flex-1 rounded-full bg-ink text-sm font-semibold text-surface transition hover:opacity-90 disabled:opacity-60"
          @click="emit('confirm', selected)"
        >
          {{ pending ? '켜는 중…' : 'AI 심판 켜기' }}
        </button>
      </div>
    </div>
  </BaseOverlay>
</template>

<script setup lang="ts">
import AppIcon from '@/components/common/AppIcon.vue'
import BaseOverlay from '@/components/common/BaseOverlay.vue'
import type { RuleAnswer } from '@/composables/useRuleAssistant'

/**
 * 규칙 도우미 오버레이 (기존 VoiceSearchOverlay 대체).
 * 듣는 중 → 답변 카드. 게임 검색이 아니라 규칙 질문이다.
 */
defineProps<{
  listening: boolean
  /** ready 를 아직 못 받은 상태. listening 은 true 여도 실제로 듣기 시작한 건 아니다 */
  starting: boolean
  thinking: boolean
  statusText: string
  answer: RuleAnswer | null
}>()

defineEmits<{ close: []; again: [] }>()

/** 웨이브 바 9개 (높이 px, 투명도) */
const WAVE_BARS = [
  { height: 10, opacity: 0.45 },
  { height: 18, opacity: 0.6 },
  { height: 26, opacity: 0.75 },
  { height: 34, opacity: 0.9 },
  { height: 40, opacity: 1 },
  { height: 34, opacity: 0.9 },
  { height: 26, opacity: 0.75 },
  { height: 18, opacity: 0.6 },
  { height: 10, opacity: 0.45 },
]
</script>

<template>
  <BaseOverlay labelledby="assistant-title" @backdrop="$emit('close')">
    <div
      class="w-[520px] rounded-modal border border-line-soft bg-surface p-6 shadow-[0_12px_40px_rgba(17,17,17,0.18)]"
    >
      <div class="flex items-center gap-3">
        <span
          class="flex size-11 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
        >
          <AppIcon name="mic" :size="20" :stroke-width="1.75" />
        </span>
        <div class="flex min-w-0 flex-col">
          <strong id="assistant-title" class="text-[17px] font-semibold text-ink">
            {{
              thinking
                ? '분석하고 있어요'
                : starting
                  ? '준비하고 있어요'
                  : listening
                    ? '듣고 있어요'
                    : '이렇게 하면 됩니다'
            }}
          </strong>
          <span class="text-xs text-muted">
            규칙, 점수 계산, 애매한 상황을 물어보세요
          </span>
        </div>
      </div>

      <!-- 분석 중 -->
      <div
        v-if="thinking"
        class="my-5.5 flex flex-col items-center gap-4"
      >
        <span
          class="flex size-14 items-center justify-center rounded-full bg-accent-soft text-accent"
        >
          <AppIcon name="refresh" :size="24" :stroke-width="1.75" class="animate-spin" />
        </span>
        <p class="text-center text-[13px] text-subtle">{{ statusText }}</p>
      </div>

      <!-- 듣는 중 -->
      <div
        v-else-if="listening"
        class="my-5.5 flex flex-col items-center gap-4"
      >
        <div class="flex h-12 items-center justify-center gap-1.5">
          <span
            v-for="(bar, index) in WAVE_BARS"
            :key="index"
            class="wave-bar w-1 rounded-sm bg-accent"
            :style="{
              height: `${bar.height}px`,
              opacity: bar.opacity,
              animationDelay: `${index * 80}ms`,
            }"
          />
        </div>
        <p class="text-center text-[13px] text-subtle">{{ statusText }}</p>
        <div class="flex flex-wrap justify-center gap-1.5">
          <span class="rounded-full bg-sunken px-3 py-1.5 text-xs text-subtle">
            "스플렌더 점수 어떻게 세요?"
          </span>
          <span class="rounded-full bg-sunken px-3 py-1.5 text-xs text-subtle">
            "카탄에서 도둑 나오면요?"
          </span>
        </div>
      </div>

      <!-- 답변 -->
      <div v-else-if="answer" class="my-5 flex flex-col gap-3">
        <!-- 인식된 발화가 비어 있을 수 있다(req 없이 res 만 오는 경우) -->
        <div
          v-if="answer.question"
          class="flex flex-col gap-1 rounded-field bg-sunken px-3.5 py-3"
        >
          <span class="text-[11px] font-semibold text-muted">이렇게 들었어요</span>
          <strong class="text-sm font-semibold text-ink">
            {{ answer.question }}
          </strong>
        </div>
        <div
          class="flex flex-col gap-2 rounded-field border border-line-soft p-3.5"
        >
          <span class="text-[11px] font-semibold tracking-wide text-accent">
            규칙 안내
          </span>
          <p class="text-sm leading-relaxed text-body">{{ answer.answer }}</p>
          <span class="text-[11px] text-muted">
            헷갈리면 상자 안 설명서를 확인하거나 카운터에 물어보세요
          </span>
        </div>
      </div>

      <div class="flex gap-2">
        <button
          type="button"
          class="h-11 flex-1 rounded-full border border-line text-sm font-semibold text-ink transition hover:bg-sunken"
          @click="$emit('close')"
        >
          닫기
        </button>
        <button
          type="button"
          class="h-11 flex-1 rounded-full bg-ink text-sm font-semibold text-surface transition hover:opacity-90"
          @click="$emit('again')"
        >
          {{ listening ? '다시 듣기' : '다시 물어보기' }}
        </button>
      </div>
    </div>
  </BaseOverlay>
</template>

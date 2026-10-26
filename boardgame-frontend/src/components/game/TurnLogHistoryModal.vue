<script setup lang="ts">
import BaseOverlay from '@/components/common/BaseOverlay.vue'
import { tileColorClass, tileLabel, type StoredTurnLog } from '@/composables/useAiReferee'

/**
 * '이전 화면 보기' - 서버에 기록된 마지막 테이블 상태를 루미큐브 타일로 그린다.
 *
 * 세트 하나가 한 줄이고 세트 안 타일 순서를 그대로 유지한다 - 루미큐브는 어떤 타일이
 * 어느 세트에 몇 번째로 놓였는지가 곧 규칙 판정의 근거라, 순서를 흐트러뜨리면 안 된다.
 */
defineProps<{
  log: StoredTurnLog | null
  loading?: boolean
  error?: string | null
}>()

defineEmits<{ close: [] }>()
</script>

<template>
  <BaseOverlay labelledby="turn-log-title" @backdrop="$emit('close')">
    <div
      class="flex max-h-full w-[560px] flex-col rounded-modal border border-line-soft bg-surface p-6 shadow-[0_12px_40px_rgba(17,17,17,0.18)]"
    >
      <h2 id="turn-log-title" class="text-[17px] font-semibold text-ink">
        이전 화면
      </h2>
      <p class="mt-1.5 text-[13px] text-subtle">
        <template v-if="log">
          {{ log.turnNo }}턴 · {{ log.table.length }}세트 · 타일
          {{ log.tileCount }}장
        </template>
        <template v-else>AI 심판이 마지막으로 읽은 테이블입니다.</template>
      </p>

      <div class="my-5 flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto">
        <p v-if="loading" class="py-6 text-center text-[13px] text-muted">
          불러오는 중…
        </p>

        <p v-else-if="error" class="py-6 text-center text-[13px] text-danger">
          {{ error }}
        </p>

        <p
          v-else-if="!log || log.table.length === 0"
          class="py-6 text-center text-[13px] text-muted"
        >
          아직 기록된 테이블이 없습니다. 턴을 넘기면 여기에 나타나요.
        </p>

        <!-- 세트 하나가 한 줄 -->
        <div
          v-for="(tileSet, setIndex) in log?.table ?? []"
          v-else
          :key="setIndex"
          class="flex flex-col gap-1.5 rounded-field border border-line-soft bg-sunken p-3"
        >
          <span class="text-[11px] font-semibold text-muted">
            {{ setIndex + 1 }}번 세트 · {{ tileSet.length }}장
          </span>
          <div class="flex flex-wrap items-center gap-1.5">
            <span
              v-for="(tile, tileIndex) in tileSet"
              :key="tileIndex"
              class="flex h-11 min-w-9 items-center justify-center rounded-md border border-line-soft bg-surface px-1.5 text-base font-bold tabular-nums shadow-[0_1px_3px_rgba(17,17,17,0.12)]"
              :class="tileColorClass(tile.color)"
              :title="tile.color"
            >
              {{ tileLabel(tile) }}
            </span>
          </div>
        </div>
      </div>

      <button
        type="button"
        class="h-11 w-full shrink-0 rounded-full border border-line text-sm font-semibold text-ink transition hover:bg-sunken"
        @click="$emit('close')"
      >
        닫기
      </button>
    </div>
  </BaseOverlay>
</template>

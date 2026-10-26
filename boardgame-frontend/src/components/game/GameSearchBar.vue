<script setup lang="ts">
import AppIcon from '@/components/common/AppIcon.vue'

/** 검색 + 규칙 도우미. 음성은 게임 검색이 아니라 규칙 질문용이다. */
const keyword = defineModel<string>('keyword', { required: true })

defineEmits<{ 'ask-rule': [] }>()
</script>

<template>
  <div class="flex shrink-0 items-center gap-2.5">
    <div
      class="flex h-11 flex-1 items-center gap-2.5 rounded-full border border-line bg-surface px-4"
    >
      <AppIcon name="search" :size="18" :stroke-width="1.75" class="text-muted" />
      <input
        v-model="keyword"
        type="text"
        placeholder="게임 이름으로 찾기"
        class="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted"
      />
    </div>

    <button
      type="button"
      class="flex h-11 shrink-0 items-center gap-2 rounded-full bg-ink px-4.5 text-sm font-semibold text-surface transition hover:opacity-90"
      @click="$emit('ask-rule')"
    >
      <AppIcon name="mic" :size="17" :stroke-width="1.75" />
      <span>규칙 물어보기</span>
    </button>
  </div>
</template>

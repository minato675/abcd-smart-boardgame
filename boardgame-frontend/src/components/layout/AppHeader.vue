<script setup lang="ts">
import { onMounted, ref } from 'vue'
import brandMark from '@/assets/brand-mark.png'
import AppIcon from '@/components/common/AppIcon.vue'
import { useRoomSession } from '@/composables/useRoomSession'

/**
 * 상단 헤더 (56px).
 * - 기본형(목록): 카페 마크 + 이름 + 안내문
 * - 서브 페이지형(상세): 뒤로가기 + 카페 마크
 * 우측은 항상 방 번호 · 사용 시간 칩과 조명(다크 테마) 토글.
 */
const props = withDefaults(
  defineProps<{ subtitle?: string; showBack?: boolean }>(),
  { showBack: false, subtitle: '오늘 대여 가능한 게임을 골라보세요' },
)

defineEmits<{ back: [] }>()

const { cafeName, roomName, elapsedLabel } = useRoomSession()

const isDark = ref(false)

onMounted(() => {
  isDark.value = document.documentElement.dataset.theme === 'dark'
})

function toggleTheme(): void {
  isDark.value = !isDark.value
  document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light'
}
</script>

<template>
  <header
    class="flex h-14 shrink-0 items-center gap-4 border-b border-line-soft bg-surface px-5"
  >
    <button
      v-if="props.showBack"
      type="button"
      class="flex size-10 shrink-0 items-center justify-center rounded-full border border-line text-ink transition hover:bg-sunken"
      aria-label="게임 목록으로 돌아가기"
      @click="$emit('back')"
    >
      <AppIcon name="chevron-left" :size="18" :stroke-width="1.75" />
    </button>

    <div class="flex min-w-0 items-center gap-2.5">
      <span
        class="flex size-7 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-ink"
      >
        <img :src="brandMark" alt="" class="size-full object-cover" />
      </span>
      <div class="flex min-w-0 flex-col">
        <strong class="truncate text-sm font-bold tracking-tight text-ink">
          {{ cafeName }}
        </strong>
        <span class="truncate text-[11px] text-muted">{{ props.subtitle }}</span>
      </div>
    </div>

    <div class="ml-auto flex items-center gap-2">
      <div
        class="flex h-9 items-center gap-2 rounded-full bg-warm-bg px-3.5 text-warm"
      >
        <span class="size-1.5 rounded-full bg-warm" />
        <span class="text-xs font-bold">{{ roomName }}</span>
        <span class="h-3.5 w-px bg-current opacity-30" />
        <span class="font-mono text-xs font-semibold tabular-nums">
          {{ elapsedLabel }}
        </span>
      </div>

      <button
        type="button"
        class="flex size-9 items-center justify-center rounded-full border border-line text-subtle transition hover:bg-sunken"
        aria-label="조명 전환"
        @click="toggleTheme"
      >
        <AppIcon :name="isDark ? 'moon' : 'sun'" :size="16" :stroke-width="1.75" />
      </button>
    </div>
  </header>
</template>

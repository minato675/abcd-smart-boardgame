<script setup lang="ts">
/**
 * 관리자 좌측 내비게이션.
 *
 * 다섯 화면뿐이라 접거나 계층을 두지 않는다 — 카운터 직원이 손님을 앞에 두고
 * 쓰는 화면이라 두 번 클릭해야 닿는 메뉴가 없어야 한다.
 */
import { RouterLink } from 'vue-router'
import brandMark from '@/assets/brand-mark.png'
import AppIcon from '@/components/common/AppIcon.vue'
import type { IconName } from '@/components/common/icons'
import { CAFE_NAME } from '@/config/env'

interface NavItem {
  to: string
  label: string
  icon: IconName
  /** 우측에 붙는 숫자 배지 (0 이면 숨긴다) */
  badge?: number
}

defineProps<{ items: NavItem[] }>()
</script>

<template>
  <aside
    class="flex w-[212px] shrink-0 flex-col border-r border-line-soft bg-surface"
  >
    <div class="flex h-16 shrink-0 items-center gap-2.5 border-b border-line-soft px-5">
      <span
        class="flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-ink"
      >
        <img :src="brandMark" alt="" class="size-full object-cover" />
      </span>
      <div class="flex min-w-0 flex-col">
        <strong class="truncate text-[13px] font-bold tracking-tight text-ink">
          {{ CAFE_NAME }}
        </strong>
        <span class="text-[11px] text-muted">관리자</span>
      </div>
    </div>

    <nav class="flex flex-1 flex-col gap-0.5 p-3">
      <RouterLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        class="flex h-10 items-center gap-2.5 rounded-field px-3 text-[13px] font-semibold text-subtle no-underline transition hover:bg-sunken hover:text-ink hover:no-underline"
        active-class="!bg-accent-soft !text-accent-strong"
      >
        <AppIcon :name="item.icon" :size="16" :stroke-width="1.9" />
        <span class="min-w-0 flex-1 truncate">{{ item.label }}</span>
        <span
          v-if="item.badge"
          class="flex h-5 min-w-5 items-center justify-center rounded-full bg-ink px-1.5 text-[10px] font-bold text-surface tabular-nums"
        >
          {{ item.badge }}
        </span>
      </RouterLink>
    </nav>

    <RouterLink
      to="/"
      class="m-3 flex h-10 items-center justify-center gap-2 rounded-field border border-line text-xs font-semibold text-subtle no-underline transition hover:bg-sunken hover:text-ink hover:no-underline"
    >
      <AppIcon name="external-link" :size="14" :stroke-width="1.9" />
      손님 태블릿 화면
    </RouterLink>
  </aside>
</template>

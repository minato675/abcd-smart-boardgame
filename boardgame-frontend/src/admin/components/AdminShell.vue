<script setup lang="ts">
/**
 * 관리자 화면 공통 셸 — 좌측 내비 + 상단 바 + 본문.
 *
 * 손님 화면의 TabletFrame(1024x600 고정)과 달리 폭을 잡지 않는다. 이 화면은
 * 카운터 PC 모니터에서 열리고, 표와 차트는 넓을수록 좋기 때문이다.
 * 다만 아주 넓은 모니터에서 한 줄이 끝없이 길어지지 않도록 본문에 상한만 둔다.
 *
 * 다크 테마 토글은 손님 화면과 같은 `html[data-theme]` 을 쓴다 — 토큰이 하나라
 * 두 화면의 색이 따로 놀지 않는다.
 */
import { computed, onMounted, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import ToastMessage from '@/components/common/ToastMessage.vue'
import { useToast } from '@/composables/useToast'
import { isCabinetMqttConfigured, isCabinetMqttConnected } from '../cabinetMqtt'
import { useAdminStore } from '../store'
import AdminSidebar from './AdminSidebar.vue'

defineProps<{ title: string; description?: string }>()

const { toast } = useToast()
const { rooms, activeRents, now } = useAdminStore()

const isDark = ref(false)
onMounted(() => {
  isDark.value = document.documentElement.dataset.theme === 'dark'
})

function toggleTheme(): void {
  isDark.value = !isDark.value
  document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light'
}

const navItems = computed(() => [
  { to: '/admin', label: '대시보드', icon: 'dashboard' as const },
  {
    to: '/admin/rooms',
    label: '방 현황',
    icon: 'door' as const,
    badge: rooms.value.filter((room) => room.status === 'USE').length,
  },
  {
    to: '/admin/rents',
    label: '대여 현황',
    icon: 'package' as const,
    badge: activeRents.value.length,
  },
  { to: '/admin/cabinets', label: '재고 · 사물함', icon: 'cabinet' as const },
  { to: '/admin/ai', label: 'AI 사용 로그', icon: 'robot' as const },
])

/**
 * 브로커 연결 상태. mqtt.js 의 재연결은 우리가 통보받지 못하므로
 * 화면 시계(1초)가 돌 때마다 다시 물어본다.
 */
const brokerLabel = computed(() => {
  void now.value
  if (!isCabinetMqttConfigured()) return { text: 'MQTT 미설정', tone: 'text-muted' }
  return isCabinetMqttConnected()
    ? { text: '컨트롤러 연결됨', tone: 'text-ok' }
    : { text: '컨트롤러 연결 끊김', tone: 'text-danger' }
})

const clock = computed(() => {
  const date = new Date(now.value)
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getMonth() + 1}월 ${date.getDate()}일 ${pad(date.getHours())}:${pad(date.getMinutes())}`
})
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-canvas">
    <AdminSidebar :items="navItems" />

    <div class="flex min-h-0 min-w-0 flex-1 flex-col">
      <header
        class="flex h-16 shrink-0 items-center gap-4 border-b border-line-soft bg-surface px-6"
      >
        <div class="min-w-0 flex-1">
          <h1 class="truncate text-[17px] font-bold tracking-tight text-ink">
            {{ title }}
          </h1>
          <p v-if="description" class="truncate text-xs text-muted">
            {{ description }}
          </p>
        </div>

        <slot name="actions" />

        <span
          class="hidden items-center gap-1.5 text-[11px] font-semibold xl:flex"
          :class="brokerLabel.tone"
        >
          <AppIcon name="wifi" :size="13" :stroke-width="2" />
          {{ brokerLabel.text }}
        </span>

        <span class="hidden font-mono text-xs font-semibold text-subtle tabular-nums lg:block">
          {{ clock }}
        </span>

        <button
          type="button"
          class="flex size-9 shrink-0 items-center justify-center rounded-full border border-line text-subtle transition hover:bg-sunken"
          aria-label="조명 전환"
          @click="toggleTheme"
        >
          <AppIcon :name="isDark ? 'moon' : 'sun'" :size="16" :stroke-width="1.75" />
        </button>
      </header>

      <main class="custom-scroll min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-6">
        <div class="mx-auto flex max-w-[1440px] min-w-0 flex-col gap-5">
          <slot />
        </div>
      </main>
    </div>

    <!-- 토스트는 손님 화면과 같은 컴포넌트를 쓴다. 그쪽은 태블릿 프레임 기준
         absolute 라서, 여기서는 화면 전체를 덮는 fixed 레이어를 기준면으로 준다. -->
    <div class="pointer-events-none fixed inset-0 z-60">
      <ToastMessage v-if="toast" :toast="toast" />
    </div>
  </div>
</template>

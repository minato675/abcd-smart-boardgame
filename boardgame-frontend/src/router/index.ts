import { createRouter, createWebHistory } from 'vue-router'
import GameListView from '@/views/GameListView.vue'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'game-list',
      component: GameListView,
    },
    {
      path: '/games/:id',
      name: 'game-detail',
      // 상세정보는 진입 빈도가 낮아 지연 로딩
      component: () => import('@/views/GameDetailView.vue'),
    },
    /*
     * 관리자 화면. 데모라 로그인이 없다 — 주소를 아는 사람은 누구나 들어온다.
     * 실서비스로 가면 여기 라우트 가드와 서버 인증이 같이 붙어야 한다.
     *
     * 손님 태블릿과 번들을 나눈다: 태블릿은 이 화면을 절대 열지 않는데
     * 차트·표 코드까지 같이 받을 이유가 없다.
     */
    {
      path: '/admin',
      name: 'admin-dashboard',
      component: () => import('@/admin/views/AdminDashboardView.vue'),
    },
    {
      path: '/admin/rooms',
      name: 'admin-rooms',
      component: () => import('@/admin/views/AdminRoomsView.vue'),
    },
    {
      path: '/admin/rents',
      name: 'admin-rents',
      component: () => import('@/admin/views/AdminRentsView.vue'),
    },
    {
      path: '/admin/cabinets',
      name: 'admin-cabinets',
      component: () => import('@/admin/views/AdminCabinetsView.vue'),
    },
    {
      path: '/admin/ai',
      name: 'admin-ai-logs',
      component: () => import('@/admin/views/AdminAiLogsView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: { name: 'game-list' },
    },
  ],
})

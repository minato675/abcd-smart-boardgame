<script setup lang="ts">
/**
 * 화면설계 공통 셸: 1024 x 600 고정 태블릿 프레임.
 * 기본 슬롯은 화면 본문, overlay 슬롯은 프레임 안에 깔리는 모달/토스트 레이어.
 */
</script>

<template>
  <div class="flex h-screen items-center justify-center overflow-hidden bg-canvas p-4">
    <div
      class="relative flex h-[600px] w-[1024px] flex-col overflow-hidden rounded-xl border border-line bg-canvas"
    >
      <slot />
      <slot name="overlay" />
    </div>
  </div>
</template>

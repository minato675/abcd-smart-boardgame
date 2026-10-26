<script setup lang="ts">
/**
 * 태블릿 프레임 안쪽을 덮는 모달 레이어.
 * fixed 대신 absolute 를 써서 1024x600 프레임을 벗어나지 않는다.
 */
withDefaults(defineProps<{ labelledby?: string }>(), {})
defineEmits<{ backdrop: [] }>()
</script>

<template>
  <div
    class="absolute inset-0 z-50 flex items-center justify-center bg-[rgba(17,17,17,0.4)] p-4"
    role="dialog"
    aria-modal="true"
    :aria-labelledby="labelledby"
    @click.self="$emit('backdrop')"
  >
    <slot />
  </div>
</template>

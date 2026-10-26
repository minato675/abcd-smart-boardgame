<script setup lang="ts">
/**
 * 게임 이미지 자리.
 *
 * 우선순위: 서버 이미지 → 이름으로 찾은 로컬 SVG → 이름 첫 글자.
 * 서버가 준 url 이 404 나면(백엔드에 이미지 서빙이 없어 흔하다) 깨진 아이콘 대신
 * 로컬 SVG 로 내려간다.
 */
import { computed, ref, watch } from 'vue'
import { localThumbnail } from './localThumbnails'

const props = withDefaults(
  defineProps<{ url?: string | null; name?: string; textSize?: string }>(),
  { url: null, name: '', textSize: 'text-2xl' },
)

/** 서버 이미지가 깨졌는지. url 이 바뀌면 새 주소로 다시 시도한다. */
const remoteFailed = ref(false)

watch(
  () => props.url,
  () => {
    remoteFailed.value = false
  },
)

const source = computed(() =>
  props.url && !remoteFailed.value ? props.url : localThumbnail(props.name),
)
</script>

<template>
  <img
    v-if="source"
    :src="source"
    :alt="props.name"
    class="size-full rounded-field object-cover"
    @error="remoteFailed = true"
  />
  <div
    v-else
    class="flex size-full items-center justify-center rounded-field border border-line-soft bg-sunken font-bold text-muted"
    :class="props.textSize"
    aria-hidden="true"
  >
    {{ props.name.slice(0, 1) }}
  </div>
</template>

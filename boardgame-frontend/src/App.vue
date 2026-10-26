<script setup lang="ts">
import { RouterView } from 'vue-router'
import { connectRoomMqtt } from '@/mqtt/roomMqtt'
import { useTts } from '@/composables/useTts'
import { useNotificationSound } from '@/composables/useNotificationSound'

/*
 * 방 이벤트 구독은 화면이 아니라 앱 단위다. 호출어로 QnA 가 시작되는 경로에서는
 * 태블릿이 어느 화면에 있든 qna/ready 를 받아야 하므로 여기서 한 번만 연결한다.
 */
connectRoomMqtt()

/*
 * 위반 음성/알림음 모두 MQTT 이벤트 콜백에서 나가므로 사용자 제스처 없이 재생이
 * 불릴 수 있다. 화면 아무 데나 처음 터치/클릭할 때 한 번 미리 틔워 둔다.
 */
const { unlock: unlockTts } = useTts()
const { unlock: unlockNotificationSound } = useNotificationSound()
window.addEventListener(
  'pointerdown',
  () => {
    unlockTts()
    unlockNotificationSound()
  },
  { once: true },
)
</script>

<template>
  <RouterView />
</template>

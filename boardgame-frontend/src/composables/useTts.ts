import { ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID } from '@/config/env'

/**
 * ElevenLabs TTS 로 텍스트를 음성 파일(mp3)로 받아 재생한다.
 *
 * 브라우저 내장 음성 합성과 달리 기기에 설치된 음성에 기대지 않아 목소리가 일정하다.
 *
 * 주의: 지금은 이 프런트가 ELEVENLABS_API_KEY 를 들고 직접 호출하는 임시 구조다.
 * VITE_ 로 시작하는 값은 빌드 결과물(JS 번들)에 그대로 박혀 브라우저에서 누구나
 * 볼 수 있으므로, 운영 배포 전에는 이 호출을 백엔드로 옮겨 키를 감춰야 한다.
 */

const TTS_URL = `https://api.elevenlabs.io/v1/text-to-speech/${ELEVENLABS_VOICE_ID}`

/** 무음 1프레임 WAV - 사용자 제스처 없이 오디오가 막히는 걸 피하려고 미리 한 번 재생한다 */
const SILENT_WAV =
  'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA='

let unlocked = false
let currentAudio: HTMLAudioElement | null = null
let currentController: AbortController | null = null

function stopCurrent(): void {
  currentController?.abort()
  currentController = null

  if (currentAudio) {
    currentAudio.pause()
    currentAudio.removeAttribute('src')
    currentAudio = null
  }
}

export function useTts() {
  /**
   * 첫 사용자 조작(터치/클릭)에 맞춰 한 번 불러야 한다.
   *
   * 브라우저는 사용자 제스처 없이 나간 오디오 재생을 조용히 막는 경우가 많다.
   * 무음 오디오를 그 제스처 처리 안에서 한 번 재생해 두면, 그 뒤로는 이벤트
   * 핸들러 밖(예: MQTT 이벤트 콜백)에서도 재생이 허용된다.
   */
  function unlock(): void {
    if (unlocked) return
    unlocked = true

    const audio = new Audio(SILENT_WAV)
    audio.volume = 0
    audio.play().catch(() => {
      // 그래도 막히면 실제 재생 때 다시 시도된다 - 여기서는 조용히 넘긴다
    })
  }

  /**
   * 재생 중이거나 요청 중이던 문장이 있으면 끊고 새 문장을 읽는다.
   *
   * 위반은 '지금 상태'에 대한 지적이라, 여러 건이 잇달아 오면 최신 것만 들려주면
   * 된다 - 응답이 늦게 와도 그사이 취소됐으면(currentController 가 바뀌었으면) 버린다.
   */
  async function speak(text: string): Promise<void> {
    if (!text) return

    stopCurrent()
    const controller = new AbortController()
    currentController = controller

    try {
      const response = await fetch(TTS_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'xi-api-key': ELEVENLABS_API_KEY,
        },
        body: JSON.stringify({
          text,
          // 한국어를 읽어야 해서 다국어 모델을 쓴다 - 영어 전용 모델은 한국어를 못 읽는다
          model_id: 'eleven_multilingual_v2',
        }),
        signal: controller.signal,
      })

      if (!response.ok) {
        console.error(`[tts] 요청 실패 (${response.status})`, await response.text())
        return
      }

      const blob = await response.blob()
      if (currentController !== controller) return

      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      currentAudio = audio
      audio.addEventListener('ended', () => URL.revokeObjectURL(url))
      audio.addEventListener('error', () => URL.revokeObjectURL(url))
      await audio.play()
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      console.error('[tts] 재생 실패', error)
    }
  }

  return { speak, unlock }
}

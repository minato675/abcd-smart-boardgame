/**
 * 짧은 알림음 재생 (ElevenLabs Sound Effects API 로 미리 생성해 public/sounds 에 둔 정적 파일).
 *
 * 매번 바뀌는 문장을 읽는 TTS(useTts)와 달리 이 소리들은 고정 신호라, 이벤트마다
 * API 를 부르지 않고 한 번 생성해 둔 mp3 를 재생만 한다.
 *
 * <audio>.volume 은 1.0(원본 그대로)이 상한이라, 원본 mp3 자체가 조용하게
 * 만들어지면 그 이상 키울 수 없다. Web Audio 의 GainNode 는 1.0 을 넘겨 증폭할
 * 수 있어 이 방식을 쓴다 - 값을 올리면 더 커지고 내리면 더 작아진다.
 */
const DING_SRC = '/sounds/ding.mp3'
const ERROR_SRC = '/sounds/error.mp3'

/** 원본 대비 배율. 1 이 원본 음량, 3 이면 세 배로 증폭한다. 너무 올리면 찢어지는 소리가 날 수 있다. */
const DING_GAIN = 10
const ERROR_GAIN = 10

let audioContext: AudioContext | null = null
const bufferCache = new Map<string, Promise<AudioBuffer>>()

function getContext(): AudioContext {
  if (!audioContext) audioContext = new AudioContext()
  return audioContext
}

function loadBuffer(src: string): Promise<AudioBuffer> {
  let cached = bufferCache.get(src)
  if (!cached) {
    cached = fetch(src)
      .then((response) => response.arrayBuffer())
      .then((data) => getContext().decodeAudioData(data))
    bufferCache.set(src, cached)
  }
  return cached
}

async function play(src: string, gain: number): Promise<void> {
  try {
    const context = getContext()
    if (context.state === 'suspended') await context.resume()

    const buffer = await loadBuffer(src)
    const source = context.createBufferSource()
    source.buffer = buffer

    const gainNode = context.createGain()
    gainNode.gain.value = gain

    source.connect(gainNode)
    gainNode.connect(context.destination)
    source.start()
  } catch {
    // 재생 실패는 조용히 넘어간다 - 알림음이 안 나도 화면 동작에는 지장 없다
  }
}

export function useNotificationSound() {
  return {
    /**
     * 첫 사용자 제스처에서 한 번 불러야 한다 - AudioContext 는 그 전까지 'suspended'
     * 상태라 소리가 안 난다. useTts 의 unlock() 과 같은 이유, 같은 타이밍이다.
     */
    unlock: () => {
      void getContext().resume()
    },
    /** 마이크/호출어로 음성인식이 시작됐을 때, AI 심판 턴이 정상적으로 넘어갔을 때 */
    playDing: () => void play(DING_SRC, DING_GAIN),
    /** AI 심판이 규칙 위반을 잡아냈을 때 */
    playError: () => void play(ERROR_SRC, ERROR_GAIN),
  }
}

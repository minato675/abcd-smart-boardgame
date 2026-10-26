import { ref } from 'vue'

export type ToastTone = 'success' | 'danger'

export interface Toast {
  message: string
  tone: ToastTone
}

const toast = ref<Toast | null>(null)
let hideId: ReturnType<typeof setTimeout> | null = null

/** '대여버튼 클릭.html' 하단에 있던 완료 토스트 */
export function useToast() {
  function show(message: string, tone: ToastTone = 'success', ms = 2600): void {
    if (hideId) clearTimeout(hideId)
    toast.value = { message, tone }
    hideId = setTimeout(() => {
      toast.value = null
      hideId = null
    }, ms)
  }

  function hide(): void {
    if (hideId) clearTimeout(hideId)
    hideId = null
    toast.value = null
  }

  return { toast, show, hide }
}

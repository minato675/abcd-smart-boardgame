import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/**
 * 컨테이너의 실제 픽셀 너비를 따라간다.
 *
 * SVG 를 viewBox 로 늘리면 선 굵기와 글자까지 같이 늘어나서, 넓은 카드에서는
 * 2px 선이 3px 로 보이고 좁은 카드에서는 축 글자가 뭉갠다. 그래서 뷰포트에
 * 맞춰 늘리지 않고 측정한 너비로 좌표를 다시 계산한다.
 */
export function useChartWidth(element: Ref<HTMLElement | null>, fallback = 560) {
  const width = ref(fallback)
  let observer: ResizeObserver | null = null

  onMounted(() => {
    if (!element.value) return
    observer = new ResizeObserver((entries) => {
      const measured = entries[0]?.contentRect.width ?? 0
      // 레이아웃이 잡히기 전 0 이 들어오면 좌표가 전부 NaN 이 된다
      if (measured > 0) width.value = measured
    })
    observer.observe(element.value)
  })

  onBeforeUnmount(() => observer?.disconnect())

  return width
}

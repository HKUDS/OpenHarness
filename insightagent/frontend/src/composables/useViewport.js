import { ref } from 'vue'

// 全局共享的视口断点：≥900px 视为桌面端控制台，其余走移动端 App
const query = typeof window !== 'undefined' ? window.matchMedia('(min-width: 900px)') : null
const isDesktop = ref(query ? query.matches : false)

if (query) {
  const sync = (e) => {
    isDesktop.value = e.matches
  }
  if (query.addEventListener) query.addEventListener('change', sync)
  else query.addListener(sync)
}

export function useViewport() {
  return { isDesktop }
}

import { ref } from 'vue'

// Day / night theme. public/theme-boot.js resolves the saved or system choice
// onto <html data-theme> before the first paint; this module keeps it live.
const KEY = 'gm-theme'
const root = typeof document === 'undefined' ? null : document.documentElement

export const theme = ref(root?.dataset.theme === 'light' ? 'light' : 'dark')

// The pick also lives in memory, so a browser that refuses storage still keeps
// it for this session instead of following the system again.
let picked = null
function saved() {
  try { return localStorage.getItem(KEY) ?? picked } catch { return picked }
}

export function setTheme(next, { remember = true } = {}) {
  theme.value = next
  if (remember) picked = next
  if (!root) return
  root.dataset.theme = next
  if (remember) try { localStorage.setItem(KEY, next) } catch { /* private mode */ }
}

/** Track the OS setting until the user picks a theme; returns a cleanup. */
export function followSystem() {
  if (typeof matchMedia !== 'function') return () => {}
  const media = matchMedia('(prefers-color-scheme: light)')
  const changed = () => { if (!saved()) setTheme(media.matches ? 'light' : 'dark', { remember: false }) }
  media.addEventListener('change', changed)
  return () => media.removeEventListener('change', changed)
}

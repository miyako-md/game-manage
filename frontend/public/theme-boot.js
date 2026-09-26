// Runs before the first paint, so the saved or system theme never flashes the other one.
(() => {
  let theme = null
  try { theme = localStorage.getItem('gm-theme') } catch { /* private mode */ }
  if (theme !== 'light' && theme !== 'dark') theme = matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme
})()

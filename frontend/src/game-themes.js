// Game id -> skin key for game-themes.css; unknown games keep the neutral look.
const SKINS = { wuthering_waves: 'wuwa', nte: 'nte', endfield: 'endfield' }
export const skinOf = (gameId) => SKINS[gameId] || null
export const SKIN_KEYS = Object.values(SKINS)
export const SKIN_TOKENS = ['--skin-bg', '--skin-bg-grad', '--skin-surface', '--skin-line', '--skin-line-strong', '--skin-ink', '--skin-muted',
  '--skin-accent', '--skin-accent-2', '--skin-hot', '--skin-on-accent', '--skin-radius-card', '--skin-radius-tile', '--skin-radius-chip', '--skin-glow', '--skin-tint-rgb']

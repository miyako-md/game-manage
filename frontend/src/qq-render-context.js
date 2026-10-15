import { inject, nextTick } from 'vue'

export const QQ_RENDER_CONTEXT = Symbol('qq-render')
export const useQqRender = () => inject(QQ_RENDER_CONTEXT, null)

export function createQqRenderContext(input) {
  const pending = new Set()
  return {
    command: input.command, roleName: input.roleName || '', now: input.now,
    track(task) {
      const promise = Promise.resolve(task)
      pending.add(promise)
      promise.finally(() => pending.delete(promise)).catch(() => {})
      return promise
    },
    async settled() {
      // Watchers can start a second request when the first cached read settles.
      do { await Promise.allSettled([...pending]); await nextTick() } while (pending.size)
    },
  }
}

export function captureSection(game, command) {
  if (game === 'wuthering_waves') return ({roles:'roles',combat:'combat',activities:'activities',resources:'resources',gacha:'gacha',news:'news'})[command] || 'profile'
  if (game === 'endfield') return ({roles:'operators',exploration:'operators',combat:'challenges',gacha:'gacha',news:'news'})[command] || 'overview'
  return ({roles:'characters',exploration:'characters',realestate:'assets',vehicles:'assets',teams:'teams',gacha:'gacha',news:'news'})[command] || 'overview'
}

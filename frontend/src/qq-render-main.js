import { createApp, nextTick } from 'vue'
import './motion.css'
import './style.css'
import './qq-render.css'
import QqRenderApp from './QqRenderApp.vue'
import { configureHttpClient, setAccountScope } from './http-client.js'
import { createQqRenderContext, QQ_RENDER_CONTEXT } from './qq-render-context.js'

window.__QQ_RENDER_READY__ = false
try {
  const input = window.__QQ_RENDER__
  if (!input || input.version !== 1 || !Array.isArray(input.entries) || !Number.isFinite(input.now)
      || !['overview','summary','roles','stamina','progress','exploration','combat','gacha','calabash','activities','resources','realestate','vehicles','teams','record','news','calendar','events','recent_events'].includes(input.command)) throw new Error()
  configureHttpClient({ mode: 'cloud' })
  const entry = input.entries.find(row => row.account?.game === input.game) || input.entries[0]
  if (entry && input.command !== 'overview') setAccountScope({ user_id:'qq-render', account_id:entry.account.account_id, role_id:entry.role, provider:entry.account.provider })
  const context = createQqRenderContext(input)
  const app = createApp(QqRenderApp, { input })
  app.provide(QQ_RENDER_CONTEXT, context)
  app.config.errorHandler = () => { window.__QQ_RENDER_ERROR__ = 'qq_render_component_error' }
  app.mount('#app')
  await nextTick()
  await context.settled()
  if (!window.__QQ_RENDER_ERROR__) window.__QQ_RENDER_READY__ = true
} catch {
  window.__QQ_RENDER_ERROR__ = 'qq_render_invalid_input'
}

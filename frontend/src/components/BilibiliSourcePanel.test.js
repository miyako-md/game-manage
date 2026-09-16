import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const Panel = await loadVue(new URL('./BilibiliSourcePanel.vue', import.meta.url))
test('B站面板不把异常空列表称为历史完成，能查看过滤原因', async (t) => {
  const previous = globalThis.fetch
  globalThis.fetch = async path => ({ok:true,json:async()=>path.endsWith('/audit') ? {rows:[{
    id:'123',title:'版本PV',decision:'excluded',reason_text:'视频或转发视频',body:'9月15日PV',url:'https://t.bilibili.com/123',published_at:'2026-09-15T00:00:00Z',
  }]} : {sources:[{game_id:'nte',uid:'3546636978489848',status:'error',message:'动态列表异常为空',history_complete:false,total:0,accepted:0}],login:{configured:false}}})
  t.after(()=>{globalThis.fetch=previous})
  const root = mount(t, Panel, {})
  await new Promise(resolve=>setImmediate(resolve)); await nextTick()
  assert.match(content(root), /60天历史尚未完整回补/)
  assert.match(content(root), /动态列表异常为空/)
  await nodes(root,'button').find(n=>content(n)==='查看筛选记录').props.onClick()
  await nextTick()
  assert.match(content(root), /暂无符合条件的已采集记录/)
})

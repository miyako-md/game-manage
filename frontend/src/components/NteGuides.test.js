import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const Panel = await loadVue(new URL('./NteGuides.vue', import.meta.url))
const flush = async () => { await new Promise(setImmediate); await nextTick() }
const section = { key: 'weapons', title: '弧盘推荐', items: ['推荐甲弧盘'], note: '辅助适用', pages: [1] }
const catalog = { reviewed_at:'2026-09-26', sources: [
  { id:1, title:'原帖一', author:'作者', version:'1.3', url:'https://www.tajiduo.com/bbs/index.html#/post?postId=1' },
  { id:2, title:'原帖二', author:'作者', version:'1.4', url:'https://www.tajiduo.com/bbs/index.html#/post?postId=2' },
], guides: [
  { id:'甲', name:'甲', aliases:[], element:'魂', role:'主 C', status:'reviewed', source_id:1, pages:[1], sections:[section] },
  { id:'乙', name:'乙', aliases:['别名乙'], element:'灵', role:'辅助', status:'original_only', source_id:2, pages:[2], sections:[{...section,items:[]}] },
] }
const source = id => ({ id, images:['https://bbs-upload.tajiduo.com/1.png','https://bbs-upload.tajiduo.com/2.png'], paragraphs:['正文'], fetched_at:'2026-09-26T01:00:00Z', summary_changed:false })
function api(t, handler) { t.mock.method(globalThis,'fetch',async (url,init) => ({ ok:true,json:async()=>handler(url,init) })) }

test('public guides show reviewed advice, source version, original pages and owned filtering', async t => {
  api(t, url => url.endsWith('/guides') ? catalog : source(1))
  const root = mount(t, Panel, {roles:[{id:'r',name:'甲'}]}); await flush(); await flush()
  assert.match(content(root), /推荐甲弧盘/); assert.match(content(root), /V1.3/)
  assert.match(content(root), /辅助适用/)
  const filter = nodes(root,'input').find(n=>n.props.type==='checkbox')
  filter.props['onUpdate:modelValue'](true); await nextTick()
  assert.equal(nodes(root,'button').filter(n=>n.props['aria-label']==='查看乙攻略').length,0)
  filter.props['onUpdate:modelValue'](false); await nextTick()
  nodes(root,'button').find(n=>n.props['aria-label']==='查看乙攻略').props.onClick(); await flush()
  assert.match(content(root), /文字推荐待整理/)
  assert.doesNotMatch(content(root), /推荐甲弧盘/)
  assert.equal(nodes(root,'img').at(-1).props.src,'https://bbs-upload.tajiduo.com/2.png')
})

test('source change warns and a late source response cannot replace the selected role', async t => {
  let release
  api(t, url => url.endsWith('/guides') ? catalog : url.endsWith('/1') ? new Promise(resolve=>{release=resolve}) : {...source(2),summary_changed:true})
  const root=mount(t,Panel,{roles:[]});await flush()
  nodes(root,'button').find(n=>n.props['aria-label']==='查看乙攻略').props.onClick();await flush()
  release({...source(1),paragraphs:['旧请求正文']});await flush()
  assert.match(content(root),/原帖有更新/)
  assert.doesNotMatch(content(root),/旧请求正文/)
})

test('explicit refresh uses write protection and exposes stale fallback', async t => {
  let written
  api(t,(url,init)=>{
    if(url.endsWith('/guides'))return catalog
    if(url.endsWith('/refresh')){written=init;return {...source(1),stale:true,error:'原帖暂时无法读取'}}
    return source(1)
  })
  const root=mount(t,Panel,{roles:[]});await flush();await flush()
  await nodes(root,'button').find(n=>content(n)==='刷新原帖').props.onClick();await flush()
  assert.equal(written.method,'POST');assert.equal(written.headers['X-Game-Assistant'],'1')
  assert.match(content(root),/原帖暂时无法读取/);assert.match(content(root),/推荐甲弧盘/)
})

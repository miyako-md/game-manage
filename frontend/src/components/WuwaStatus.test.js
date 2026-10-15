import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
const Status=await loadVue(new URL('./WuwaStatus.vue',import.meta.url))

test('source failures retain the same safe badge before and after raw error redaction',t=>{
  const original={state:'source_error',stale:true,fetched_at:'2026-10-15T04:00:00Z',error:'secret-bearing upstream detail'}
  const website=mount(t,Status,{snap:original}),qq=mount(t,Status,{snap:{...original,error:undefined}})
  assert.equal(content(website),content(qq))
  assert.match(content(qq),/旧数据/)
  assert.match(content(qq),/来源读取异常/)
  assert.doesNotMatch(content(website),/secret-bearing/)
  assert.equal(nodes(qq,'span').filter(node=>node.props.role==='status').length,1)
})

test('status follows shared snapshot-state priority without mislabeling successful empty data',t=>{
  const failed=mount(t,Status,{snap:{state:'ok',poll_status:{state:'auth_expired'}}})
  // collectionState follows the explicit top-level snapshot state first.
  assert.doesNotMatch(content(failed),/来源读取异常/)
  for(const state of ['error','source_error','invalid_data','auth_expired']) assert.match(content(mount(t,Status,{snap:{state}})),/来源读取异常/)
  assert.match(content(mount(t,Status,{snap:{poll_status:{state:'error'}}})),/来源读取异常/)
  for(const state of ['ok','never','stale']) assert.doesNotMatch(content(mount(t,Status,{snap:{state,payload:[]}})),/来源读取异常/)
})

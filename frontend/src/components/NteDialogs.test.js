import test from 'node:test'
import assert from 'node:assert/strict'
import { h, nextTick, reactive } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
const Module = await loadVue(new URL('./NteModuleCard.vue', import.meta.url))
const button = (root,label)=>nodes(root,'button').find(n=>content(n)===label)

test('NTE detail is mounted only after opening and disposed on close/account switch',async t=>{
  let mounts=0
  const Detail={setup(){mounts++;return()=>h('p','实际详情内容')}}
  const props=reactive({capability:'roles',accountId:'a',snap:{payload:{schema_version:1,entries:[{name:'甲'}]}}})
  const Host={setup:()=>()=>h(Module,props,{default:()=>h(Detail)})}
  const root=mount(t,Host,{})
  assert.equal(mounts,0);assert.equal(nodes(root,'dialog').length,0)
  button(root,'查看角色练度').props.onClick();await nextTick()
  assert.equal(mounts,1);assert.match(content(nodes(root,'dialog')[0]),/实际详情内容/)
  button(root,'关闭详情').props.onClick();await nextTick()
  assert.equal(nodes(root,'dialog').length,0)
  button(root,'查看角色练度').props.onClick();await nextTick();props.accountId='b';await nextTick()
  assert.equal(nodes(root,'dialog').length,0)
})

test('unknown, zero and failure states stay visible in summary without opening dialog',t=>{
  const root=mount(t,Module,{capability:'stamina',snap:{stale:true,error:'上游暂不可用',payload:{schema_version:1,current:0,maximum:320,city_current:null,city_maximum:100}}})
  assert.match(content(root),/0 \/ 320/);assert.match(content(root),/未知 \/ 100/)
  assert.match(content(root),/上游暂不可用/);assert.match(content(root),/旧数据/)
})

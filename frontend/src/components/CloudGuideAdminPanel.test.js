import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
import { configureHttpClient, invalidateSession } from '../http-client.js'
const tick=async()=>{await new Promise(resolve=>setImmediate(resolve));await nextTick()}
const Panel=await loadVue(new URL('./CloudGuideAdminPanel.vue',import.meta.url))
const status=(job={})=>({
  job:{state:'idle',last_run:{started_at:'2026-10-21T21:30:00+00:00',finished_at:'2026-10-21T21:40:00+00:00',outcome:'stopped',stop_code:'http:429'},next_run_at:'2026-10-22T21:30:00+00:00',retry_after:0,...job},
  wuthering_waves:{roles_total:47,roles_checked:null,checked_at_oldest:null,
    pending:[{character_id:'1311',name:'心',post_id:'1555005846752059392',title:'V3.7心培养攻略一图流',author:'轩儿Xuaner',published_at:'2026-09-30T15:00:00Z'}],
    extraction_failed:[{character_id:'1102',name:'散华'}],failed:[{character_id:'1408',name:'漂泊者',error_code:'http:403'}]},
  tower:{checked_at:'2026-10-21T21:41:00+00:00',current_period_covered:null,error_code:null},
  nte:{posts:[{post_id:491439,title:'异环V1.3全角色养成一图流',fetched_at:null,summary_changed:true,stale:true,error:false}]}})
const button=(root,text)=>nodes(root,'button').find(n=>content(n)===text)

test('the card shows the job, pending posts and failures without turning unknown values into zero',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  const calls=[]
  t.mock.method(globalThis,'fetch',async(path,options)=>{calls.push([path,options.method]);return new Response(JSON.stringify(status()))})
  const root=mount(t,Panel);await tick()
  assert.deepEqual(calls,[['/api/admin/guides','GET']])
  const text=content(root)
  assert.match(text,/管理员 · 攻略更新/);assert.match(text,/已停止.*http:429/)
  assert.match(text,/已检查 未知 \/ 47 名/);assert.match(text,/最早一次检查：未知/)
  assert.match(text,/新帖未提炼 · 1 名/);assert.match(text,/心 · V3\.7心培养攻略一图流 · 轩儿Xuaner/)
  assert.match(text,/提炼失败 · 1 名/);assert.match(text,/漂泊者 · http:403/)
  assert.match(text,/当期收录情况未知/)
  assert.match(text,/读取于 未知 · 原帖有更新，摘要待复核 · 待更新/)
  assert.doesNotMatch(text,/已检查 0/)
})

test('立即检查 posts once with CSRF, then waits for the cooldown and polls a running job',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  t.mock.timers.enable({apis:['setTimeout','Date']})
  let row=status(),reads=0
  const posts=[]
  t.mock.method(globalThis,'fetch',async(path,options)=>{
    if(path.endsWith('/csrf'))return new Response(JSON.stringify({csrf_token:'fixture'}))
    if(options.method==='POST'){posts.push(options.headers['X-CSRF-Token']);row=status({state:'queued',retry_after:600});return new Response(JSON.stringify({state:'queued',retry_after:600}),{status:202})}
    reads++;return new Response(JSON.stringify(row))
  })
  const root=mount(t,Panel);await tick()
  await button(root,'立即检查').props.onClick();await tick()
  assert.deepEqual(posts,['fixture'])
  assert.match(content(root),/已排入后台检查/)
  assert.ok(button(root,'后台检查进行中').props.disabled)
  const before=reads
  row=status({state:'idle',last_run:{started_at:'2026-10-22T02:00:00+00:00',finished_at:'2026-10-22T02:05:00+00:00',outcome:'ok',stop_code:null},retry_after:300})
  t.mock.timers.tick(2500);await tick()
  assert.equal(reads,before+1)
  assert.match(content(root),/后台检查已完成/)
  assert.ok(button(root,'立即检查').props.disabled)
  assert.match(content(root),/冷却中/)
  await button(root,'立即检查').props.onClick();await tick()
  assert.equal(posts.length,1)
})

test('a 429 shows the cooldown and a 503 keeps the button usable later',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  let answer={detail:'guide_check_cooldown',retry_after:120},code=429
  t.mock.method(globalThis,'fetch',async(path,options)=>{
    if(path.endsWith('/csrf'))return new Response(JSON.stringify({csrf_token:'fixture'}))
    if(options.method==='POST')return new Response(JSON.stringify(answer),{status:code,headers:{'Retry-After':'120'}})
    return new Response(JSON.stringify(status()))
  })
  const root=mount(t,Panel);await tick()
  await button(root,'立即检查').props.onClick();await tick()
  assert.match(content(root),/立即检查冷却中，请稍后再试/)
  assert.ok(button(root,'立即检查').props.disabled)
  const other=mount(t,Panel);await tick()
  answer={detail:'scheduler_unavailable'};code=503
  await button(other,'立即检查').props.onClick();await tick()
  assert.match(content(other),/后台调度暂不可用/)
  assert.equal(button(other,'立即检查').props.disabled,false)
})

test('website invalidation clears the card and ignores a late status',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  t.mock.timers.enable({apis:['setTimeout']})
  let release,reads=0
  t.mock.method(globalThis,'fetch',async()=>{reads++;return new Promise(resolve=>{release=()=>resolve(new Response(JSON.stringify(status())))})})
  const root=mount(t,Panel);await tick()
  invalidateSession();release();await tick()
  assert.doesNotMatch(content(root),/新帖未提炼/)
  t.mock.timers.tick(100000);await tick()
  assert.equal(reads,1)
})

test('new posts are grouped by what they wait for; an unextracted one can be extracted from the card',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  const row=status()
  const item=(id,name,state,extra={})=>({character_id:id,name,attribute:'',post_id:'15'+id,title:`${name}培养攻略`,author:'轩儿Xuaner',published_at:'2026-10-01T00:00:00Z',
    url:`https://www.kurobbs.com/forum/post/15${id}`,kind:'article',state,has_static:state!=='not_extracted',...extra})
  row.wuthering_waves.pending=[item('1311','心','not_extracted'),item('1209','莫宁','extracted_empty'),item('1211','秧秧·玄翎','awaiting_review'),item('1102','散华','not_extracted',{kind:'video'})]
  row.nte={...row.nte,author_checked_at:'2026-10-27T21:31:00Z',new_posts:[{id:515374,title:'异环角色 | V1.4明音凛培养攻略一图流',role:'明音凛',known_role:false,published_at:'2026-10-07T00:00:00Z',url:'https://www.tajiduo.com/bbs/index.html#/post?postId=515374&id=2'}]}
  const posts=[]
  t.mock.method(globalThis,'fetch',async(path,options)=>{
    if(path.endsWith('/csrf'))return new Response(JSON.stringify({csrf_token:'fixture'}))
    if(options.method==='POST'){posts.push([path,JSON.parse(options.body)]);return new Response(JSON.stringify({candidates:[]}))}
    return new Response(JSON.stringify(row))})
  const root=mount(t,Panel);await tick()
  const text=content(root)
  assert.match(text,/新帖未提炼 · 2 名.*心 · 心培养攻略.*已提炼，但没识别到内容 · 1 名.*线上没有图片识别（OCR）.*莫宁.*已提炼，待人工核对 · 1 名.*秧秧·玄翎/)
  assert.match(text,/有新攻略帖待收录 · 1 篇.*明音凛 · 异环角色 \| V1\.4明音凛培养攻略一图流.*攻略页已先展示原图/)
  const links=nodes(root,'a').map(a=>a.props.href)
  assert.ok(links.includes("https://www.kurobbs.com/forum/post/151209") && links.some(href=>href.includes('postId=515374')))
  // Only the unextracted article gets the button; a video cannot be extracted.
  assert.equal(nodes(root,'button').filter(n=>content(n)==='立即提炼').length,1)
  button(root,'立即提炼').props.onClick();await tick();await tick()
  assert.deepEqual(posts,[['/api/admin/wuwa/guides/updates/extract',{character_id:'1311',name:'心',attribute:'',post_id:'151311'}]])
  assert.match(content(root),/已提炼 心 的新帖/)
})


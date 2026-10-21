import {createApp,nextTick} from 'vue'
import LabRoot from './LabRoot.vue'
import {configure} from './models.js'
import {auditLayout} from './layout-audit.js'
import {skinOf} from '../game-themes.js'
import '../style.css'
import '../wuwa.css'
import '../render.css'
import './lab.css'
import './font-primary.css'
import './reuse.css'
import './shared-charts.css'
import './endfield-image.css'
import './guide-image.css'
import './skin.css'
import './skin-wuwa.css'
import './skin-nte.css'
import './skin-endfield.css'

let app=null
const frame=()=>new Promise(resolve=>requestAnimationFrame(resolve))
window.disposeLongRender=async()=>{
 if(app)app.unmount()
 app=null;configure([],{})
 document.querySelector('#app').replaceChildren()
 await nextTick();await frame()
}
window.mountLongRender=async request=>{
 const state={job_id:request.job_id,input_fingerprint:request.input_fingerprint}
 window.__LONG_RENDER_STATE__={...state,state:'loading'}
 try{
  await window.disposeLongRender()
  const snapshot=request.snapshot
  // A skinned game image starts from the website's validated dark tokens; the skin then overrides the surfaces.
  document.documentElement.dataset.theme=skinOf(snapshot.game)?'dark':'light'
  let command=snapshot.next_command
  if(snapshot.kind==='wuwa_role')command='鸣潮 角色 '+(snapshot.display_data.detail.role?.role_name||'详情')
  if(snapshot.kind==='nte_role')command='异环 角色'+(snapshot.display_data.snapshot.display_mode==='detail'?' '+(snapshot.display_data.snapshot.payload.entries?.[0]?.name||'详情'):'')
  const input={snapshot,scheme:'dossier',command,origin:'',id:snapshot.kind==='notice'&&/帮助/.test(snapshot.title)?'help':snapshot.kind}
  configure([input],Object.fromEntries(request.asset_urls.map(url=>[url,true])))
  app=createApp(LabRoot,{input});app.mount('#app');await nextTick()
  for(const details of document.querySelectorAll('.reuse details:not([data-render-collapsed])'))details.open=true
  for(const e of document.querySelectorAll('.reuse .t-item,.reuse .t-panel,.reuse [data-reveal]')){e.style.opacity='1';e.style.transform='none'}
  const root=document.querySelector('.lab-sheet'),decoded=new WeakMap(),missing=new Set()
  for(let round=0;round<8;round++){
   const pending=[...root.querySelectorAll('img')].filter(img=>decoded.get(img)!==img.getAttribute('src'))
   if(!pending.length)break
   await Promise.all(pending.map(async img=>{
    const source=img.getAttribute('src');img.loading='eager'
    try{await img.decode();decoded.set(img,source)}catch{
     missing.add(img.alt||'图标');img.dispatchEvent(new Event('error'));await nextTick()
     if(img.isConnected&&img.getAttribute('src')===source){
      const replacement=document.createElement('span');replacement.className='render-missing-image'
      replacement.textContent=img.alt||'图片暂不可用';img.replaceWith(replacement)
     }
    }
   }))
   await nextTick()
  }
  if([...root.querySelectorAll('img')].some(img=>!img.complete||!img.naturalWidth))throw Error('unresolved_image')
  await document.fonts.ready;await frame();await frame()
  const box=root.getBoundingClientRect(),overflow=[]
  for(const e of root.querySelectorAll('*')){const b=e.getBoundingClientRect();if(b.width&&b.height&&(b.left<box.left-2||b.right>box.right+2||b.bottom>box.bottom+2))overflow.push('outside_image')}
  const audit=auditLayout(root,root),badNames=[...root.innerText.matchAll(/角色[ \t]*\d{3,}|共鸣者[ \t]*\d{3,}|角色\/弧盘|fork_[a-z_]+|CHARACTER_[A-Z_]+|char_\d+_[a-z]+/g)].map(m=>m[0])
  window.__LONG_RENDER_STATE__={...state,state:'ready',width:Math.ceil(box.width),height:Math.ceil(box.height),overflow,layout_issues:audit.issueCount,layout_details:audit.issues.slice(0,8),bad_names:badNames.length,bad_name_matches:badNames.slice(0,4),missing_assets:[...missing]}
 }catch{window.__LONG_RENDER_STATE__={...state,state:'failed',error:'render_readiness_failed'}}
}

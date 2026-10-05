// Bilibili uses Geetest v3; keep this separate from the games' v4 widget.
let loading
export function loadBilibiliGeetest() {
  if(globalThis.window?.initGeetest) return Promise.resolve(window.initGeetest)
  if(loading) return loading
  const pending=new Promise((resolve,reject)=> {
    if(!globalThis.document) {reject(new Error('验证码组件无法加载，请重试'));return}
    const script=document.createElement('script')
    script.src='https://static.geetest.com/static/tools/gt.js';script.async=true;script.referrerPolicy='no-referrer'
    const timer=setTimeout(()=>fail(),15000)
    function fail() { clearTimeout(timer);script.remove();reject(new Error('验证码组件无法加载，请重试')) }
    script.onerror=fail
    script.onload=()=>{clearTimeout(timer);if(window.initGeetest)resolve(window.initGeetest);else fail()}
    document.head.appendChild(script)
  })
  loading=pending.catch(error=>{loading=undefined;throw error})
  return loading
}

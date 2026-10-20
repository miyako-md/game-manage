<script setup>
defineProps({data:{type:Object,required:true}})
function splitItem(text){
 if(typeof text!=='string')return null
 const idx=text.indexOf('：')
 if(idx<=0||idx>=text.length-1||idx>18)return null
 return [text.slice(0,idx),text.slice(idx+1)]
}
</script>
<template>
 <div class="render-notice">
  <section class="cap-card" data-render-block><header v-if="data.title" class="cap-title"><h2>{{ data.title }}</h2></header>
   <div class="notice-sections">
    <section v-for="(section,i) in data.sections || []" :key="i" class="notice-section" data-render-block>
     <h3 v-if="section.title" class="notice-heading">{{ section.title }}</h3>
     <ul class="item-list">
      <li v-for="(item,j) in section.items || []" :key="j" class="item" data-render-block>
       <p v-if="splitItem(item)" class="notice-text is-kv"><span class="notice-label">{{ splitItem(item)[0] }}</span><span class="notice-sep">：</span><code class="notice-cmd">{{ splitItem(item)[1] }}</code></p>
       <p v-else class="notice-text">{{ item }}</p>
      </li>
     </ul>
    </section>
   </div>
   <div v-if="data.notices?.length" class="notice-callouts">
    <p v-for="(notice,i) in data.notices || []" :key="i" class="notice-text notice-callout" data-render-block>{{ notice }}</p>
   </div>
  </section>
 </div>
</template>
<style scoped>
.render-notice{display:grid;gap:12px}.notice-section{margin-top:12px}.notice-heading{font-size:14px;font-weight:600;color:var(--text)}.notice-text{font-size:13px;line-height:1.7;color:var(--text-body);overflow-wrap:anywhere}.notice-text.is-kv{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}.notice-label{color:var(--text-muted);font-weight:500}.notice-sep{color:var(--text-faint)}.notice-cmd{margin-left:auto;padding:2px 8px;border-radius:6px;background:var(--surface-soft);border:1px solid var(--border);font-family:var(--font-sans);font-size:12px;font-weight:600;color:var(--text)}.item{padding:8px 0;border-bottom:1px solid var(--border)}.item:last-child{border-bottom:0}.notice-callouts{margin-top:14px;padding:12px 16px;border-radius:12px;background:var(--surface-soft);border:1px solid var(--border);display:grid;gap:6px}.cap-title h2{font-size:15px;font-weight:600}
</style>

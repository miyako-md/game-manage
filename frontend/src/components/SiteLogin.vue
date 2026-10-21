<script setup>
import { ref, onBeforeUnmount } from 'vue'
import { loginSite, registerSite } from '../identity-api.js'
import GameIcon from './GameIcon.vue'
import { gameVars } from '../dashboard.js'
const emit = defineEmits(['authenticated'])
const GAMES = [{ id: 'wuthering_waves', name: '鸣潮' }, { id: 'nte', name: '异环' }, { id: 'endfield', name: '终末地' }]
const registering = ref(false), username = ref(''), password = ref(''), invite = ref(''), error = ref(''), busy = ref(false)
let disposed = false
onBeforeUnmount(() => { disposed = true; password.value = ''; invite.value = '' })
async function submit() {
  if (busy.value) return
  busy.value = true; error.value = ''
  const body = { username: username.value.trim(), password: password.value, invite: invite.value.trim() }
  try { const user = await (registering.value ? registerSite(body) : loginSite(body)); if (!disposed) emit('authenticated', user) }
  catch (failure) { if (!disposed && failure.name !== 'AbortError') error.value = failure.status === 401 ? '用户名或密码不正确' : failure.message }
  finally { password.value = ''; invite.value = ''; if (!disposed) busy.value = false }
}
</script>
<template>
  <section class="site-login">
    <div class="site-login-art">
      <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
      <div class="site-login-tiles" aria-hidden="true"><span v-for="game in GAMES" :key="game.id" class="login-tile" :style="gameVars(game.id)"><GameIcon :game-id="game.id" /><b>{{ game.name }}</b></span></div>
      <p class="site-login-games">鸣潮 · 异环 · 终末地</p>
    </div>
    <div class="site-login-panel">
      <p class="eyebrow">游戏管家</p><h1>{{ registering ? '邀请注册' : '网站登录' }}</h1>
      <form @submit.prevent="submit">
        <label>用户名<input name="username" v-model="username" autocomplete="username" required maxlength="64" /></label>
        <small v-if="registering">3–64 位字母、数字、_、. 或 -</small>
        <label>密码<input name="password" v-model="password" type="password" :autocomplete="registering ? 'new-password' : 'current-password'" required :minlength="registering ? 12 : 1" maxlength="128" /></label>
        <label v-if="registering">邀请码<input name="invite" v-model="invite" autocomplete="off" required maxlength="128" /></label>
        <p v-if="error" role="alert">{{ error }}</p>
        <button class="ui-button primary" :disabled="busy">{{ busy ? '正在验证…' : registering ? '注册并登录' : '登录' }}</button>
      </form>
      <button type="button" class="text-link" :disabled="busy" @click="registering = !registering; error = ''; password = ''; invite = ''">{{ registering ? '已有账号，去登录' : '使用邀请码注册' }}</button>
    </div>
  </section>
</template>
<style scoped>
/* One white card: the three games as tone tiles on a warm panel beside the form (game-manage-ui-v1). */
.site-login{width:min(100%,900px);margin:7vh auto;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,420px);overflow:hidden;border:1px solid var(--card-border);border-radius:var(--radius-shell);background:var(--card-bg);box-shadow:var(--card-shadow)}
.site-login-art{position:relative;display:flex;flex-direction:column;justify-content:space-between;gap:24px;min-height:460px;margin:7px;padding:26px;overflow:hidden;border-radius:calc(var(--radius-shell) - 7px);background:var(--control-track)}
.site-login-tiles{position:relative;height:210px}
.login-tile{position:absolute;display:grid;justify-items:start;align-content:space-between;width:150px;height:150px;padding:14px;border:4px solid var(--card-bg);border-radius:30px;background:var(--game-tone);box-shadow:0 18px 40px -24px rgba(38,40,46,.45);color:var(--game-accent)}
.login-tile:nth-child(1){left:0;top:44px;transform:rotate(-8deg)}
.login-tile:nth-child(2){left:31%;top:0;z-index:2;transform:rotate(3deg)}
.login-tile:nth-child(3){left:60%;top:56px;transform:rotate(10deg)}
.login-tile .game-icon{width:44px;height:44px;border-radius:13px;background:var(--card-bg);font-size:18px;font-weight:600}
.login-tile b{font-size:17px;font-weight:600}
.site-login-games{margin:0;color:var(--text);font-size:22px;font-weight:600;line-height:30px;letter-spacing:-.02em}
.site-login-panel{display:grid;align-content:center;gap:18px;padding:44px 40px}
.site-login form{display:grid;gap:14px}.site-login label{display:grid;gap:7px;font-size:13px;font-weight:500}
.site-login input{width:100%;min-width:0;min-height:44px;box-sizing:border-box;padding:10px 13px;border:1px solid var(--field-border,var(--border));border-radius:var(--radius-control);background:var(--field-bg,var(--card-bg));color:var(--text);font-weight:400}
.site-login input:focus-visible{background:var(--card-bg);border-color:var(--accent);outline:none;box-shadow:var(--ring)}
.site-login .ui-button.primary{min-height:44px;margin-top:4px}
h1,p{margin:0}h1{font-size:28px;font-weight:600;line-height:36px;letter-spacing:-.03em}p{line-height:1.6}small{font-size:12px;color:var(--text-muted)}p[role=alert]{color:var(--danger);font-size:13px}
.site-login .text-link{justify-self:start}
@media(max-width:760px){.site-login{grid-template-columns:1fr;margin:3vh auto}.site-login-art{min-height:0;padding:20px}.site-login-tiles{height:130px}.login-tile{width:96px;height:96px;padding:10px;border-radius:22px}.login-tile .game-icon{width:32px;height:32px;border-radius:10px;font-size:14px}.login-tile b{font-size:14px}.site-login-games{font-size:19px;line-height:26px}.site-login-panel{padding:28px 22px}}
</style>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { accountRequest, AccountError } from '../accountAccess'
import type { AccountUser, RegistrationPolicy } from '../accountAccess'
import ProjectLicense from './ProjectLicense.vue'
const props = defineProps<{ base: string; initialInvite?: string; resetToken?: string; sessionNotice?: string }>()
const emit = defineEmits<{ authenticated: [result: { access_token: string; browser_session?:string|null; user: AccountUser }]; consumed: [] }>()
const view = ref<'login' | 'register' | 'recover' | 'reset'>(props.resetToken ? 'reset' : props.initialInvite ? 'register' : 'login')
const policy = ref<RegistrationPolicy | null>(null)
const username = ref(''), name = ref(''), password = ref(''), confirm = ref(''), showPassword = ref(false)
const rememberMe = ref(false)
const invite = ref(props.initialInvite || ''), preview = ref<Record<string, any> | null>(null), teacherApply = ref(false), reason = ref(''), recoveryNote = ref('')
const busy = ref(false), notice = ref(''), error = ref(''), challenge = ref<{ id: string; image: string } | null>(null), challengeAnswer = ref('')
let alive = true, previewGeneration = 0
const resetSecret = ref(props.resetToken || '')
const canApplyTeacher = computed(() => Boolean(policy.value?.teacher_applications && preview.value?.kind !== 'teacher' && !preview.value?.course_title))
watch(canApplyTeacher, allowed => { if (!allowed) teacherApply.value = false })
async function loadPolicy() {
  error.value = ''
  try { const data = await accountRequest<RegistrationPolicy>(props.base, '', '/auth/registration-policy'); if (alive) policy.value = data }
  catch (e) { if (alive) error.value = (e as Error).message }
}
async function loadChallenge() {
  try { const data = await accountRequest<{ id: string; image: string }>(props.base, '', '/auth/challenge'); if (alive) { challenge.value = data; challengeAnswer.value = '' } }
  catch (e) { error.value = (e as Error).message }
}
function switchView(value: typeof view.value) {
  if (busy.value) return
  view.value = value; password.value = ''; confirm.value = ''; showPassword.value = false; error.value = ''; notice.value = ''; challenge.value = null; challengeAnswer.value = ''
  if (value === 'register') { void loadPolicy(); if (invite.value) void checkInvite() }
}
async function checkInvite() {
  const generation = ++previewGeneration, code = invite.value
  preview.value = null; error.value = ''
  if (!code.trim()) return
  try { const data = await accountRequest<Record<string, any>>(props.base, '', '/auth/invite-preview', { code }); if (alive && generation === previewGeneration && invite.value === code) preview.value = data }
  catch (e) { if (generation === previewGeneration) error.value = (e as Error).message }
}
async function submit() {
  if (busy.value) return
  error.value = ''; notice.value = ''
  if (['register', 'reset'].includes(view.value) && password.value !== confirm.value) { error.value = '两次输入的密码不一致。'; return }
  if (view.value === 'register' && policy.value?.mode === 'closed') { error.value = '暂不开放注册，请联系管理员。'; return }
  busy.value = true
  const extra = { challenge_id: challenge.value?.id || '', challenge_answer: challengeAnswer.value }
  try {
    if (view.value === 'login') {
      const result = await accountRequest<{ access_token: string; user: AccountUser }>(props.base, '', '/auth/login', { username: username.value.trim(), password: password.value, remember_me: rememberMe.value, ...extra })
      if (alive) emit('authenticated', result)
    } else if (view.value === 'register') {
      const result = await accountRequest<{ message: string }>(props.base, '', '/auth/register', { username: username.value.trim(), display_name: name.value.trim(), password: password.value, invite_code: invite.value.trim(), teacher_reason: canApplyTeacher.value && teacherApply.value ? reason.value : '', ...extra })
      switchViewAfter('login'); notice.value = result.message + ' 请使用刚设置的密码登录。'; emit('consumed')
    } else if (view.value === 'recover') {
      const result = await accountRequest<{ message: string }>(props.base, '', '/auth/recover', { username: username.value.trim(), note: recoveryNote.value, ...extra })
      notice.value = result.message
    } else {
      const result = await accountRequest<{ message: string }>(props.base, '', '/auth/reset-password', { token: resetSecret.value, password: password.value, ...extra })
      resetSecret.value = ''; emit('consumed'); switchViewAfter('login'); notice.value = result.message
    }
  } catch (e) {
    error.value = (e as Error).message
    if (e instanceof AccountError && (e.challenge || challenge.value)) await loadChallenge()
  } finally { busy.value = false }
}
function switchViewAfter(value: typeof view.value) { view.value = value; password.value = ''; confirm.value = ''; challenge.value = null; challengeAnswer.value = '' }
onMounted(() => { void loadPolicy(); if (invite.value) void checkInvite() })
onUnmounted(() => { alive = false; password.value = ''; confirm.value = ''; resetSecret.value = '' })
</script>

<template>
  <section class="auth-shell account-access">
    <div class="auth-card account-access-card">
      <div class="account-brand"><span aria-hidden="true">✦</span><div><strong>智学助手</strong><small>课程 · 学习 · AI 助手</small></div></div>
      <h1>{{ view === 'register' ? '开启你的课程空间' : view === 'recover' ? '找回账号密码' : view === 'reset' ? '设置新的登录密码' : '欢迎回到课程空间' }}</h1>
      <p class="account-muted">{{ view === 'register' ? '一个账号，连接你的课程与学习记录。' : view === 'recover' ? '填写账号和核实线索，由管理员协助处理。' : view === 'reset' ? '重置后，其他设备上的旧登录将失效。' : '继续学习、准备教学，或管理你的平台。' }}</p>
      <nav v-if="view === 'login' || view === 'register'" class="account-tabs" aria-label="登录与注册"><button :aria-pressed="view === 'login'" :disabled="busy" @click="switchView('login')">登录</button><button :aria-pressed="view === 'register'" :disabled="busy" @click="switchView('register')">注册账号</button></nav>
      <p v-if="!policy" class="account-muted"><span class="ui-spinner" aria-hidden="true" />读取注册设置… <button type="button" @click="loadPolicy">重试</button></p>
      <p v-if="view === 'register' && policy?.mode === 'closed'" class="account-notice">当前暂停注册。已有账号仍可登录，请联系管理员获取帮助。</p>
      <form class="account-form" :aria-busy="busy" @submit.prevent="submit">
        <fieldset :disabled="busy">
          <template v-if="view !== 'reset'"><label>登录账号<input v-model="username" autocomplete="username" :minlength="view === 'register' ? 3 : 1" maxlength="80" :pattern="view === 'register' ? '[A-Za-z0-9][A-Za-z0-9_.-]{2,79}' : undefined" required placeholder="学号或自定义账号" /><small v-if="view === 'register'">字母、数字、点、下划线或短横线，至少3个字符。</small></label></template>
          <template v-if="view === 'register'">
            <label>姓名<input v-model="name" autocomplete="name" required maxlength="120" placeholder="便于教师识别你的姓名" /></label>
            <label>{{ policy?.mode === 'invite' ? '邀请码' : '邀请码（选填）' }}<div class="account-inline"><input v-model="invite" :required="policy?.mode === 'invite'" maxlength="80" autocapitalize="characters" autocomplete="off" placeholder="输入邀请人提供的邀请码" @input="preview = null" @blur="checkInvite" /><button type="button" @click="checkInvite">核对</button></div></label>
            <div v-if="preview" class="account-invite-preview"><strong>{{ preview.course_title || preview.label }}</strong><small>{{ [preview.semester, preview.teacher].filter(Boolean).join(' · ') }}</small><span>{{ preview.kind === 'teacher' ? '管理员发出的教师邀请' : preview.approval_required ? '加入课程需教师审核' : preview.course_title ? '注册后加入这门课程' : '平台账号邀请' }}</span></div>
            <label v-if="canApplyTeacher" class="account-check"><input v-model="teacherApply" type="checkbox" />申请教师身份（需管理员审核）</label>
            <label v-if="canApplyTeacher && teacherApply">教师申请说明<textarea v-model="reason" minlength="8" maxlength="500" required rows="3" placeholder="任教信息、教学用途及可核实的联系方式" /><small>课程学生邀请码不用于教师申请。申请获批前保持学生权限。</small></label>
          </template>
          <label v-if="view !== 'recover'">{{ view === 'reset' ? '新密码' : '密码' }}<div class="account-password"><input v-model="password" :type="showPassword ? 'text' : 'password'" :autocomplete="view === 'login' ? 'current-password' : 'new-password'" :minlength="view === 'login' ? 1 : 15" maxlength="200" required :placeholder="view === 'login' ? '输入登录密码' : '至少15个字符，可用易记长句'" /><button type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</button></div></label>
          <label v-if="view === 'register' || view === 'reset'">确认密码<input v-model="confirm" type="password" autocomplete="new-password" minlength="15" maxlength="200" required placeholder="再次输入密码" /><small>建议使用易记长句，不要求大写字母或特殊符号。</small></label>
          <label v-if="view === 'login'" class="account-check"><input v-model="rememberMe" type="checkbox" />7天免登录</label>
          <label v-if="view === 'recover'">身份核实线索<textarea v-model="recoveryNote" rows="4" minlength="5" maxlength="500" required placeholder="例如：姓名、任课教师，以及可与管理员约定的联系方式。不要填写密码或证件号码。" /></label>
          <div v-if="challenge" class="account-challenge"><img :src="challenge.image" alt="图形验证码，点击右侧按钮可换一张" /><button type="button" @click="loadChallenge">换一张</button><label>验证码<input v-model="challengeAnswer" autocomplete="off" maxlength="5" required placeholder="不区分大小写" /></label></div>
          <button class="account-primary" type="submit" :disabled="view === 'register' && (!policy || policy.mode === 'closed')"><span v-if="busy" class="ui-spinner" aria-hidden="true" />{{ busy ? '正在处理，请稍候…' : view === 'login' ? '登录课程空间' : view === 'register' ? '创建账号' : view === 'recover' ? '提交找回申请' : '确认重置密码' }}</button>
        </fieldset>
      </form>
      <p v-if="error" class="account-error" role="alert">{{ error }}</p><p v-if="sessionNotice && view==='login'" class="account-notice" role="status">{{ sessionNotice }}</p><p v-if="notice" class="account-notice" role="status">{{ notice }}</p>
      <div class="account-footlinks"><button v-if="view === 'login'" :disabled="busy" @click="switchView('recover')">忘记密码？</button><button v-else :disabled="busy" @click="switchView('login')">已有账号，返回登录</button></div>
      <ProjectLicense />
    </div>
  </section>
</template>

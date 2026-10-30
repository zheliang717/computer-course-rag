<script setup lang="ts">
import ProjectLicense from './ProjectLicense.vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import DetailDialog from './DetailDialog.vue'
import SessionManager from './SessionManager.vue'
import AccountAvatar from './AccountAvatar.vue'
import AvatarEditor from './AvatarEditor.vue'
import type { AvatarState } from '../avatars'
import { accountRequest, accountStateLabel, AccountError } from '../accountAccess'
import type { AccountUser } from '../accountAccess'
const props = defineProps<{ base: string; token: string; user: AccountUser; avatar: AvatarState; initialInvite?: string }>()
const emit = defineEmits<{ close: []; updated: [name: string]; avatarUpdated: [value: AvatarState]; changed: []; signout: [] }>()
const avatarBusy = ref(false), avatarDirty = ref(false)
const profile = ref<Record<string, any> | null>(null), name = ref(''), contact = ref(''), busy = ref(false), loading = ref(true), error = ref(''), notice = ref('')
const code = ref(props.initialInvite || ''), preview = ref<Record<string, any> | null>(null), currentPassword = ref(''), newPassword = ref(''), confirm = ref(''), confirmed = ref(false), teacherReason = ref('')
const challenge = ref<{ id: string; image: string } | null>(null), challengeAnswer = ref('')
const leaving = ref(false)
const dirty = computed(() => avatarDirty.value || Boolean(profile.value && (name.value !== profile.value.display_name || contact.value !== profile.value.contact || code.value || currentPassword.value || newPassword.value || confirm.value || teacherReason.value)))
function close() { if (dirty.value) leaving.value = true; else emit('close') }
let alive = true
const req = <T,>(path: string, body?: unknown, method?: string) => accountRequest<T>(props.base, props.token, path, body, method)
async function load() {
  loading.value = true
  try { const result = await req<Record<string, any>>('/accounts/profile'); if (alive) { const untouched = !profile.value || (name.value === profile.value.display_name && contact.value === profile.value.contact); profile.value = result; if (untouched) { name.value = result.display_name; contact.value = result.contact } } }
  catch (e) { error.value = (e as Error).message }
  finally { loading.value = false }
}
async function action(fn: () => Promise<void>) {
  if (busy.value || avatarBusy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn() } catch (e) {
    error.value = (e as Error).message
    if (e instanceof AccountError && (e.challenge || challenge.value)) await refreshChallenge()
  } finally { busy.value = false }
}
async function refreshChallenge() {
  try { challenge.value = await req<{ id: string; image: string }>('/auth/challenge'); challengeAnswer.value = '' }
  catch (e) { error.value = (e as Error).message }
}
async function save() {
  await action(async () => { const result = await req<Record<string, any>>('/accounts/profile', { display_name: name.value, contact: contact.value }, 'PATCH'); profile.value = result; name.value = result.display_name; contact.value = result.contact; emit('updated', result.display_name); notice.value = '个人资料已保存。' })
}
async function checkCode() {
  const value = code.value; preview.value = null
  await action(async () => { const result = await req<Record<string, any>>('/auth/invite-preview', { code: value }); if (code.value === value) preview.value = result })
}
async function join() {
  await action(async () => { const result = await req<{ message: string }>('/accounts/join-course', { code: code.value }); notice.value = result.message; code.value = ''; preview.value = null; await load(); emit('changed') })
}
async function password() {
  if (newPassword.value !== confirm.value) { error.value = '两次输入的新密码不一致。'; return }
  await action(async () => {
    await req('/accounts/password', { current_password: currentPassword.value, new_password: newPassword.value, challenge_id: challenge.value?.id || '', challenge_answer: challengeAnswer.value })
    currentPassword.value = ''; newPassword.value = ''; confirm.value = ''; emit('signout')
  })
}
async function apply() {
  await action(async () => { const result = await req<{ message: string }>('/accounts/teacher-application', { reason: teacherReason.value }); notice.value = result.message; teacherReason.value = ''; await load() })
}
onMounted(() => { void load() })
onUnmounted(() => { alive = false; currentPassword.value = ''; newPassword.value = ''; confirm.value = '' })
</script>
<template>
  <DetailDialog title="个人中心" kicker="MY ACCOUNT" :close-disabled="busy || avatarBusy" @close="close">
    <div class="profile-summary">
      <AccountAvatar :name="user.display_name" :identity="user.username" :image="avatar.image" />
      <div><strong>{{ user.display_name }}</strong><p>账号：{{ user.username }}</p></div>
      <span class="profile-role">{{ user.role_label }}</span>
    </div>
    <p v-if="loading" role="status"><span class="ui-spinner" aria-hidden="true" />正在读取账号信息…</p>
    <p v-if="error" class="account-error" role="alert">{{ error }} <button v-if="!profile" @click="load">重试</button></p><p v-if="notice" class="account-notice" role="status">{{ notice }}</p>
    <AvatarEditor v-if="profile" :base="base" :token="token" :avatar="avatar" :disabled="busy" @busy="avatarBusy = $event" @dirty="avatarDirty = $event" @updated="emit('avatarUpdated', $event)" />
    <div v-if="profile" class="account-settings-layout" :inert="avatarBusy">
      <section><h3>基本资料</h3><form class="account-form" @submit.prevent="save"><fieldset :disabled="busy"><label>姓名<input v-model="name" required maxlength="120" autocomplete="name" /></label><label>联系信息（选填）<input v-model="contact" maxlength="200" placeholder="供管理员线下核实使用，不会自动发送邮件" /></label><button class="account-primary" type="submit">保存资料</button></fieldset></form></section>
      <section v-if="user.role === 'student'"><h3>加入课程</h3><form class="account-form" @submit.prevent="join"><fieldset :disabled="busy"><label>课程邀请码<div class="account-inline"><input v-model="code" required maxlength="80" placeholder="向任课教师获取邀请码" @input="preview = null" /><button type="button" @click="checkCode">核对</button></div></label><div v-if="preview" class="account-invite-preview"><strong>{{ preview.course_title || preview.label }}</strong><small>{{ [preview.semester, preview.teacher].filter(Boolean).join(' · ') }}</small><span>{{ preview.approval_required ? '需教师审核' : '确认后加入课程' }}</span></div><button class="account-primary" type="submit">确认加入课程</button></fieldset></form><div v-for="item in profile.course_requests" :key="item.id" class="account-invite-preview"><strong>{{ item.course_title }}</strong><span>{{ accountStateLabel(item.status) }}</span><small v-if="item.reason">{{ item.reason }}</small></div></section>
      <section><h3>修改密码</h3><p class="account-muted">修改后会退出所有设备。请先保存其他页面尚未提交的内容。</p><form class="account-form" @submit.prevent="password"><fieldset :disabled="busy"><label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" required maxlength="200" /></label><label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" required minlength="15" maxlength="200" placeholder="至少15个字符，可用容易记住的长句" /></label><label>再次确认新密码<input v-model="confirm" type="password" autocomplete="new-password" required minlength="15" maxlength="200" /></label><div v-if="challenge" class="account-challenge"><img :src="challenge.image" alt="图形验证码" /><button type="button" @click="refreshChallenge">换一张</button><label>验证码<input v-model="challengeAnswer" required maxlength="5" /></label></div><label class="account-check"><input v-model="confirmed" required type="checkbox" />我已保存其他内容，确认修改后重新登录</label><button class="account-primary" :disabled="!confirmed" type="submit">修改密码并重新登录</button></fieldset></form></section>
      <section v-if="user.role === 'student'"><h3>教师身份申请</h3><p v-if="profile.teacher_application" class="account-muted">{{ accountStateLabel(profile.teacher_application.status) }} · {{ profile.teacher_application.review_reason || '申请处理结果将在这里显示。' }}</p><form v-if="!profile.teacher_application || profile.teacher_application.status === 'rejected'" class="account-form" @submit.prevent="apply"><fieldset :disabled="busy"><label>任教与身份核实说明<textarea v-model="teacherReason" required minlength="8" maxlength="500" rows="3" placeholder="填写任教信息及可核实的联系方式" /></label><button type="submit">提交教师申请</button></fieldset></form><p class="account-muted">审核前不改变当前权限；学生课程与教师身份不能混用，请先与管理员核实。</p></section>
    </div>
    <SessionManager :base="base" :token="token" @signout="emit('signout')" />
    <ProjectLicense />
    <DetailDialog v-if="leaving" title="离开个人中心？" size="small" @close="leaving = false">
      <p v-if="avatarDirty" class="account-muted">头像裁剪尚未保存。离开后需要重新选择图片；其他尚未提交的填写内容也不会保存。</p>
      <p v-else class="account-muted">还有未提交的填写内容。密码不会保存在浏览器中，离开后需要重新输入。</p>
      <template #footer><button type="button" @click="leaving = false">继续填写</button><button type="button" @click="emit('close')">放弃填写并关闭</button></template>
    </DetailDialog>
  </DetailDialog>
</template>

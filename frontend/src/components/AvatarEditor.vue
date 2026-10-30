<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import { AccountError } from '../accountAccess'
import { cropRectangle, loadAvatarFile, readAvatar, writeAvatar } from '../avatars'
import type { AvatarState } from '../avatars'

const props = defineProps<{ base: string; token: string; avatar: AvatarState; disabled?: boolean }>()
const emit = defineEmits<{ updated: [value: AvatarState]; busy: [value: boolean]; dirty: [value: boolean] }>()
const fileInput = ref<HTMLInputElement | null>(null), canvas = ref<HTMLCanvasElement | null>(null)
const source = shallowRef<HTMLImageElement | null>(null)
const zoom = ref(1), horizontal = ref(50), vertical = ref(50), busy = ref(false)
const loaded = ref(false)
const error = ref(''), notice = ref(''), requiresRead = ref(false), confirmReset = ref(false)
const expected = ref<string | null>(props.avatar.revision), resetExpected = ref<string | null>(null)
const disabled = computed(() => busy.value || props.disabled || !loaded.value)
const changedElsewhere = computed(() => !!source.value && expected.value !== props.avatar.revision)
let generation = 0, alive = true
let drag: { pointer: number; x: number; y: number; horizontal: number; vertical: number } | null = null
watch(busy, value => emit('busy', value), { flush: 'sync' })
watch(source, value => emit('dirty', !!value), { flush: 'sync' })

function resetPosition() { zoom.value = 1; horizontal.value = 50; vertical.value = 50 }
function cancel() { generation += 1; source.value = null; resetPosition(); error.value = ''; notice.value = ''; if (fileInput.value) fileInput.value.value = '' }
function paint() {
  if (!source.value || !canvas.value) return
  const context = canvas.value.getContext('2d')
  if (!context) { error.value = '浏览器无法预览图片，请尝试更新浏览器。'; return }
  const rectangle = cropRectangle(source.value.naturalWidth, source.value.naturalHeight, zoom.value, horizontal.value, vertical.value)
  context.fillStyle = '#fff'; context.fillRect(0, 0, 256, 256)
  context.imageSmoothingEnabled = true; context.imageSmoothingQuality = 'high'
  context.drawImage(source.value, rectangle.x, rectangle.y, rectangle.side, rectangle.side, 0, 0, 256, 256)
}
watch([source, zoom, horizontal, vertical], async () => { await nextTick(); paint() })
async function choose(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  input.value = ''; if (!file || disabled.value) return
  const current = ++generation
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const image = await loadAvatarFile(file)
    if (alive && current === generation) { expected.value = props.avatar.revision; requiresRead.value = false; resetPosition(); source.value = image }
  } catch (e) { if (alive) error.value = (e as Error).message }
  finally { if (alive) busy.value = false }
}
function startDrag(event: PointerEvent) {
  if (disabled.value || !canvas.value || event.button !== 0) return
  drag = { pointer: event.pointerId, x: event.clientX, y: event.clientY, horizontal: horizontal.value, vertical: vertical.value }
  canvas.value.setPointerCapture(event.pointerId)
}
function moveDrag(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointer || !source.value || !canvas.value || disabled.value) return
  const side = Math.min(source.value.naturalWidth, source.value.naturalHeight) / zoom.value
  const scale = side / canvas.value.getBoundingClientRect().width
  const dx = source.value.naturalWidth - side, dy = source.value.naturalHeight - side
  if (dx > 0) horizontal.value = Math.max(0, Math.min(100, drag.horizontal - (event.clientX - drag.x) * scale / dx * 100))
  if (dy > 0) vertical.value = Math.max(0, Math.min(100, drag.vertical - (event.clientY - drag.y) * scale / dy * 100))
}
async function reread(silent = false) {
  if (busy.value || props.disabled) return
  busy.value = true; error.value = ''
  try {
    const value = await readAvatar(props.base, props.token)
    if (!alive) return
    expected.value = value.revision; emit('updated', value); requiresRead.value = false; loaded.value = true
    if (!silent) notice.value = source.value ? '已读取当前头像。请核对预览，再决定是否保存这次裁剪。' : '已重新读取当前头像。'
  } catch (e) { if (alive) { error.value = (e as Error).message; requiresRead.value = true } }
  finally { if (alive) busy.value = false }
}
async function save(reset = false) {
  if (disabled.value || (!reset && (!source.value || requiresRead.value || changedElsewhere.value || !canvas.value))) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    paint()
    const image = reset ? null : canvas.value!.toDataURL('image/jpeg', 0.9)
    const result = await writeAvatar(props.base, props.token, image, reset ? resetExpected.value : expected.value)
    if (!alive) return
    cancel(); confirmReset.value = false; requiresRead.value = false; expected.value = result.revision
    emit('updated', result); notice.value = reset ? '已恢复默认头像。' : '头像已保存。'
  } catch (e) {
    if (alive) {
      error.value = (e as Error).message
      if (e instanceof AccountError && (e.status === 409 || e.status === 0)) { requiresRead.value = true; confirmReset.value = false }
    }
  } finally { if (alive) busy.value = false }
}
function askReset() { resetExpected.value = props.avatar.revision; confirmReset.value = true }
onMounted(() => { void reread(true) })
onUnmounted(() => { alive = false; generation += 1; source.value = null; drag = null })
</script>

<template>
  <section class="avatar-editor" :aria-busy="busy" aria-label="头像设置">
    <div class="avatar-editor-heading"><div><h3>我的头像</h3><p>让课程空间更有你的样子</p></div><div class="avatar-editor-actions"><button type="button" :disabled="disabled" @click="fileInput?.click()">{{ source ? '重新选图' : '更换头像' }}</button><button v-if="avatar.image && !source" type="button" :disabled="disabled" @click="askReset">恢复默认</button></div></div>
    <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" aria-label="选择头像图片" hidden :disabled="disabled" @change="choose" />
    <p class="avatar-file-hint">JPG、PNG、WebP · 最大 5 MB</p>
    <p v-if="busy" class="avatar-progress" role="status"><span class="ui-spinner" aria-hidden="true" />正在处理头像，请稍候…</p>
    <div v-if="source" class="avatar-crop-layout">
      <div class="avatar-crop-preview"><canvas ref="canvas" width="256" height="256" role="img" aria-label="头像裁剪预览，可拖动调整位置" @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="drag = null" @pointercancel="drag = null" @lostpointercapture="drag = null" /><p>拖动图片调整位置</p></div>
      <div class="avatar-crop-controls"><label for="avatar-zoom">缩放 <output>{{ Math.round(zoom * 100) }}%</output></label><input id="avatar-zoom" v-model.number="zoom" type="range" min="1" max="3" step="0.01" aria-label="头像缩放" :disabled="disabled" />
        <details><summary>精细调整位置</summary><label for="avatar-horizontal">水平位置</label><input id="avatar-horizontal" v-model.number="horizontal" type="range" min="0" max="100" step="1" aria-label="头像水平位置" :disabled="disabled" /><label for="avatar-vertical">垂直位置</label><input id="avatar-vertical" v-model.number="vertical" type="range" min="0" max="100" step="1" aria-label="头像垂直位置" :disabled="disabled" /></details>
        <button class="avatar-position-reset" type="button" :disabled="disabled" @click="resetPosition">重置裁剪</button>
        <div class="avatar-crop-buttons"><button class="account-primary" type="button" :disabled="disabled || requiresRead || changedElsewhere" @click="save()">保存头像</button><button type="button" :disabled="disabled" @click="cancel">取消裁剪</button></div>
      </div>
    </div>
    <p v-if="changedElsewhere" class="account-notice" role="status">当前头像有更新。先重新读取核对，本次裁剪会保留。</p>
    <p v-if="error" class="account-error" role="alert">{{ error }}</p><p v-if="notice" class="account-notice" role="status">{{ notice }}</p>
    <button v-if="requiresRead || changedElsewhere" type="button" :disabled="busy || props.disabled" @click="reread()">重新读取当前头像</button>
    <DetailDialog v-if="confirmReset" title="恢复默认头像？" size="small" :close-disabled="busy" @close="confirmReset = false"><p>将改用姓名默认头像。之后仍可重新上传图片。</p><template #footer><button type="button" :disabled="busy" @click="confirmReset = false">保留当前头像</button><button class="account-primary" type="button" :disabled="busy" @click="save(true)">确认恢复默认</button></template></DetailDialog>
  </section>
</template>

<style scoped>
.avatar-editor { border: 1px solid #dfe7f3; border-radius: 15px; margin: 0 0 22px; min-width: 0; padding: 18px; }
.avatar-editor-heading { align-items: center; display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; }
.avatar-editor-heading h3 { color: #324b6e; font-size: 15px; margin: 0 0 6px; }
.avatar-editor-heading p, .avatar-file-hint, .avatar-crop-preview p { color: #8392a8; font-size: 12px; line-height: 1.7; margin: 0; }
.avatar-editor-actions, .avatar-crop-buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.avatar-editor button { min-height: 44px; }
.avatar-editor-actions button { background: #edf3ff; border: 1px solid #dae5f7; color: #3e61a0; font-size: 12px; }
.avatar-file-hint { margin-top: 10px; }
.avatar-progress { align-items: center; color: #5b79a5; display: flex; font-size: 13px; gap: 8px; }
.avatar-crop-layout { align-items: center; background: #f7f9fd; border-radius: 13px; display: grid; gap: 24px; grid-template-columns: minmax(0, 256px) minmax(0, 1fr); margin-top: 18px; padding: 20px; }
.avatar-crop-preview { min-width: 0; text-align: center; }
.avatar-crop-preview canvas { aspect-ratio: 1; background: #fff; border: 3px solid #fff; border-radius: 50%; box-shadow: 0 5px 20px #40578218; box-sizing: border-box; cursor: grab; display: block; height: auto; margin: auto; max-width: 256px; touch-action: none; width: 100%; }
.avatar-crop-preview canvas:active { cursor: grabbing; }
.avatar-crop-preview p { margin-top: 10px; }
.avatar-crop-controls { display: grid; gap: 14px; min-width: 0; }
.avatar-crop-controls label { align-items: center; color: #516b90; display: flex; font-size: 12px; justify-content: space-between; }
.avatar-crop-controls input[type=range] { accent-color: #526be3; background: transparent; border: 0; box-shadow: none; cursor: pointer; height: 32px; min-height: 32px; padding: 0; width: 100%; }
.avatar-crop-controls summary { color: #6c82a2; cursor: pointer; font-size: 12px; padding: 8px 0; }
.avatar-crop-controls details label { margin-top: 9px; }
.avatar-position-reset { background: transparent; color: #697f9e; font-size: 12px; justify-self: start; padding: 6px 0; }
.avatar-crop-buttons button:not(.account-primary) { background: white; border: 1px solid #d9e3f3; color: #617b9e; }
.avatar-editor :is(button,input,summary):focus-visible { outline: 3px solid #adcaef; outline-offset: 3px; }
@media(max-width:600px) { .avatar-editor { padding: 14px; }.avatar-crop-layout { gap: 15px; grid-template-columns: minmax(0,1fr); padding: 14px; }.avatar-crop-preview canvas { max-width: 200px; }.avatar-crop-buttons { display: grid; grid-template-columns: 1fr 1fr; }.avatar-editor-heading { align-items: start; }.avatar-editor-heading h3 { font-size: 14px; } }
</style>

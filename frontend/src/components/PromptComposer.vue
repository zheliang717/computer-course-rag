<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, useId, watch } from 'vue'

const model = defineModel<string>({ required: true })
const props = withDefaults(defineProps<{
  label: string
  placeholder: string
  sendDisabled?: boolean
  submitLabel?: string
  canStop?: boolean
}>(), { sendDisabled: false, submitLabel: '发送 ↗', canStop: false })
const emit = defineEmits<{ submit: []; stop: [] }>()
const editor = ref<HTMLTextAreaElement | null>(null)
const composing = ref(false)
const hintId = `prompt-hint-${useId()}`
const lines = computed(() => model.value.split('\n').length)

function resize() {
  const element = editor.value
  if (!element) return
  element.style.height = 'auto'
  const style = getComputedStyle(element)
  const min = parseFloat(style.minHeight) || 48
  const max = parseFloat(style.maxHeight) || 180
  element.style.height = `${Math.min(max, Math.max(min, element.scrollHeight + 2))}px`
}
watch(model, async () => { await nextTick(); resize() }, { flush: 'post' })
onMounted(() => { resize(); window.addEventListener('resize', resize); window.visualViewport?.addEventListener('resize', resize) })
onUnmounted(() => { window.removeEventListener('resize', resize); window.visualViewport?.removeEventListener('resize', resize) })

function submit() {
  if (!composing.value && !props.sendDisabled && model.value.trim()) emit('submit')
}
function keydown(event: KeyboardEvent) {
  // Enter confirms a Chinese/Japanese IME candidate before it means "send".
  // Do not prevent its default action or submit a half-composed prompt.
  if (event.key !== 'Enter' || event.isComposing || composing.value || event.keyCode === 229) return
  if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return
  if (window.matchMedia('(max-width: 920px)').matches) return
  event.preventDefault()
  submit()
}
</script>

<template>
  <section class="prompt-composer" :aria-busy="canStop">
    <textarea ref="editor" v-model="model" rows="1" enterkeyhint="enter" :aria-label="label" :aria-describedby="hintId"
      :placeholder="placeholder" @keydown="keydown" @input="resize"
      @compositionstart="composing = true" @compositionend="composing = false" />
    <div class="prompt-composer-footer">
      <div :id="hintId" class="prompt-composer-hint"><span class="desktop-input-hint">Enter 发送 · Shift + Enter 换行</span><span class="mobile-input-hint">可换行编辑 · 点击发送</span><small v-if="model.length">{{ lines > 1 ? `${lines} 行 · ` : '' }}{{ model.length }} 字符</small></div>
      <div class="prompt-composer-actions"><button v-if="canStop" type="button" class="stream-stop-button" @click="emit('stop')">停止生成</button><button type="button" :aria-busy="canStop" :disabled="sendDisabled || !model.trim() || composing" @click="submit"><span v-if="canStop" class="ui-spinner" aria-hidden="true" />{{ submitLabel }}</button></div>
    </div>
  </section>
</template>

<style scoped>
.prompt-composer { display: grid; gap: 10px; min-width: 0; width: 100%; }
.prompt-composer textarea { background: #f8faff; border: 1px solid #d5e1f1; border-radius: 13px; box-sizing: border-box; color: #253b58; display: block; font: inherit; font-size: 13px; line-height: 1.65; max-height: min(200px, 30dvh); min-height: 66px; min-width: 0; outline: none; overflow-y: auto; padding: 13px 14px; resize: none; scrollbar-gutter: stable; white-space: pre-wrap; width: 100%; }
.prompt-composer textarea:focus { background: #fff; border-color: #7298dc; box-shadow: 0 0 0 3px #6791d921; }
.prompt-composer textarea::placeholder { color: #8b9bb1; }
.prompt-composer-footer { align-items: center; display: flex; flex-wrap: wrap; gap: 8px 14px; justify-content: space-between; min-width: 0; }
.prompt-composer-hint { color: #8292a9; display: grid; font-size: 10px; gap: 3px; line-height: 1.5; }
.prompt-composer-hint small { color: #6f83a0; font-size: 10px; }
.mobile-input-hint { display: none; }
.prompt-composer-actions { align-items: center; display: flex; flex: none; flex-wrap: wrap; gap: 8px; margin-inline-start: auto; }
.prompt-composer-actions button { border-radius: 10px; font-size: 12px; min-height: 38px; padding: 9px 16px; }
.prompt-composer :is(textarea,button):focus-visible { outline: 3px solid #a5c1ee; outline-offset: 3px; }
@media (max-width: 520px) { .prompt-composer { gap: 8px; } .prompt-composer textarea { font-size: 14px; padding: 11px 12px; } .prompt-composer-hint { font-size: 9px; } .prompt-composer-actions button { padding: 8px 12px; } }
@media (max-width: 920px) {
  .prompt-composer { gap: 6px; }
  .prompt-composer textarea { font-size: 16px; min-height: 46px; max-height: min(140px, 24dvh); padding: 9px 11px; }
  .desktop-input-hint { display: none; }
  .mobile-input-hint { display: inline; }
  .prompt-composer-actions button { min-height: 40px; }
}
</style>

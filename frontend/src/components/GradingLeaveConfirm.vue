<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useDialogFocus } from '../useDialogFocus'
defineProps<{ studentName: string; actionLabel: string }>()
const emit = defineEmits<{ cancel: []; discard: []; stash: [] }>()
const dialog = ref<HTMLElement | null>(null)
const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
useDialogFocus(dialog, () => emit('cancel'), () => true)
onBeforeUnmount(() => { if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true }) })
</script>
<template>
  <div class="grading-leave-overlay" @click.self="emit('cancel')"><section ref="dialog" class="grading-leave-dialog" role="alertdialog" aria-modal="true" aria-labelledby="grading-leave-title" aria-describedby="grading-leave-description" tabindex="-1"><h3 id="grading-leave-title">批改内容尚未保存</h3><p id="grading-leave-description">{{ studentName }}的成绩或评语有未保存修改。{{ actionLabel }}前，请选择如何处理。暂存只保存在当前浏览器，不会提交成绩。</p><footer><button type="button" @click="emit('cancel')">返回继续批改</button><button type="button" @click="emit('stash')">暂存草稿并继续</button><button type="button" class="danger-soft" @click="emit('discard')">放弃修改并继续</button></footer></section></div>
</template>
<style scoped>
.grading-leave-overlay { align-items: center; background: #17203380; display: flex; inset: 0; justify-content: center; padding: 20px; position: fixed; z-index: 160; }.grading-leave-dialog { background: white; border-radius: 18px; box-shadow: 0 24px 80px #17203340; max-width: 480px; padding: 26px; width: 100%; }.grading-leave-dialog h3 { color: #253c59; font-size: 20px; margin: 0 0 14px; }.grading-leave-dialog p { color: #5b6d86; font-size: 14px; line-height: 1.9; }.grading-leave-dialog footer { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }.grading-leave-dialog button { font-size: 13px; }button:focus-visible { outline: 3px solid #b8a3e3; outline-offset: 3px; }
</style>

<script setup lang="ts">
import { defineAsyncComponent, onUnmounted, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import releaseMarkdown from '../../../docs/changelog/2026-10-29.md?raw'

const RichText = defineAsyncComponent(() => import('./RichText.vue'))
const props = defineProps<{ owner: string; active: boolean; ready: boolean }>()
const releaseId = '2026-10-29-zhixue-assistant'
const storageKey = `rag_update_notice:${props.owner}`
const open = ref(false)
const seen = ref(false)
try { seen.value = localStorage.getItem(storageKey) === releaseId } catch { /* Session-only acknowledgement if storage is unavailable. */ }
const content = releaseMarkdown.replace(/^# [^\n]+\n/, '')
const downloadUrl = URL.createObjectURL(new Blob([releaseMarkdown], { type: 'text/markdown;charset=utf-8' }))

function show() {
  open.value = true
  seen.value = true
  try { localStorage.setItem(storageKey, releaseId) } catch { /* Keep the in-memory acknowledgement. */ }
}
watch(() => [props.active, props.ready], () => {
  if (!props.active) { open.value = false; return }
  if (!props.ready || seen.value || document.querySelector('dialog[open], .assignment-modal, .answer-reader-backdrop, #global-ai-assistant')) return
  show()
}, { immediate: true, flush: 'post' })
onUnmounted(() => URL.revokeObjectURL(downloadUrl))
</script>

<template>
  <button v-if="active" type="button" class="platform-update-entry" @click="show">
    <span class="update-entry-icon" aria-hidden="true">✦</span>
    <span><small>更新公告 · 10月29日<span v-if="!seen" class="update-unread">新</span></small><strong>资料与账号体验升级</strong><span>资料版本 · 数据导出 · 登录设备</span></span>
    <b>查看更新 ›</b>
  </button>
  <DetailDialog v-if="open" title="智学助手更新公告" kicker="2026.10.29" close-label="关闭更新公告" @close="open = false">
    <div class="platform-update-content"><RichText :source="content" :tools="false" /></div>
    <template #footer><a class="update-download" :href="downloadUrl" download="智学助手_更新日志_2026-10-29.md">下载更新日志</a><button type="button" class="update-acknowledge" @click="open = false">知道了</button></template>
  </DetailDialog>
</template>

<style scoped>
.platform-update-entry{align-items:center;background:linear-gradient(110deg,#f0f5ff,#fff);border:1px solid #dce6f5;border-radius:14px;box-shadow:0 3px 10px #284d7a04;color:#2d4b75;display:flex;gap:12px;margin:4px 0 18px;min-height:74px;padding:14px 18px;text-align:left;width:100%}
.update-entry-icon{align-items:center;background:#e5edff;border-radius:10px;color:#5a69c9;display:flex;flex:none;font-size:22px;height:38px;justify-content:center;width:38px}
.platform-update-entry>span:nth-child(2){display:grid;flex:1;gap:4px;min-width:0}
.platform-update-entry small{color:#7a8ba5;font-size:10px}.platform-update-entry strong{font-size:14px}.platform-update-entry>span>span{color:#7890ad;font-size:11px;line-height:1.6}
.platform-update-entry>b{flex:none;font-size:11px;white-space:nowrap}.update-unread{background:#e8edff;border-radius:4px;color:#566bc5;font-size:10px;margin-left:6px;padding:1px 4px}
.platform-update-entry:focus-visible,.update-download:focus-visible{outline:3px solid #a5c6ef;outline-offset:3px}
.platform-update-content{margin:auto;max-width:860px}.platform-update-content :deep(.answer-markdown){font-size:14px;line-height:1.9}.platform-update-content :deep(h2){border-bottom:1px solid #e2eaf5;color:#244671;padding-bottom:9px}.platform-update-content :deep(h3){color:#3b5b86;margin-top:23px}
.update-download{color:#4875ad;font-size:12px;text-decoration:none}.update-acknowledge{font-size:12px;padding:10px 18px}
@media(max-width:600px){.platform-update-entry{gap:9px;margin-bottom:14px;padding:12px}.update-entry-icon{font-size:18px;height:32px;width:32px}.platform-update-entry strong{font-size:13px}.platform-update-entry>b{font-size:10px}.platform-update-entry>span>span{font-size:10px}.platform-update-content :deep(.answer-markdown){font-size:13px}}
</style>

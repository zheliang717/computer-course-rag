<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import { useViewMemory } from '../viewMemory'
type Page = { page_number: number; chapter: string | null; content: string; chunks: Array<{ id: string; position: number; content: string }> }
const props = defineProps<{ content: { document: { id: string; name: string; version_label: string }; pages: Page[] }; initialPage: number | null; busy: boolean; returnLabel: string }>()
const emit = defineEmits<{ close: []; selection: [page: number, event: MouseEvent] }>()
const memory = useViewMemory(), owner = memory?.owner()
const key = JSON.stringify([owner, 'document-reading', props.content.document.id])
type Reading = { page: number; scroll: Record<number, number> }
const remembered = memory?.values.get(key) as Reading | undefined
const positions: Record<number, number> = { ...remembered?.scroll }
const pages = computed(() => [...props.content.pages].sort((a, b) => a.page_number - b.page_number))
const pageNumber = ref(props.initialPage ?? remembered?.page ?? pages.value[0]?.page_number ?? 1)
const index = computed(() => pages.value.findIndex(item => item.page_number === pageNumber.value))
const current = computed(() => pages.value[index.value] || null)
const jump = ref(pageNumber.value), message = ref('')
const view = ref<'reading' | 'information'>('reading')
const frame = ref<InstanceType<typeof DetailDialog> | null>(null)
let restoring = false
function remember() { if (memory && owner === memory.owner()) memory.values.set(key, { page: pageNumber.value, scroll: { ...positions } }) }
async function go(number: number) {
  if (!pages.value.some(item => item.page_number === number)) { message.value = '未载入这一页，请从可用页码中选择。'; return }
  const top = positions[number] || 0
  restoring = true
  pageNumber.value = number; jump.value = number; message.value = ''; view.value = 'reading'; remember()
  await nextTick(); frame.value?.scrollTo(top)
  window.requestAnimationFrame(() => { restoring = false })
}
watch(() => props.initialPage, number => { if (number !== null) void go(number) })
watch(view, async value => { if (value === 'reading') { const top = positions[pageNumber.value] || 0; restoring = true; await nextTick(); frame.value?.scrollTo(top); window.requestAnimationFrame(() => { restoring = false }) } })
function track(top: number) { if (view.value === 'reading' && !restoring) { positions[pageNumber.value] = top; remember() } }
onBeforeUnmount(remember)
</script>

<template>
  <DetailDialog ref="frame" :title="content.document.name" :description="`版本 ${content.document.version_label} · 已载入 ${pages.length} 页`" kicker="COURSE READER" close-label="关闭资料预览" :close-disabled="busy" :initial-scroll-top="positions[pageNumber] || 0" :view-key="view" @scroll="track" @close="emit('close')">
    <template #navigation><div class="document-view-nav"><div role="group" aria-label="资料视图"><button type="button" :aria-pressed="view === 'reading'" @click="view = 'reading'">原文阅读</button><button type="button" :aria-pressed="view === 'information'" @click="view = 'information'">资料信息</button></div><form @submit.prevent="go(jump)"><label>第<input v-model.number="jump" type="number" min="1" :aria-label="'资料跳转页码'" />页</label><button type="submit">跳转</button></form></div></template>
    <section v-show="view === 'information'" class="document-information"><slot name="information" /></section>
    <section v-show="view === 'reading'">
      <p v-if="message" class="document-read-message" role="alert">{{ message }}</p>
      <slot name="notice" />
      <article v-if="current" :key="current.page_number" class="document-reading-page" :data-document-page="current.page_number"><header><span>第 {{ current.page_number }} 页</span><h3>{{ current.chapter || '正文' }}</h3></header><pre @mouseup="emit('selection', current.page_number, $event)">{{ current.content }}</pre><details><summary>查看本页检索文本块</summary><div v-for="chunk in current.chunks" :key="chunk.id" class="chunk-preview"><b>#{{ chunk.position + 1 }}</b><p>{{ chunk.content }}</p></div></details></article>
      <p v-else class="document-read-message">这一页未载入，请用页码选择已载入的内容。</p>
    </section>
    <template #footer><div class="document-reader-pages"><button type="button" :disabled="index <= 0 || busy" @click="go(pages[index - 1]!.page_number)">上一页</button><span>{{ Math.max(0, index + 1) }} / {{ pages.length }}</span><button type="button" :disabled="index < 0 || index >= pages.length - 1 || busy" @click="go(pages[index + 1]!.page_number)">下一页</button></div><button type="button" class="text-button" :disabled="busy" @click="emit('close')">{{ returnLabel }}</button><slot name="actions" /></template>
  </DetailDialog>
</template>

<style scoped>
.document-view-nav { align-items: center; background: #f8fafd; border-bottom: 1px solid #e5edf5; display: flex; flex: none; flex-wrap: wrap; gap: 10px; justify-content: space-between; padding: 9px 24px; }.document-view-nav > div { display: flex; gap: 5px; }.document-view-nav button { background: transparent; color: #6b83a0; font-size: 12px; padding: 9px 12px; }.document-view-nav button[aria-pressed=true] { background: #fff; box-shadow: 0 2px 5px #263f5c0d; color: #356caa; }.document-view-nav form { align-items: center; display: flex; gap: 6px; }.document-view-nav label { align-items: center; color: #8293a9; display: flex; font-size: 11px; gap: 6px; }.document-view-nav input { font-size: 12px; min-height: 32px; padding: 5px 7px; width: 66px; }.document-reading-page { background: #fff; color: #344d68; margin: 0 auto; max-width: 850px; }.document-reading-page header { align-items: center; border-bottom: 1px solid #edf1f7; display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 22px; padding-bottom: 16px; }.document-reading-page header span { color: #8296b0; font-size: 11px; }.document-reading-page h3 { color: #365475; font-size: 15px; margin: 0; }.document-reading-page pre { font-family: inherit; font-size: 15px; line-height: 2; overflow-wrap: anywhere; white-space: pre-wrap; word-break: break-word; }.document-reading-page details { border-top: 1px solid #e6edf5; color: #7e94ad; font-size: 12px; margin-top: 28px; padding-top: 18px; }.document-reading-page summary { cursor: pointer; }.document-reader-pages { align-items: center; display: flex; gap: 10px; }.document-reader-pages button { background: #edf3fb; color: #567ba6; font-size: 12px; padding: 8px 11px; }.document-reader-pages span { color: #7e93ad; font-size: 12px; }.document-read-message { background: #fff6e7; border-radius: 10px; color: #92734d; font-size: 12px; padding: 12px; }
@media(max-width:600px) { .document-view-nav { padding: 9px 12px; }.document-view-nav button { font-size: 11px; padding: 7px 8px; }.document-reading-page pre { font-size: 14px; line-height: 1.95; } }
</style>

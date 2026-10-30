<script setup lang="ts" generic="T">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useViewMemory } from '../viewMemory'

type Result = { items: T[]; total: number; page: number; page_size: number }
const props = withDefaults(defineProps<{
  items: T[]; pageSize?: number; scope?: string; label?: string; stateKey?: string
  loadPage?: (page: number, pageSize: number) => Promise<Result>
}>(), { pageSize: 10, scope: '', label: '记录' })
const memory = useViewMemory()
const owner = memory?.owner(), workspace = memory?.page()
const memoryKey = () => JSON.stringify([owner, workspace, props.stateKey || props.label, props.scope])
type Remembered = { page: number; size: number; remote: Result | null }
const remembered = memory?.values.get(memoryKey()) as Remembered | undefined
const page = ref(remembered?.page || 1)
const size = ref(remembered?.size || props.pageSize)
const remote = shallowRef<Result | null>(remembered?.remote || null)
const loading = ref(false)
const error = ref('')
const jump = ref(page.value)
const retryPage = ref(page.value)
let generation = 0
function remember() {
  if (!memory || owner !== memory.owner()) return
  if (memory.values.size > 200) memory.values.delete(memory.values.keys().next().value!)
  memory.values.set(memoryKey(), { page: page.value, size: size.value, remote: remote.value })
}
const total = computed(() => props.loadPage ? remote.value?.total ?? 0 : props.items.length)
const pages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))
const shown = computed(() => props.loadPage ? remote.value?.items ?? [] : props.items.slice((page.value - 1) * size.value, page.value * size.value))
const sizes = computed(() => [...new Set([5, props.pageSize, 10, 20, 50])].sort((a, b) => a - b))

async function go(target: number): Promise<void> {
  const next = Math.max(1, Math.trunc(target) || 1)
  if (!props.loadPage) { page.value = Math.min(next, pages.value); jump.value = page.value; remember(); return }
  const current = ++generation
  retryPage.value = next
  loading.value = true
  error.value = ''
  try {
    const result = await props.loadPage(next, size.value)
    if (current !== generation) return
    const lastPage = Math.max(1, Math.ceil(result.total / size.value))
    if (next > lastPage) { await go(lastPage); return }
    remote.value = result
    page.value = result.page
    jump.value = result.page
    remember()
  } catch (cause) {
    if (current === generation) error.value = cause instanceof Error ? cause.message : '列表加载失败，请重试。'
  } finally { if (current === generation) loading.value = false }
}

watch(() => props.items, () => { void go(props.loadPage ? retryPage.value : page.value) })
watch(() => props.scope, () => { remote.value = null; page.value = 1; void go(1) })
watch(size, () => { void go(1) })
onMounted(() => { if (props.loadPage) void go(page.value); else void go(page.value) })
onUnmounted(() => { remember(); generation += 1 })
defineExpose({ showLastPage: () => go(pages.value), showItem: (index: number) => go(Math.floor(index/size.value)+1) })
</script>

<template>
  <div class="paged-list" :aria-busy="loading">
    <slot name="header" :total="total" />
    <p v-if="loading" class="pagination-loading" role="status"><span class="pagination-spinner" />正在加载…</p>
    <p v-if="error" class="pagination-error" role="alert">{{ error }} <button type="button" @click="go(retryPage)">重试</button></p>
    <slot :items="shown" :total="total" :page="page" :page-size="size" :loading="loading" :error="error" />
    <nav v-if="total > 0" class="list-pager" :aria-label="`${label}分页`">
      <span class="pager-summary" role="status">共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页</span>
      <label>每页<select v-model.number="size" :disabled="loading" :aria-label="`${label}每页条数`"><option v-for="value in sizes" :key="value" :value="value">{{ value }} 条</option></select></label>
      <div class="pager-step-buttons">
        <button type="button" :disabled="loading || page <= 1" @click="go(page - 1)">上一页</button>
        <button type="button" :disabled="loading || page >= pages" @click="go(page + 1)">下一页</button>
      </div>
      <form v-if="pages > 2" @submit.prevent="go(Math.min(jump, pages))"><input v-model.number="jump" type="number" min="1" :max="pages" :disabled="loading" :aria-label="`${label}跳转页码`" /><button :disabled="loading" type="submit">跳转</button></form>
    </nav>
  </div>
</template>

<style scoped>
.paged-list > .list-pager{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:10px;padding:14px 0 0;margin-top:12px;border-top:1px solid #e8edf5;min-width:0;max-width:100%}
.list-pager .pager-summary{margin-right:auto;line-height:1.6;white-space:normal}
.list-pager>label{flex:none;white-space:nowrap;margin:0;gap:6px;font-size:12px}
.list-pager .pager-step-buttons{display:flex;flex-wrap:nowrap;align-items:center;gap:6px;flex:none}
.list-pager .pager-step-buttons button{width:auto;min-height:40px;white-space:nowrap;margin:0}
.list-pager>form{display:flex;align-items:center;gap:6px;flex:none;margin:0}
.list-pager>form input{width:54px;max-width:54px;min-width:0}
.list-pager>label select{width:76px;min-width:0;max-width:76px;min-height:40px;padding:6px 24px 6px 8px}
@media(max-width:650px){
  .paged-list>.list-pager{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 6px;padding-inline-end:0}
  .list-pager .pager-summary{grid-column:1/-1;font-size:11px;margin:0}
  .list-pager>label{justify-self:start;font-size:11px;gap:4px}
  .list-pager .pager-step-buttons{justify-self:end;gap:4px}
  .list-pager .pager-step-buttons button{padding:8px;font-size:11px}
  .list-pager>form{grid-column:1/-1;justify-self:end}
  /* A jump input should not create a mostly empty third row on home cards. */
  .paged-list>.list-pager:has(>form){gap:8px 6px}
  .list-pager:has(>form) .pager-summary{grid-column:1;grid-row:1;align-self:center}
  .list-pager:has(>form)>label{grid-column:2;grid-row:1;justify-self:end}
  .list-pager:has(>form)>label select{width:64px;max-width:64px;padding-right:22px}
  .list-pager:has(>form) .pager-step-buttons{grid-column:1;grid-row:2;justify-self:start}
  .list-pager:has(>form)>form{grid-column:2;grid-row:2;gap:4px}
  .list-pager:has(>form)>form input{width:44px;max-width:44px;text-align:center;padding:6px 3px}
  .list-pager:has(>form)>form button{padding:8px;min-height:40px;font-size:11px;white-space:nowrap}
}
.list-pager input::-webkit-inner-spin-button,.list-pager input::-webkit-outer-spin-button{appearance:none;margin:0}
</style>

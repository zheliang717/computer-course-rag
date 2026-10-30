<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
type Reading = { id: string; document_id: string; document_name: string; first_page: number; last_page: number; note: string; position: number; revision: number }
const props = defineProps<{ sectionId: string; materials: { id: string; name: string; page_count: number | null }[]; manage: boolean; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
defineEmits<{ open: [id: string, page: number] }>()
const revision = ref(0), busy = ref(false), error = ref(''), editing = ref(false), editingId = ref('')
const form = ref({ document_id: '', first_page: 1, last_page: 1, note: '', position: 1, revision: 1 })
const rows: Reading[] = []
const selectedMaterial = computed(() => props.materials.find(m => m.id === form.value.document_id))
const loadPage = (page: number, size: number) => props.request(`/api/v1/sections/${props.sectionId}/readings?page=${page}&page_size=${size}`) as Promise<{ items: Reading[]; total: number; page: number; page_size: number }>
watch(() => props.sectionId, () => { editing.value = false; error.value = '' })
function edit(item?: Reading) {
  editingId.value = item?.id || ''
  form.value = item ? { document_id: item.document_id, first_page: item.first_page, last_page: item.last_page, note: item.note, position: item.position, revision: item.revision } : { document_id: props.materials[0]?.id || '', first_page: 1, last_page: 1, note: '', position: 1, revision: 1 }
  editing.value = true; error.value = ''
}
async function save() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    await props.request(`/api/v1/sections/${props.sectionId}/readings${editingId.value ? '/' + editingId.value : ''}`, { method: editingId.value ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form.value) })
    editing.value = false; revision.value++
  } catch (e) { error.value = e instanceof Error ? e.message : '阅读安排保存失败' }
  finally { busy.value = false }
}
async function remove(item: Reading) {
  if (busy.value || !window.confirm('移除这项阅读安排？不会删除资料原文。')) return
  busy.value = true; error.value = ''
  try { await props.request(`/api/v1/sections/${props.sectionId}/readings/${item.id}?revision=${item.revision}`, { method: 'DELETE' }); revision.value++ }
  catch (e) { error.value = e instanceof Error ? e.message : '移除失败' }
  finally { busy.value = false }
}
</script>
<template>
  <section class="chapter-readings">
    <header><h4>章节阅读</h4><button v-if="manage" type="button" @click="edit()">安排阅读 ＋</button></header>
    <p v-if="error" role="alert">{{ error }}</p>
    <form v-if="editing && manage" @submit.prevent="save">
      <label>课程资料<select v-model="form.document_id" required><option v-for="m in materials" :key="m.id" :value="m.id">{{ m.name }}</option></select></label>
      <div class="reading-range"><label>起始页<input v-model.number="form.first_page" type="number" min="1" :max="selectedMaterial?.page_count || undefined" required /></label><label>结束页<input v-model.number="form.last_page" type="number" :min="form.first_page" :max="selectedMaterial?.page_count || undefined" required /></label><label>顺序<input v-model.number="form.position" type="number" min="1" max="10000" required /></label></div>
      <label>阅读提示<input v-model="form.note" maxlength="500" placeholder="如：先理解算法边界，再推演例子" /></label>
      <div class="reading-actions"><button :disabled="busy || !form.document_id" type="submit">{{ busy ? '保存中…' : '保存安排' }}</button><button :disabled="busy" type="button" @click="editing = false">取消</button></div>
    </form>
    <PagedList :items="rows" :load-page="loadPage" :scope="sectionId + ':' + revision" :page-size="5" label="章节阅读" v-slot="{ items, loading, total }">
      <article v-for="item in items" :key="item.id">
        <button class="reading-open" type="button" @click="$emit('open', item.document_id, item.first_page)"><strong>{{ item.document_name }}</strong><span>第 {{ item.first_page }}{{ item.last_page !== item.first_page ? '—' + item.last_page : '' }} 页 ↗</span><small v-if="item.note">{{ item.note }}</small></button>
        <div v-if="manage" class="reading-actions"><button type="button" :disabled="busy" @click="edit(item)">编辑</button><button type="button" :disabled="busy" @click="remove(item)">移除</button></div>
      </article>
      <p v-if="!loading && !total">本章节暂无指定阅读。</p>
    </PagedList>
  </section>
</template>
<style scoped>
.chapter-readings { border-top:1px solid #e3eaf6; margin-top:16px; padding-top:12px; min-width:0; } header,.reading-actions {display:flex;align-items:center;gap:8px;flex-wrap:wrap} header {justify-content:space-between} h4{margin:0} button{font-size:12px} form{background:#f5f8fd;padding:12px;border-radius:12px;margin-block:12px;display:grid;gap:10px}.reading-range{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px} label{display:grid;gap:6px;font-size:12px;min-width:0} input,select{width:100%;min-width:0;font:inherit} article{display:flex;align-items:center;gap:8px;border-bottom:1px solid #e7edf6;padding-block:10px}.reading-open{flex:1;min-width:0;display:grid;gap:5px;text-align:left;background:transparent;color:#284d86;padding:4px;overflow-wrap:anywhere}.reading-open span,small{font-weight:400;font-size:12px;color:#71819b}p{font-size:12px;color:#73839b} [role=alert]{color:#a14437}@media(max-width:480px){article{align-items:stretch;flex-direction:column}.reading-actions{justify-content:flex-end}}
</style>

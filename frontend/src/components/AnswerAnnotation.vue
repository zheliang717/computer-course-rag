<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
import RichText from './RichText.vue'
const props = defineProps<{ historyId: string; answer: string; citationCount: number; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
type Annotation = { id: string; answer_quote: string; category: string; comment: string; created_at: string; review_status?:string; review_note?:string; revised_answer?:string }
const historyOpen = ref(false), revision = ref(0), occurrence = ref(0)
const occurrences = computed(() => { const positions: number[] = []; if (!quote.value) return positions; let start = 0; while (start < props.answer.length) { const index = props.answer.indexOf(quote.value, start); if (index < 0) break; positions.push(index); start = index + Math.max(1, quote.value.length) } return positions })
watch(() => quote.value, () => { occurrence.value = 0 })
const loadPage = (page: number, size: number) => props.request(`/api/v1/history/${props.historyId}/annotations?page=${page}&page_size=${size}`) as Promise<{ items: Annotation[]; total: number; page: number; page_size: number }>
const open = ref(false), quote = ref(''), category = ref('unclear'), comment = ref(''), source = ref(''), busy = ref(false), status = ref('')
const pieces = computed(() => props.answer.split(/\n\s*\n/).map(v => v.trim()).filter(v => v.length >= 2 && v.length <= 2000))
watch(() => props.historyId, () => { open.value = false; quote.value = ''; comment.value = ''; status.value = '' })
async function send() {
  if (busy.value || !quote.value) return
  busy.value = true; status.value = ''
  const start = occurrences.value[occurrence.value] ?? -1
  try {
    if (start < 0) throw new Error('请重新选择回答中的原文。')
    // JavaScript offsets are UTF-16; server anchors count Unicode code points.
    const start_offset = Array.from(props.answer.slice(0, start)).length
    await props.request(`/api/v1/history/${props.historyId}/annotations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answer_quote: quote.value, start_offset, end_offset: start_offset + Array.from(quote.value).length, category: category.value, comment: comment.value.trim(), source_index: source.value ? Number(source.value) : null }) })
    revision.value++; status.value = '已记录具体段落与问题，感谢反馈。'; open.value = false; comment.value = ''
  } catch (e) { status.value = e instanceof Error ? e.message : '反馈暂未保存，请重试' }
  finally { busy.value = false }
}
</script>
<template>
  <section class="answer-annotation"><button type="button" :aria-expanded="open" @click="open = !open">反馈具体内容</button><button type="button" :aria-expanded="historyOpen" @click="historyOpen=!historyOpen">{{ historyOpen ? '收起反馈' : '我的反馈' }}</button><p v-if="status" role="status">{{ status }}</p>
    <form v-if="open" @submit.prevent="send"><label>有疑问的原文<select v-model="quote" required><option disabled value="">选择回答段落</option><option v-for="(part, index) in pieces" :key="index" :value="part">{{ part.slice(0, 70) }}{{ part.length > 70 ? '…' : '' }}</option></select></label>
      <label>也可粘贴更准确的原句<textarea v-model="quote" minlength="2" maxlength="2000" required rows="3" /></label>
      <label v-if="occurrences.length>1">原句在回答中重复，请选择位置<select v-model.number="occurrence"><option v-for="(position,i) in occurrences" :key="position" :value="i">第 {{ i+1 }} 处 · {{ answer.slice(Math.max(0,position-15),position+20) }}</option></select></label><div class="annotation-options"><label>问题类型<select v-model="category"><option value="unclear">讲解不清楚</option><option value="factual">知识点有误</option><option value="calculation">推演或计算有误</option><option value="citation">引用不支持结论</option><option value="other">其他问题</option></select></label><label v-if="citationCount">对应资料<select v-model="source"><option value="">不指定</option><option v-for="n in citationCount" :key="n" :value="String(n)">资料 {{ n }}</option></select></label></div>
      <label>说明<textarea v-model="comment" required minlength="2" maxlength="2000" rows="2" placeholder="哪里有疑问？可补充你的推导或正确依据。" /></label><div class="annotation-actions"><button type="submit" :disabled="busy">{{ busy ? '正在保存…' : '提交反馈' }}</button><button type="button" :disabled="busy" @click="open = false">取消</button></div></form>
    <PagedList v-if="historyOpen" :items="[] as Annotation[]" :load-page="loadPage" :scope="historyId + revision" :page-size="3" label="内容反馈" v-slot="{items,total,loading}"><article v-for="item in items" :key="item.id"><blockquote>{{ item.answer_quote }}</blockquote><p>{{ item.comment }}</p><p>回答整体审核：{{ item.review_status==='approved'?'已通过':item.review_status==='rejected'?'需修订':'待教师核对' }}</p><blockquote v-if="item.review_note">教师意见：{{ item.review_note }}</blockquote><details v-if="item.revised_answer"><summary>查看教师修订答案</summary><RichText :source="item.revised_answer" :tools="false" /></details><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</small></article><p v-if="!loading&&!total">暂未提交具体内容反馈。</p></PagedList>
  </section>
</template>
<style scoped>
.answer-annotation>button+button{margin-left:8px}article{padding-block:10px;border-bottom:1px solid #e2e9f3}blockquote{margin:0;padding:8px;border-left:3px solid #abbbe7;white-space:pre-wrap;max-height:120px;overflow:auto}small{color:#8090a7}.answer-annotation{margin-block:10px;font-size:12px}button{font-size:12px}form{display:grid;gap:10px;margin-top:10px;padding:12px;background:#f6f8fd;border:1px solid #e0e7f2;border-radius:12px;min-width:0}label{display:grid;gap:6px;min-width:0}select,textarea{font:inherit;width:100%;min-width:0}p{color:#637b9e}.annotation-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.annotation-actions{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:360px){.annotation-options{grid-template-columns:1fr}}
</style>

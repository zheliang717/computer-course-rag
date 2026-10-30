<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import PagedList from './PagedList.vue'
import RichText from './RichText.vue'
type Content = { question_type: string; stem: string; options: string[]; correct_answer: string; explanation: string | null; difficulty: number; knowledge_point: string | null }
type Entry = { question_id: string | null; points: number; question: Content; content?: Content }
type State = { id: string; course_id: string; title: string; description: string | null; due_at: string | null; status: string; revision: number; ai_policy: string; previous_version_id: string | null; questions: Entry[]; signature?: string; max_score?: number }
type BankQuestion = Content & { id: string }
type Revision = { revision: number; reason: string; created_at: string; content: State }
const props = defineProps<{ assignmentId: string; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
const emit = defineEmits<{ close: []; saved: [id: string] }>()
const state = ref<State | null>(null), preview = ref<State | null>(null), busy = ref(false), dirty = ref(false), error = ref(''), message = ref(''), tab = ref('edit'), index = ref(0), picker = ref(false), search = ref(''), keyword = ref(''), confirmed = ref(false), reason = ref('调整作业草稿'), content = ref<Content | null>(null), options = ref('')
const creatingQuestion = ref(false)
const questionList=ref<{showItem:(index:number)=>Promise<void>}|null>(null)
function chooseQuestion(value:number){if(content.value&&!window.confirm('当前题目尚未应用，确认放弃这部分修改？'))return;content.value=null;index.value=value}
function revealQuestion(){void nextTick(()=>questionList.value?.showItem(index.value))}
const controller = new AbortController()
let sequence = 0
const current = computed(() => state.value?.questions[index.value]), editable = computed(() => state.value?.status === 'draft'), total = computed(() => state.value?.questions.reduce((n, q) => n + Number(q.points || 0), 0) || 0)
const labels: Record<string, string> = { single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题', fill_blank: '填空题', short_answer: '简答题' }
const bankRows: BankQuestion[] = [], revisionRows: Revision[] = []
watch(() => props.assignmentId, async () => {
  const seq = ++sequence; state.value = null; busy.value = true; error.value = ''; dirty.value = false; tab.value = 'edit'; preview.value = null
  try { const value = await props.request(`/api/v1/assignments/${props.assignmentId}/editor`, { signal: controller.signal }) as State; if (seq === sequence) state.value = value }
  catch (e) { if (seq === sequence) error.value = e instanceof Error ? e.message : '作业读取失败' }
  finally { if (seq === sequence) busy.value = false }
}, { immediate: true })
watch(content, value => { if (value) dirty.value = true }, { deep: true })
onBeforeUnmount(() => { sequence++; controller.abort() })
function close() { if (busy.value) return; if (dirty.value && !window.confirm('有尚未保存的作业修改，确认放弃并关闭？')) return; emit('close') }
function touch() { dirty.value = true; preview.value = null; confirmed.value = false }
function move(offset: number) { if (!state.value) return; const next = index.value + offset; if (next < 0 || next >= state.value.questions.length) return; const [row] = state.value.questions.splice(index.value, 1); state.value.questions.splice(next, 0, row!); index.value = next; touch(); revealQuestion() }
function remove() { if (!state.value || !current.value || !window.confirm('从这份草稿移除本题？题库原题和历史作答不会删除。')) return; state.value.questions.splice(index.value, 1); index.value = Math.max(0, Math.min(index.value, state.value.questions.length - 1)); content.value = null; touch(); revealQuestion() }
function add(q: BankQuestion) { if (!state.value || state.value.questions.some(r => r.question_id === q.id)) return; state.value.questions.push({ question_id: q.id, points: 10, question: q }); index.value = state.value.questions.length - 1; picker.value = false; content.value = null; touch(); revealQuestion() }
function editQuestion(fresh = false) { creatingQuestion.value = fresh; const q = fresh ? { question_type: 'short_answer', stem: '', options: [], correct_answer: '', explanation: '', difficulty: 2, knowledge_point: '' } : current.value?.content || current.value?.question; if (!q) return; content.value = { question_type: q.question_type, stem: q.stem, options: [...q.options], correct_answer: q.correct_answer || '', explanation: q.explanation, difficulty: q.difficulty, knowledge_point: q.knowledge_point }; options.value = q.options.join('\n') }
function applyContent() { if (!content.value || !state.value) return; const value = { ...content.value, options: options.value.split('\n').map(s => s.trim()).filter(Boolean) }; if (current.value && !creatingQuestion.value) { current.value.content = value; current.value.question = value } else { state.value.questions.push({ question_id: null, points: 10, content: value, question: value }); index.value = state.value.questions.length - 1 } content.value = null; touch(); revealQuestion() }
const loadBank = (page: number, size: number) => props.request(`/api/v1/questions/page?course_id=${state.value?.course_id}&keyword=${encodeURIComponent(keyword.value)}&page=${page}&page_size=${size}`, { signal: controller.signal }) as Promise<{ items: BankQuestion[]; total: number; page: number; page_size: number }>
const loadHistory = (page: number, size: number) => props.request(`/api/v1/assignments/${props.assignmentId}/revisions?page=${page}&page_size=${size}`, { signal: controller.signal }) as Promise<{ items: Revision[]; total: number; page: number; page_size: number }>
async function save() {
  if (!state.value || busy.value || !editable.value) return
  if (content.value) { error.value='请先应用或取消当前题目编辑，再保存整份草稿。'; return }
  busy.value = true; error.value = ''; message.value = ''
  try {
    state.value = await props.request(`/api/v1/assignments/${props.assignmentId}/editor`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: state.value.revision, title: state.value.title, description: state.value.description, due_at: state.value.due_at ? new Date(state.value.due_at).toISOString() : null, ai_policy: state.value.ai_policy, reason: reason.value, questions: state.value.questions.map(q => ({ question_id: q.question_id, points: q.points, content: q.content || null })) }) }) as State
    dirty.value = false; preview.value = null; confirmed.value = false; message.value = '草稿已保存，学生暂不可见。'; emit('saved', props.assignmentId)
  } catch (e) { error.value = e instanceof Error ? e.message : '保存失败，请重试' }
  finally { busy.value = false }
}
async function readPreview() {
  if (dirty.value) { error.value = '请先保存草稿，再查看发布预览。'; return }
  busy.value = true; error.value = ''
  try { preview.value = await props.request(`/api/v1/assignments/${props.assignmentId}/publication-preview`) as State; tab.value = 'preview'; confirmed.value = false }
  catch (e) { error.value = e instanceof Error ? e.message : '预览读取失败' }
  finally { busy.value = false }
}
async function publish() {
  if (!preview.value?.signature || !confirmed.value || busy.value) return
  busy.value = true; error.value = ''
  try { state.value = await props.request(`/api/v1/assignments/${props.assignmentId}/publish`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signature: preview.value.signature, confirmed: true }) }) as State; message.value = '作业已发布。'; preview.value = null; tab.value = 'edit'; emit('saved', props.assignmentId) }
  catch (e) { error.value = e instanceof Error ? e.message : '发布结果未确认，请刷新核对后再操作' }
  finally { busy.value = false }
}
let forkId = crypto.randomUUID()
async function fork() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { const next = await props.request(`/api/v1/assignments/${props.assignmentId}/fork`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_id: forkId }) }) as State; dirty.value = false; emit('saved', next.id); emit('close') }
  catch (e) { error.value = e instanceof Error ? e.message : '修订草稿创建结果未确认，可重试核对' }
  finally { busy.value = false }
}
</script>
<template>
  <DetailDialog title="作业编辑与发布" :description="state?.title" :close-disabled="busy" @close="close">
    <p v-if="error" class="editor-error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p><p v-if="busy" role="status"><span class="ui-spinner" />正在处理…</p>
    <template v-if="state"><nav class="editor-tabs"><button type="button" :aria-current="tab==='edit'?'page':undefined" @click="tab='edit'">{{ editable ? '编辑草稿' : '已发布版本' }}</button><button type="button" :disabled="busy" @click="readPreview">发布预览</button><button type="button" @click="tab='history'">修订历史</button></nav>
      <section v-if="tab==='edit'" class="assignment-editor"><p v-if="!editable">已发布内容保持不变。需要调整题目或辅助规则时，请另建修订草稿。</p><label>作业名称<input v-model="state.title" :disabled="!editable||busy" minlength="2" maxlength="200" @input="touch" /></label><label>作业说明<textarea v-model="state.description" :disabled="!editable||busy" rows="2" maxlength="3000" @input="touch" /></label><label>截止时间<input :value="state.due_at ? new Date(new Date(state.due_at).getTime()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16) : ''" type="datetime-local" :disabled="!editable||busy" @input="state.due_at=($event.target as HTMLInputElement).value; touch()" /></label><label>本作业 AI 辅助<select v-model="state.ai_policy" :disabled="!editable||busy" @change="touch"><option value="disabled">不开放辅助</option><option value="hints">仅提供概念与思路提示</option><option value="guided">允许分步辅导</option></select></label>
        <header class="editor-row"><strong>{{ state.questions.length }} 道题 · 合计 {{ total }} 分</strong><div v-if="editable"><button type="button" @click="picker=!picker">从题库添加</button><button type="button" @click="index=state.questions.length; editQuestion(true)">新建题目</button></div></header>
        <section v-if="picker" class="editor-picker"><form @submit.prevent="keyword=search.trim()"><input v-model="search" type="search" placeholder="查询本课程题目" /><button type="submit">查询</button></form><PagedList :items="bankRows" :load-page="loadBank" :scope="keyword" :page-size="5" label="添加作业题目" v-slot="{items}"><button v-for="q in items" :key="q.id" class="editor-bank-row" type="button" :disabled="state.questions.some(row=>row.question_id===q.id)" @click="add(q)">{{ q.stem.slice(0,100) }} ＋</button></PagedList></section>
        <PagedList ref="questionList" :items="state.questions" :page-size="8" label="作业草稿题目" v-slot="{items}"><div class="editor-question-list"><button v-for="q in items" :key="state.questions.indexOf(q)" type="button" :aria-current="index===state.questions.indexOf(q)?'step':undefined" @click="chooseQuestion(state.questions.indexOf(q))"><span>{{ state.questions.indexOf(q)+1 }}</span><strong>{{ q.question.stem.slice(0,100) }}</strong><small>{{ q.points }} 分</small></button></div></PagedList>
        <section v-if="current" class="editor-current"><div class="editor-row"><span>第 {{ index+1 }} 题 · {{ labels[current.question.question_type] }}</span><div v-if="editable"><button type="button" :disabled="index===0" @click="move(-1)">上移</button><button type="button" :disabled="index===state.questions.length-1" @click="move(1)">下移</button><button type="button" @click="remove">移除</button></div></div><RichText :source="current.question.stem" :tools="false" /><label>分值<input v-model.number="current.points" type="number" min="0.01" max="1000" step="0.01" :disabled="!editable||busy" @input="touch" /></label><button v-if="editable && !content" type="button" @click="editQuestion()">编辑本题内容（保存为独立新题）</button></section>
        <form v-if="content" class="editor-content" @submit.prevent="applyContent"><label>题型<select v-model="content.question_type"><option v-for="(label,key) in labels" :key="key" :value="key">{{ label }}</option></select></label><label>题干<textarea v-model="content.stem" required minlength="2" maxlength="5000" rows="3" /></label><label>选项（每行一项）<textarea v-model="options" rows="3" /></label><label>参考答案<textarea v-model="content.correct_answer" required maxlength="2000" rows="2" /></label><label>解析<textarea v-model="content.explanation" maxlength="5000" rows="3" /></label><div class="editor-row"><label>设计难度<input v-model.number="content.difficulty" type="number" min="1" max="5" required /></label><label>知识点<input v-model="content.knowledge_point" maxlength="200" /></label></div><div><button type="submit">应用到本草稿</button><button type="button" @click="content=null">取消题目编辑</button></div></form>
        <label v-if="editable">修订说明<input v-model="reason" minlength="2" maxlength="500" /></label>
      </section>
      <section v-if="tab==='preview'&&preview"><h3>{{ preview.title }}</h3><p>{{ preview.questions.length }} 道题 · 总分 {{ preview.max_score }}</p><p>截止：{{ preview.due_at ? new Date(preview.due_at).toLocaleString('zh-CN') : '未设置' }} · AI 辅助：{{ {disabled:'未开放',hints:'思路提示',guided:'分步辅导'}[preview.ai_policy as 'disabled'|'hints'|'guided'] }}</p><RichText :source="preview.description||''" :tools="false" /><PagedList :items="preview.questions" :page-size="5" label="作业发布预览" v-slot="{items}"><article v-for="q in items" :key="q.question_id!" class="editor-preview-question"><strong>{{ q.points }} 分</strong><RichText :source="q.question.stem" :tools="false" /><ol><li v-for="option in q.question.options" :key="option">{{ option }}</li></ol><details><summary>核对答案与解析</summary><RichText :source="q.question.correct_answer" :tools="false" /><RichText :source="q.question.explanation||''" :tools="false" /></details></article></PagedList><label v-if="editable" class="editor-confirm"><input v-model="confirmed" type="checkbox" />已核对题目、分值、截止时间与 AI 辅助规则，确认发布</label></section>
      <PagedList v-if="tab==='history'" :items="revisionRows" :load-page="loadHistory" :scope="String(state.revision)" :page-size="5" label="作业修订历史" v-slot="{items,total}"><details v-for="row in items" :key="row.revision" class="editor-history"><summary>第 {{ row.revision }} 次保存 · {{ row.reason }}</summary><p>{{ new Date(row.created_at).toLocaleString('zh-CN') }} · {{ row.content.title }} · {{ row.content.status }}</p><article v-for="(q,i) in row.content.questions" :key="i"><strong>第 {{ i+1 }} 题 · {{ q.points }} 分</strong><RichText :source="q.question.stem" :tools="false" /></article></details><p v-if="!total">尚无修订快照；原作业不会被补写或重算。</p></PagedList>
    </template>
    <template #footer><span>{{ dirty ? '有未保存的修改' : state ? '已保存 · 修订 '+state.revision : '' }}</span><div class="editor-row"><button v-if="editable&&tab==='edit'" type="button" :disabled="busy||!dirty||!state?.questions.length" @click="save">保存草稿</button><button v-if="editable&&tab==='preview'" type="button" :disabled="busy||!confirmed" @click="publish">确认发布</button><button v-if="state&&!editable" type="button" :disabled="busy" @click="fork">创建修订草稿</button></div></template>
  </DetailDialog>
</template>
<style scoped>
.assignment-editor{display:grid;gap:12px;font-size:13px;min-width:0}.editor-tabs,.editor-row,.editor-row>div{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.editor-tabs{border-bottom:1px solid #e4ebf7;padding-bottom:12px;margin-bottom:16px}.editor-tabs [aria-current]{background:#405fba;color:#fff}label{display:grid;gap:7px;min-width:0}input,textarea,select{font:inherit;width:100%;min-width:0;box-sizing:border-box}button{font-size:12px}.editor-row{justify-content:space-between}.editor-question-list{display:grid;gap:6px}.editor-question-list>button{display:flex;align-items:center;gap:10px;text-align:left;padding:10px;background:#f7f9fe;border:1px solid #e3eaf5;min-width:0}.editor-question-list strong{flex:1;font-size:12px;min-width:0;overflow-wrap:anywhere}.editor-question-list [aria-current]{border-color:#6a86d8;background:#edf2ff}.editor-question-list small{white-space:nowrap;color:#7184a2}.editor-current,.editor-content,.editor-picker{border:1px solid #dce5f4;border-radius:12px;background:#f8faff;padding:14px;display:grid;gap:12px}.editor-current label{max-width:130px}.editor-bank-row{display:block;width:100%;text-align:left;margin-block:6px;overflow-wrap:anywhere}.editor-picker form{display:flex;gap:8px}.editor-error{color:#ad4838}.editor-preview-question,.editor-history{border-bottom:1px solid #e0e8f6;padding-block:16px}.editor-confirm{display:flex;align-items:flex-start;gap:10px;font-size:12px;margin-top:18px}.editor-confirm input{width:auto}.editor-history summary{cursor:pointer;color:#395a92}.editor-content>div{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:500px){.editor-tabs{gap:4px}.editor-tabs button{padding:9px;font-size:11px}.editor-current,.editor-content{padding:10px}.editor-row>label{flex:1;min-width:100px}}
</style>

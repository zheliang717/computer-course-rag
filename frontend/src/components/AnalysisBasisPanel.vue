<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
const RichText = defineAsyncComponent(() => import('./RichText.vue'))
const props = defineProps<{ base: string; token: string; owner: string; draftId: string }>()
const emit = defineEmits<{ openAssignment: [id: string] }>()
type Page<T> = { items: T[]; total: number; page: number; page_size: number }
type Question = { question_id: string; position: number; stem: string; options: string[]; knowledge_point?: string;
  correct_answer: string; explanation?: string; question_type: string; student_answer?: string;
  objective_correct?: boolean | null; correct_count?: number; wrong_count?: number; unscored_count?: number; input_truncated?: boolean;
  objective_counts_available?: boolean; answer_distribution?: Array<{answer: string; count: number; answer_truncated: boolean}>; distribution_other_count?: number }
type Work = { submission_id: string; student_name: string; grading_status: string; recorded_score: number; max_score: number;
  teacher_feedback?: string; teacher_feedback_truncated?: boolean;
  answers: Array<{ question_id: string; position: number; stem: string; answer: string; truncated: boolean }> }
type Basis = { kind: 'review' | 'student_analysis'; assignment_id: string; status: 'saved' | 'legacy' | 'unavailable';
  captured_at: string | null; input_kind: 'online' | 'local_outline' | null; stale: boolean | null;
  facts: Record<string, unknown>; questions: Page<Question>; work: Page<Work>; notice: string; scope_note: string;
  content_edited: boolean | null; original_content: string | null; content_notes: Array<{code: string; excerpt: string; message: string}> }
const opened = ref(false), loading = ref(false), error = ref(''), result = ref<Basis | null>(null)
let sequence = 0, controller: AbortController | null = null, disposed = false
const metrics = computed(() => {
  const f = result.value?.facts || {}
  return result.value?.kind === 'review' ? [
    ['已提交', f.submission_count], ['已批改', f.graded_count], ['待批改', f.pending_review_count],
    ['已批改平均得分率', typeof f.average_percent === 'number' ? `${f.average_percent}%` : null],
    ['提供题目', f.question_count_analyzed === undefined ? null : `${f.question_count_analyzed}/${f.question_count_total}`],
    ['具体作答', f.student_work_included === undefined ? '未提供' : `${f.student_work_included}/${f.student_work_total}`]]
    : [['学生', f.student_name], ['批改状态', f.grading_status === 'graded' ? '已批改' : f.grading_status ? '待批改' : null],
      ['提供题目', f.question_count_analyzed === undefined ? null : `${f.question_count_analyzed}/${f.question_count_total}`],
      ['记录分数', f.recorded_score === undefined ? null : `${f.recorded_score}/${f.max_score}`]]
})
async function load(questionPage = result.value?.questions.page || 1, workPage = result.value?.work.page || 1) {
  if (loading.value) return
  const current = sequence; loading.value = true; error.value = ''
  controller = new AbortController(); const ownController = controller
  const timeout = window.setTimeout(() => ownController.abort(), 20000)
  try {
    const response = await fetch(`${props.base}/api/v1/teaching-drafts/${props.draftId}/analysis-basis?question_page=${questionPage}&work_page=${workPage}&page_size=5`,
      { headers: { Authorization: `Bearer ${props.token}` }, signal: ownController.signal })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '依据暂不可读，请稍后重试。')
    if (!disposed && sequence === current) result.value = data
  } catch (value) { if (!disposed && sequence === current) { result.value = null; error.value = value instanceof Error ? value.message : '读取失败，请重试。' } }
  finally { clearTimeout(timeout); if (sequence === current) { loading.value = false; controller = null } }
}
async function toggle() { opened.value = !opened.value; if (opened.value) await load() }
function reset() { sequence++; controller?.abort(); controller = null; opened.value = false; result.value = null; error.value = ''; loading.value = false }
watch(() => [props.token, props.owner, props.draftId], reset)
onBeforeUnmount(() => { disposed = true; reset() })
</script>

<template>
  <section class="analysis-basis" aria-label="平台事实与生成依据" :aria-busy="loading">
    <button type="button" class="basis-toggle" :aria-expanded="opened" @click="toggle"><span><b>平台事实与生成依据</b><small>核对当时实际提供的题目、统计和作答</small></span><em>{{ opened ? '收起 ↑' : '展开核对 ›' }}</em></button>
    <div v-if="opened" class="basis-body">
      <p v-if="loading" role="status" class="basis-loading"><i aria-hidden="true" />正在读取保存依据…</p>
      <p v-if="error" role="alert" class="basis-warning">{{ error }}</p>
      <div class="basis-actions"><button type="button" :disabled="loading" @click="load()">{{ error ? '重试读取' : '刷新依据状态' }}</button><button v-if="result" type="button" :disabled="loading" @click="emit('openAssignment', result.assignment_id)">打开当前作业 ↗</button></div>
      <template v-if="result">
        <div class="basis-labels"><span>{{ result.status === 'saved' ? '生成时保存的输入' : '旧版摘要 · 非完整原文' }}</span><small v-if="result.captured_at">{{ new Date(result.captured_at).toLocaleString('zh-CN') }}</small><small v-if="result.input_kind">{{ result.input_kind === 'online' ? '在线分析输入' : '站内提纲输入 · 未发送模型' }}</small></div>
        <p :class="result.status === 'saved' ? 'basis-note' : 'basis-warning'">{{ result.notice }}</p>
        <p v-if="result.stale" class="basis-warning">关联作答、题目或批改记录已经变化。下方是原版本依据，不是当前学情；发布仍由服务端核对。</p>
        <p v-else-if="result.stale === null" class="basis-note">旧版缺少用于比对的完整记录，不能确认是否仍与当前数据一致。</p>
        <div class="basis-metrics"><article v-for="metric in metrics" :key="String(metric[0])"><small>{{ metric[0] }}</small><b>{{ metric[1] ?? '未记录' }}</b></article></div>
        <p class="basis-note">{{ result.scope_note }}</p>
        <section v-if="result.content_notes.length" aria-label="讲评表述核对"><p class="basis-note">以下是有限措辞检查，不是完整语义校验；未出现提示也不代表正文正确。</p><article v-for="note in result.content_notes" :key="note.code" class="basis-warning"><strong>建议人工核对</strong><p>{{ note.message }}</p><blockquote>{{ note.excerpt }}</blockquote></article></section>
        <details v-if="result.original_content" class="basis-item"><summary>{{ result.input_kind === 'online' ? '生成时的AI原始正文（未核实）' : '生成时的站内提纲' }}<small>{{ result.content_edited ? '当前正文已有教师修改' : '与当前正文分开保留' }}</small></summary><RichText :source="result.original_content" /></details>
        <details v-if="result.facts.teacher_feedback" class="basis-item"><summary>生成时的教师评语 <small v-if="result.facts.teacher_feedback_truncated">节选</small></summary><pre>{{ result.facts.teacher_feedback }}</pre></details>
        <template v-if="result.questions.total">
          <header class="basis-section"><h4>逐题核对</h4><small>仅展示当时提供的 {{ result.questions.total }} 题</small></header>
          <details v-for="question in result.questions.items" :key="question.question_id" class="basis-item">
            <summary><b>第 {{ question.position }} 题</b><span>{{ question.knowledge_point || question.stem.slice(0, 40) }}</span><small>{{ question.input_truncated ? '输入有节选' : '展开原输入' }}</small></summary>
            <RichText :source="question.stem" /><ol v-if="question.options?.length" type="A"><li v-for="(option,index) in question.options" :key="index">{{ option }}</li></ol>
            <div v-if="question.student_answer !== undefined" class="basis-answer"><strong>该学生的实际回答</strong><pre>{{ question.student_answer || '未作答' }}</pre><small>{{ question.objective_correct === null ? '主观题 · 无逐题客观判定' : question.objective_correct ? '平台客观判定：正确' : '平台客观判定：错误或未答对' }}</small></div>
            <p v-else-if="question.question_type === 'short_answer'" class="basis-note">主观题没有逐题客观正误判定；整份批改状态见上方，不据此记为待批改。</p>
            <div v-else class="basis-counts"><span>客观答对 {{ question.correct_count }}</span><span>客观答错 {{ question.wrong_count }}</span></div>
            <details v-if="question.answer_distribution?.length" class="basis-reference"><summary>查看平台原始答案分布</summary><ul><li v-for="(entry,index) in question.answer_distribution" :key="index">{{ entry.answer || '未作答' }}{{ entry.answer_truncated ? '（节选）' : '' }} · {{ entry.count }}份</li><li v-if="question.distribution_other_count">其他答案 · {{ question.distribution_other_count }}份</li></ul></details>
            <details class="basis-reference"><summary>核对输入中的参考答案与解析</summary><RichText :source="question.correct_answer" /><RichText v-if="question.explanation" :source="question.explanation" /></details>
          </details>
          <nav v-if="result.questions.total > 5" class="basis-pages" aria-label="依据题目分页"><small>{{ result.questions.page }}/{{ Math.ceil(result.questions.total / 5) }}页</small><button :disabled="loading || result.questions.page <= 1" @click="load(result.questions.page-1)">上一页</button><button :disabled="loading || result.questions.page*5 >= result.questions.total" @click="load(result.questions.page+1)">下一页</button></nav>
        </template>
        <template v-if="result.work.total">
          <header class="basis-section"><h4>实际提供的作答</h4><small>共 {{ result.work.total }} 份，不等于全班全部作答</small></header>
          <details v-for="work in result.work.items" :key="work.submission_id" class="basis-item"><summary><b>{{ work.student_name }}</b><span>{{ work.grading_status === 'graded' ? '已批改' : '待批改' }}</span><small>{{ work.grading_status === 'graded' ? '记录成绩' : '暂得分' }} {{ work.recorded_score }}/{{ work.max_score }}</small></summary><div v-for="answer in work.answers" :key="answer.question_id" class="basis-answer"><strong>第 {{ answer.position }} 题 · {{ answer.stem }}{{ answer.truncated ? ' · 回答节选' : '' }}</strong><pre>{{ answer.answer || '未作答' }}</pre></div><div v-if="work.teacher_feedback" class="basis-answer"><strong>教师评语{{ work.teacher_feedback_truncated ? '（节选）' : '' }}</strong><pre>{{ work.teacher_feedback }}</pre></div></details>
          <nav v-if="result.work.total > 5" class="basis-pages" aria-label="依据作答分页"><small>{{ result.work.page }}/{{ Math.ceil(result.work.total / 5) }}页</small><button :disabled="loading || result.work.page <= 1" @click="load(result.questions.page,result.work.page-1)">上一页</button><button :disabled="loading || result.work.page*5 >= result.work.total" @click="load(result.questions.page,result.work.page+1)">下一页</button></nav>
        </template>
      </template>
    </div>
  </section>
</template>

<style scoped>
.analysis-basis{background:#f5f8fc;border:1px solid #dbe5f2;border-radius:13px;margin:15px 0;overflow:hidden}.basis-toggle{align-items:center;background:transparent;border:0;display:flex;justify-content:space-between;padding:16px;text-align:left;width:100%}.basis-toggle b{color:#3c577e;font-size:13px}.basis-toggle small{color:#8496ae;display:block;font-size:11px;margin-top:5px}.basis-toggle em{color:#6481aa;font-size:11px;font-style:normal;white-space:nowrap}.basis-body{border-top:1px solid #e2e9f2;padding:16px}.basis-actions,.basis-labels,.basis-pages{align-items:center;display:flex;flex-wrap:wrap;gap:9px}.basis-actions button,.basis-pages button{background:#fff;border:1px solid #d9e5f3;color:#53739e;font-size:11px;padding:7px 11px}.basis-labels{margin-top:14px}.basis-labels span{background:#e5edf9;border-radius:5px;color:#53739e;font-size:11px;padding:5px 8px}.basis-labels small,.basis-section small,.basis-pages small{color:#8294ab;font-size:10px}.basis-note,.basis-warning,.basis-loading{font-size:11px;line-height:1.85}.basis-note{color:#6b809c}.basis-warning{background:#fff5e8;border-radius:7px;color:#9a703f;padding:10px}.basis-metrics{display:grid;gap:9px;grid-template-columns:repeat(auto-fit,minmax(115px,1fr));margin:15px 0}.basis-metrics article{background:white;border:1px solid #e3eaf4;border-radius:9px;padding:12px}.basis-metrics small{color:#8295af;display:block;font-size:10px}.basis-metrics b{color:#405e86;display:block;font-size:17px;margin-top:7px}.basis-section{align-items:center;display:flex;flex-wrap:wrap;gap:12px;margin-top:20px}.basis-section h4{color:#456187;font-size:13px;margin:0}.basis-item{background:white;border:1px solid #e0e8f2;border-radius:9px;margin-top:9px;padding:12px}.basis-item>summary{align-items:center;color:#5c7699;cursor:pointer;display:flex;flex-wrap:wrap;gap:10px;font-size:12px;list-style:none}.basis-item>summary:before{content:'›'}.basis-item[open]>summary:before{content:'⌄'}.basis-item summary small{color:#8c9bb0;font-size:10px;margin-left:auto}.basis-item pre{color:#4b6587;font-family:inherit;font-size:12px;line-height:1.85;overflow-wrap:anywhere;white-space:pre-wrap}.basis-item :deep(.answer-markdown){color:#4e6687;font-size:12px;line-height:1.85}.basis-item ol{color:#597295;font-size:12px;line-height:1.85}.basis-answer{border-top:1px solid #e8edf5;margin-top:12px;padding-top:12px}.basis-answer strong,.basis-answer small{color:#7488a3;font-size:11px}.basis-reference{color:#6b85a9;cursor:pointer;font-size:11px;margin-top:12px}.basis-counts{color:#8193ad;display:flex;flex-wrap:wrap;font-size:11px;gap:12px;margin-top:12px}.basis-pages{justify-content:flex-end;margin-top:12px}.basis-loading{align-items:center;color:#6986ac;display:flex;gap:8px}.basis-loading i{animation:basis-pulse 1s infinite alternate;background:#7898c3;border-radius:50%;height:7px;width:7px}button:disabled{cursor:not-allowed;opacity:.5}@keyframes basis-pulse{to{opacity:.25}}@media(prefers-reduced-motion:reduce){.basis-loading i{animation:none}}
</style>

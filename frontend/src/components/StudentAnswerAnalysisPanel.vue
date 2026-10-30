<script setup lang="ts">
import { ref, watch } from 'vue'
import type { StudentAnswerAnalysisResult } from '../studentAnswerAnalysis'

const props = defineProps<{
  result: StudentAnswerAnalysisResult | null; busy: boolean; loading: boolean; error: string
  studentName: string; enabled: boolean; renderMarkdown: (content: string) => string
}>()
defineEmits<{ generate: []; useFeedback: [value: string]; openDraft: [] }>()
const feedbackDraft = ref('')
watch(() => [props.result?.draft.id, props.result?.analysis.feedback_draft], () => {
  feedbackDraft.value = props.result?.analysis.feedback_draft || ''
}, { immediate: true })
</script>

<template>
  <section class="student-answer-analysis" aria-label="AI 学生作答分析" :aria-busy="busy || loading">
    <header><div><small>AI 教学助理 · 个体辅导</small><h3>{{ studentName }}的作答分析</h3></div><span>教师侧记录</span></header>
    <p class="analysis-description">结合姓名、逐题回答、参考答案与已保存的教师评语，分析理解与误区，准备后续辅导。</p>
    <div v-if="busy" class="analysis-wait" role="status"><span aria-hidden="true"><i /><i /><i /></span><div><strong>正在逐题分析作答…</strong><small>完成后自动保存为教师草稿，不会修改成绩。</small></div></div>
    <p v-else-if="loading" class="analysis-description" role="status">正在读取已有分析…</p>
    <p v-if="error" role="alert" class="analysis-error">{{ error }}</p>
    <p v-if="result?.stale" class="analysis-stale">作答、题目或批改记录已变化；下方是旧分析，建议重新分析后再采用评语。</p>
    <div class="analysis-actions"><button type="button" :disabled="busy || loading || !enabled" @click="$emit('generate')">{{ busy ? '分析中…' : result ? '重新分析本次作答' : error ? '重试 AI 作答分析' : 'AI 分析本次作答' }}</button><button v-if="result" type="button" class="ghost-button" :disabled="busy" @click="$emit('openDraft')">在教师草稿箱中编辑 ↗</button></div>
    <p v-if="!enabled" class="analysis-description">在线 AI 尚未就绪，可继续查看回答和人工批改。</p>
    <p v-else class="analysis-scope">点击分析会将该学生姓名和本次作答发送给 AI 模型；不会发送全校数据或自动发布。</p>
    <template v-if="result">
      <small class="analysis-coverage">本次覆盖 {{ result.question_count_analyzed }}/{{ result.question_count_total }} 题 · 最多逐题分析 12 题</small>
      <p v-if="result.content_edited" class="analysis-description">下方为教师已编辑保存的正文；原始AI建议评语另列，不会根据正文自动重写。</p>
      <div class="answer-markdown" v-html="renderMarkdown(result.draft.content)" />
      <section class="feedback-suggestion"><details><summary>核对AI原始建议评语</summary><p>{{ result.analysis.feedback_draft }}</p></details><label>整理给学生的评语<textarea v-model="feedbackDraft" rows="4" maxlength="2000" :disabled="busy || result.stale" /></label><div><small>这里的整理暂未保存；填入后仍须点击“保存批改”才更新学生记录。</small><button type="button" :disabled="busy || result.stale || feedbackDraft.trim().length < 2" @click="$emit('useFeedback', feedbackDraft.trim())">填入评语编辑框</button></div></section>
    </template>
  </section>
</template>

<style scoped>
.student-answer-analysis { background: #f5f8fd; border: 1px solid #d6e3f4; border-radius: 14px; padding: 17px; }
header { align-items: center; display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; }
header small { color: #6d85ab; font-size: 11px; }
h3 { color: #2c456c; font-size: 17px; margin: 6px 0; }
header > span { background: #e7eef9; border-radius: 16px; color: #617da6; font-size: 11px; padding: 6px 10px; }
.analysis-description, .analysis-scope { color: #6a7c94; font-size: 12px; line-height: 1.8; }
.analysis-scope { font-size: 11px; }
.analysis-actions { display: flex; flex-wrap: wrap; gap: 9px; margin: 14px 0 8px; }
.analysis-actions button { font-size: 12px; padding: 10px 14px; }
.analysis-coverage { color: #6f84a2; display: block; margin: 16px 0 8px; }
.analysis-error, .analysis-stale { border-radius: 8px; color: #9b6543; font-size: 12px; line-height: 1.8; padding: 10px; background: #fff4e9; }
.analysis-wait { align-items: center; background: #e9f0fb; border-radius: 10px; display: flex; gap: 13px; padding: 15px; }
.analysis-wait > span { display: flex; gap: 4px; }
.analysis-wait i { animation: wait 1.2s infinite; background: #7598cb; border-radius: 50%; height: 6px; width: 6px; }
.analysis-wait i:nth-child(2) { animation-delay: .15s; }
.analysis-wait i:nth-child(3) { animation-delay: .3s; }
.analysis-wait strong, .analysis-wait small { color: #4e6d9a; display: block; font-size: 12px; line-height: 1.8; }
.analysis-wait small { font-size: 11px; }
.feedback-suggestion { background: #fff; border: 1px solid #e0e8f3; border-radius: 10px; padding: 13px; }
.feedback-suggestion > div { align-items: center; display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; }
.feedback-suggestion strong { color: #4a658d; font-size: 13px; }
.feedback-suggestion button { background: #e8f0fc; color: #5675a4; font-size: 11px; padding: 7px 10px; }
.feedback-suggestion p { color: #5e728f; font-size: 13px; line-height: 1.8; white-space: pre-wrap; }
.feedback-suggestion summary { color: #6f87aa; cursor: pointer; font-size: 11px; }
.feedback-suggestion label { color: #607da4; display: grid; font-size: 12px; gap: 8px; margin: 14px 0; }
.feedback-suggestion textarea { box-sizing: border-box; font-family: inherit; font-size: 12px; line-height: 1.8; resize: vertical; width: 100%; }
.feedback-suggestion small { color: #8191a8; font-size: 11px; }
@keyframes wait { 50% { opacity: .25; transform: translateY(-3px); } }
@media (prefers-reduced-motion: reduce) { .analysis-wait i { animation: none; } }
</style>

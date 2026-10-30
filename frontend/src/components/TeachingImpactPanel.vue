<script setup lang="ts">
import type { TeachingImpact } from '../teachingInsights'
defineProps<{ impact: TeachingImpact | null; busy: boolean; error: string; hideBatchPractice?: boolean }>()
defineEmits<{ refresh: [] }>()
</script>

<template>
  <section class="teaching-impact" aria-label="学习记录回看" :aria-busy="busy">
    <header><div><small>FOLLOW THROUGH</small><h3>学习记录回看<span v-if="impact?.topic"> · {{ impact.topic }}</span></h3></div><button type="button" :disabled="busy" @click="$emit('refresh')">{{ busy ? '读取中…' : '刷新记录' }}</button></header>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="busy" role="status">正在读取最新记录…</p>
    <template v-if="impact">
      <div v-if="impact.baseline.focus && impact.current_focus" class="impact-comparison">
        <div><small>生成草稿时</small><strong>{{ impact.baseline.focus.unresolved_students }} <em>人待巩固</em></strong><span>{{ impact.baseline.focus.unresolved_questions }} 条未掌握错题记录</span><span>此前14天：{{ impact.baseline.focus.practice.scored_attempts }} 次已评分练习 · {{ impact.baseline.focus.practice.accuracy_percent === null ? '暂无正确率' : `${impact.baseline.focus.practice.accuracy_percent}% 正确率` }}</span></div>
        <div><small>当前记录</small><strong>{{ impact.current_focus.unresolved_students }} <em>人待巩固</em></strong><span>{{ impact.current_focus.unresolved_questions }} 条未掌握错题记录</span><span>最近14天：{{ impact.current_focus.practice.scored_attempts }} 次已评分练习 · {{ impact.current_focus.practice.accuracy_percent === null ? '暂无正确率' : `${impact.current_focus.practice.accuracy_percent}% 正确率` }}</span></div>
      </div>
      <p v-else>已保存生成时的匿名课程快照；本草稿未指定单一知识点。</p>
      <template v-if="!hideBatchPractice"><div v-if="impact.published_question_practice" class="published-practice"><strong>本批 {{ impact.published_question_count }} 道入库题目</strong><p v-if="impact.published_question_practice.attempts">入库后 {{ impact.published_question_practice.students }} 人参与、{{ impact.published_question_practice.attempts }} 次练习，其中 {{ impact.published_question_practice.scored_attempts }} 次已评分<span v-if="impact.published_question_practice.accuracy_percent !== null">，正确率 {{ impact.published_question_practice.accuracy_percent }}%</span>。</p><p v-else>尚未收到本批题目的练习记录，可审核并安排后续练习。</p></div>
      <p v-else class="impact-note">{{ impact.published_at ? '本草稿没有可追踪的入库题目。' : '草稿尚未入库；确认教案不等于已经授课，暂不计算入库后练习。' }}</p></template>
      <p v-if="impact.current_student_count !== impact.baseline.student_count" class="impact-note">课程成员数量已变化：{{ impact.baseline.student_count }} → {{ impact.current_student_count }}，两个时点不宜直接比较。</p>
      <p class="impact-note">{{ impact.note }}</p>
    </template>
  </section>
</template>

<style scoped>
.teaching-impact { background: #f6f9fd; border: 1px solid #dbe5f3; border-radius: 13px; padding: 15px; }
header { align-items: center; display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; }
header small { color: #8498b6; font-size: 10px; letter-spacing: 1px; }
h3 { color: #365174; font-size: 14px; margin: 5px 0; }
header button { background: #e7effc; border-radius: 8px; color: #5677a7; font-size: 11px; padding: 7px 10px; }
.impact-comparison { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 13px; }
.impact-comparison div { background: #fff; border: 1px solid #e5ebf3; border-radius: 10px; padding: 12px; }
.impact-comparison small, .impact-comparison span { color: #7f8ea5; display: block; font-size: 11px; line-height: 1.7; }
.impact-comparison strong { color: #3f5d83; display: block; font-size: 24px; margin: 6px 0; }
.impact-comparison em { font-size: 11px; font-style: normal; font-weight: 400; }
.published-practice { background: #edf3fc; border-radius: 9px; color: #526c94; margin-top: 12px; padding: 12px; }
.published-practice strong { font-size: 12px; }
p { color: #78889f; font-size: 12px; line-height: 1.7; }
.impact-note { font-size: 11px; margin-bottom: 0; }
@media (max-width: 540px) { .impact-comparison { grid-template-columns: 1fr; } }
</style>

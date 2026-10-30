<script setup lang="ts">
import type { TeachingInsights } from '../teachingInsights'
defineProps<{ insights: TeachingInsights | null; busy: boolean; error: string; courseId: string }>()
defineEmits<{
  refresh: []; prepare: [topic: string, type: 'lesson_plan' | 'question_set']; review: [assignmentId: string]; assignments: []; cohort: []
}>()
</script>

<template>
  <section class="teacher-insights" aria-label="本课程教学建议" :aria-busy="busy">
    <header><div><small>教学观察</small><h3>{{ insights?.course_title || '本课程学情' }}</h3></div><button type="button" :disabled="busy || !courseId" @click="$emit('refresh')">{{ busy ? '读取中…' : '刷新' }}</button></header>
    <p v-if="!courseId" class="muted-note">先选择教学课程，再查看本课程的学习记录。</p>
    <p v-if="busy" role="status" class="loading-note"><span />正在核对课程记录…</p>
    <p v-if="error" role="alert" class="error-note">{{ error }} <button type="button" :disabled="busy" @click="$emit('refresh')">重试</button></p>
    <template v-if="insights">
      <button type="button" class="cohort-entry" @click="$emit('cohort')"><strong>✦ 全体成绩与 AI 综合分析</strong><small>成绩分布 · 作业表现 · 按姓名跟进学生</small><span>打开学情总览 ›</span></button>
      <div class="insight-metrics"><span><b>{{ insights.student_count }}</b>在课学生</span><span><b>{{ insights.pending_review_count }}</b>待批改提交</span><span><b>{{ insights.weak_points.length }}</b>重点观察项</span></div>
      <div class="insight-section-heading"><strong>值得巩固的知识点</strong><small>最多 5 项</small></div>
      <article v-for="point in insights.weak_points" :key="point.topic" class="weak-point-card">
        <strong>{{ point.topic }}</strong><p>{{ point.unresolved_students }} 位学生 · {{ point.unresolved_questions }} 条未掌握错题记录</p>
        <div><button type="button" @click="$emit('prepare', point.topic, 'lesson_plan')">准备教案 ↗</button><button type="button" @click="$emit('prepare', point.topic, 'question_set')">补充练习 ↗</button></div>
      </article>
      <p v-if="!insights.weak_points.length" class="muted-note">尚无带知识点标注的未掌握错题，可先安排诊断练习；不代表所有学生都已掌握。</p>
      <div class="insight-section-heading"><strong>学生作答、AI 分析与讲评</strong><button type="button" @click="$emit('assignments')">全部作业 ›</button></div>
      <button v-for="item in insights.assignments" :key="item.id" type="button" class="review-assignment" @click="$emit('review', item.id)">
        <span><strong>{{ item.title }}</strong><small>{{ item.submission_count }} 份提交 · {{ item.pending_review_count ? `${item.pending_review_count} 份待批改` : item.has_published_review ? '可查看或更新讲评' : '可准备讲评' }}</small></span><b>打开 ›</b>
      </button>
      <p v-if="!insights.assignments.length" class="muted-note">暂时没有已收到提交的作业。</p>
      <p class="muted-note footer-note">展示最近有提交的 5 份作业。以上为平台记录，不是模型推测；错题样本仅作教学线索。</p>
      <p class="muted-note footer-note">更新于 {{ new Date(insights.generated_at).toLocaleString('zh-CN', { hour12: false }) }}</p>
    </template>
  </section>
</template>

<style scoped>
.teacher-insights { background: #f7f9fd; border: 1px solid #dde5f1; border-radius: 16px; margin: 12px 18px; padding: 15px; }
.cohort-entry { background: linear-gradient(120deg, #e8efff, #f0edff); border: 1px solid #d8e1f8; border-radius: 11px; color: #456aa9; display: grid; gap: 7px; margin: 14px 0; padding: 14px; text-align: left; width: 100%; }
.cohort-entry strong { font-size: 13px; }.cohort-entry small { color: #8193b2; font-size: 10px; }.cohort-entry span { font-size: 11px; }
header, .insight-section-heading { align-items: center; display: flex; gap: 10px; justify-content: space-between; }
header small { color: #6b82a5; font-size: 10px; letter-spacing: 1px; }
h3 { color: #263d62; font-size: 15px; margin: 4px 0; }
header button, .insight-section-heading button { background: transparent; color: #526f9d; font-size: 11px; padding: 5px; }
.insight-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin: 14px 0; }
.insight-metrics span { background: #fff; border-radius: 10px; color: #78869b; font-size: 10px; padding: 10px 5px; text-align: center; }
.insight-metrics b { color: #344e78; display: block; font-size: 21px; margin-bottom: 3px; }
.insight-section-heading { color: #385173; font-size: 12px; margin: 16px 0 9px; }
.insight-section-heading small { color: #8996aa; font-size: 10px; }
.weak-point-card { background: #fff; border: 1px solid #e3eaf5; border-radius: 11px; margin: 8px 0; padding: 11px; }
.weak-point-card strong { color: #334d73; font-size: 13px; }
.weak-point-card p { color: #7b889e; font-size: 11px; margin: 6px 0 10px; }
.weak-point-card div { display: flex; flex-wrap: wrap; gap: 7px; }
.weak-point-card button { background: #edf3fe; border-radius: 7px; color: #4a6ca7; font-size: 11px; padding: 6px 9px; }
.review-assignment { align-items: center; background: #fff; border: 1px solid #e5eaf2; border-radius: 10px; color: #536a8c; display: flex; gap: 10px; justify-content: space-between; margin: 7px 0; padding: 10px; text-align: left; width: 100%; }
.review-assignment span { min-width: 0; }
.review-assignment strong { display: block; font-size: 11px; line-height: 1.5; overflow-wrap: anywhere; }
.review-assignment small { color: #8290a5; display: block; font-size: 10px; margin-top: 4px; }
.review-assignment b { flex-shrink: 0; font-size: 10px; }
.muted-note { color: #687b96; font-size: 12px; line-height: 1.7; }
.footer-note { font-size: 10px; margin-bottom: 0; }
.loading-note { color: #6a82a9; font-size: 11px; }
.loading-note span { animation: pulse 1.2s infinite; background: #7391c4; border-radius: 50%; display: inline-block; height: 6px; margin-right: 7px; width: 6px; }
.error-note { color: #a35052; font-size: 11px; }
@keyframes pulse { 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { .loading-note span { animation: none; } }
</style>

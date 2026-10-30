<script setup lang="ts">
import type { AnswerReview } from '../answerReview'
defineProps<{ review: AnswerReview }>()
defineEmits<{ source: [index: number] }>()
</script>
<template>
  <details class="answer-review-panel" :class="{ incomplete: review.status !== 'ai_reviewed' }">
    <summary>{{ review.status === 'ai_reviewed' ? '讲解核对记录' : '本次核对未完成' }}<span>{{ review.status === 'ai_reviewed' ? 'AI 复核 · 查看依据' : '可缩小问题后重试' }}</span></summary>
    <p>{{ review.notice }}</p>
    <ul v-if="review.corrections?.length"><li v-for="(item, index) in review.corrections" :key="index">{{ item }}</li></ul>
    <article v-for="(anchor, index) in review.anchors || []" :key="index">
      <button type="button" @click="$emit('source', anchor.source_index - 1)">{{ review.sections?.[anchor.section_index]?.heading || '本段' }} · 资料{{ anchor.source_index }} · 第{{ anchor.page_number }}页 ↗</button>
      <blockquote>{{ anchor.quote }}</blockquote>
    </article>
  </details>
</template>
<style scoped>
.answer-review-panel { border: 1px solid #dce7f6; border-radius: 12px; background: #f7faff; margin-block: 14px; padding: 0 12px; font-size: 12px; color: #51657d; }
summary { display: flex; flex-wrap: wrap; gap: 6px 12px; justify-content: space-between; cursor: pointer; padding: 11px 0; color: #315a90; font-weight: 700; }
summary span { font-size: 10px; font-weight: 400; color: #6d819a; }
p,li { line-height: 1.8; } ul { padding-left: 18px; }
article { border-top: 1px solid #e2eaf5; padding: 8px 0; }
article button { text-align: left; background: transparent; color: #315a90; padding: 4px 0; font-size: 11px; }
blockquote { margin: 6px 0; padding-left: 10px; border-left: 2px solid #c2d6f2; overflow-wrap: anywhere; line-height: 1.8; }
.incomplete { border-color: #eadbbf; background: #fffbf2; }
</style>

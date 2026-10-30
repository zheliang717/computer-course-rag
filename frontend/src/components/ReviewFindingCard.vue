<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import type { ReviewFinding } from '../questionReviews'
const RichText = defineAsyncComponent(() => import('./RichText.vue'))
const ReviewFindingDecision = defineAsyncComponent(() => import('./ReviewFindingDecision.vue'))
defineProps<{ finding: ReviewFinding; base: string; token: string; owner: string; draftId: string; reviewId: string; fingerprint: string; stale: boolean }>()
const emit = defineEmits<{ source: [id: string, page: number] }>()
const category = (value: string) => ({ ambiguity: '题意', answer: '答案', explanation: '解析', other: '审阅' }[value] || '审阅')
</script>
<template>
  <article class="finding-card" :class="{ uncertain: finding.assessment === 'uncertain' }">
    <header><b>{{ category(finding.category) }}</b><span>{{ finding.assessment === 'uncertain' ? '待核实设想' : finding.assessment === 'improvement' ? '教学完善建议' : '需教师核对的疑点' }}</span><small>{{ finding.basis_status === 'linked' ? '有原文 / 回执定位' : finding.basis_status === 'legacy' ? '旧版未记录依据' : '依据未完整匹配' }}</small></header>
    <RichText :source="finding.detail" /><p class="finding-suggestion">{{ finding.suggestion }}</p><p class="finding-boundary">{{ finding.basis_note }}</p>
    <details v-if="finding.anchors.length" class="finding-anchors"><summary>查看对应依据 · {{ finding.anchors.filter(anchor => anchor.matched).length }}/{{ finding.anchors.length }}处可定位</summary><div v-for="(anchor, index) in finding.anchors" :key="index" :class="{ unmatched: !anchor.matched }"><strong>{{ anchor.label }}</strong><pre>{{ anchor.matched ? anchor.excerpt : `模型拟引用：${anchor.quote || '未给出原文'}` }}</pre><small>{{ anchor.reason }}</small><button v-if="anchor.matched && anchor.document_id && anchor.page_number" type="button" @click="emit('source', anchor.document_id!, anchor.page_number!)">打开这段资料 ↗</button></div></details>
    <ReviewFindingDecision v-if="finding.id" :base="base" :token="token" :owner="owner" :draft-id="draftId" :review-id="reviewId" :finding-id="finding.id" :fingerprint="fingerprint" :stale="stale" />
  </article>
</template>
<style scoped>
.finding-card { background: #fff; border: 1px solid #dce7f6; border-radius: 12px; margin: 12px 0; padding: 15px; }.finding-card.uncertain { background: #fffdf8; border-color: #e9dec7; }.finding-card header { align-items: center; display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }.finding-card header b { background: #edf3fd; border-radius: 5px; color: #6b81a3; font-size: 10px; padding: 4px 6px; }.finding-card header span { color: #4a678d; font-size: 12px; font-weight: 600; }.finding-card header small { color: #93a2b8; font-size: 10px; margin-left: auto; }.finding-suggestion { color: #617c9e; font-size: 12px; line-height: 1.8; }.finding-boundary { color: #9a8c6e; font-size: 10px; line-height: 1.8; }.finding-card :deep(.answer-markdown) { color: #3d536f; font-size: 13px; line-height: 1.8; }.finding-anchors { border-top: 1px solid #e7edf5; margin-top: 10px; padding-top: 8px; }.finding-anchors summary { color: #6c87ab; cursor: pointer; font-size: 11px; padding: 4px 0; }.finding-anchors > div { background: #f4f8ff; border-left: 3px solid #b8cde8; border-radius: 6px; margin-top: 9px; padding: 12px; }.finding-anchors > div.unmatched { background: #fff6e8; border-color: #e4cb9c; }.finding-anchors strong { color: #617fa5; font-size: 11px; }.finding-anchors pre { color: #667a96; font-family: inherit; font-size: 12px; line-height: 1.8; overflow-wrap: anywhere; white-space: pre-wrap; }.finding-anchors small { color: #8b9db4; display: block; font-size: 10px; line-height: 1.7; }.finding-anchors button { background: #e8f0ff; border: 1px solid #d9e5f6; color: #5376a9; font-size: 11px; margin-top: 9px; padding: 7px 10px; }
</style>

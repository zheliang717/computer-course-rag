<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
type Stats = { design_difficulty: number; sample_students: number; correct_rate: number | null; observed_difficulty: number | null; wilson_95_interval: number[] | null; notice: string }
const props = defineProps<{ questionId: string; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
const stats = ref<Stats | null>(null), error = ref('')
let seq = 0
watch(() => props.questionId, async () => {
  const current = ++seq; stats.value = null; error.value = ''
  try { const value = await props.request(`/api/v1/questions/${props.questionId}/statistics`) as Stats; if (current === seq) stats.value = value }
  catch (e) { if (current === seq) error.value = e instanceof Error ? e.message : '统计读取失败' }
}, { immediate: true })
onBeforeUnmount(() => seq++)
const percent = (value: number) => (value * 100).toFixed(1) + '%'
</script>
<template><details class="question-stats"><summary>作答统计与难度</summary><p v-if="error" role="alert">{{ error }}</p><template v-if="stats"><dl><div><dt>教师设计难度</dt><dd>{{ stats.design_difficulty }} 级</dd></div><div><dt>首答样本</dt><dd>{{ stats.sample_students }} 人</dd></div><div><dt>首答正确率</dt><dd>{{ stats.correct_rate === null ? '暂无' : percent(stats.correct_rate) }}</dd></div><div><dt>统计难度</dt><dd>{{ stats.observed_difficulty === null ? '样本不足' : stats.observed_difficulty + ' 级' }}</dd></div></dl><p v-if="stats.wilson_95_interval">正确率 95% 区间：{{ stats.wilson_95_interval.map(percent).join(' — ') }}</p><p>{{ stats.notice }}</p></template></details></template>
<style scoped>.question-stats{border:1px solid #e1e8f5;border-radius:12px;padding:12px;font-size:12px;margin-block:14px}summary{cursor:pointer;color:#395e95;font-weight:600}dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}dt,p{color:#7a8aa2;line-height:1.7}dd{margin:6px 0;color:#314c7b;font-size:14px}@media(max-width:600px){dl{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>

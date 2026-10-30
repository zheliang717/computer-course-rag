<script setup lang="ts">
import { computed, ref, watch } from 'vue'
type Policy = { due: number; variant: number; new: number; taught: number; interval_days: number[]; revision: number }
const props = defineProps<{ courseId: string; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
const form = ref<Policy | null>(null), days = ref(''), busy = ref(false), status = ref(''), open = ref(false)
let sequence = 0
const total = computed(() => form.value ? form.value.due + form.value.variant + form.value.new + form.value.taught : 0)
watch(() => props.courseId, async () => {
  const current = ++sequence; form.value = null; status.value = ''
  try { const value = await props.request(`/api/v1/courses/${props.courseId}/practice-policy`) as Policy; if (current === sequence) { form.value = value; days.value = value.interval_days.join(', ') } }
  catch (e) { if (current === sequence) status.value = e instanceof Error ? e.message : '读取失败' }
}, { immediate: true })
async function save() {
  if (!form.value || busy.value) return
  busy.value = true; status.value = ''; const current = sequence
  try {
    const interval_days = days.value.split(/[,，\s]+/).filter(Boolean).map(Number)
    const value = await props.request(`/api/v1/courses/${props.courseId}/practice-policy`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ due: form.value.due, variant: form.value.variant, new: form.value.new, taught: form.value.taught, interval_days, revision: form.value.revision }) }) as Policy
    if (current === sequence) { form.value = value; status.value = '推荐策略已保存，下一次推荐按新策略计算。' }
  } catch (e) { if (current === sequence) status.value = e instanceof Error ? e.message : '保存失败' }
  finally { busy.value = false }
}
</script>
<template>
  <section class="practice-policy"><button type="button" :aria-expanded="open" @click="open = !open">练习推荐策略 {{ open ? '⌃' : '⌄' }}</button><p v-if="status" role="status">{{ status }}</p><form v-if="open && form" @submit.prevent="save"><p>课程专属推荐比例（合计 {{ total }}%）</p><div class="policy-mix"><label>到期复习 %<input v-model.number="form.due" required type="number" min="0" max="100" /></label><label>薄弱点变式 %<input v-model.number="form.variant" required type="number" min="0" max="100" /></label><label>新题诊断 %<input v-model.number="form.new" required type="number" min="0" max="100" /></label><label>已授课巩固 %<input v-model.number="form.taught" required type="number" min="0" max="100" /></label></div><label>递增复习间隔（天）<input v-model="days" required placeholder="1, 3, 7, 14, 30" /></label><p>比例用于候选充足时的混排；不足会跨类别补充，不强推尚未到期的原错题。</p><button type="submit" :disabled="busy || total !== 100">{{ busy ? '保存中…' : '保存策略' }}</button></form></section>
</template>
<style scoped>
.practice-policy{border-top:1px solid #e1e8f5;margin-top:14px;padding-top:12px;font-size:12px}button{font-size:12px}form{display:grid;gap:10px;margin-top:12px}label{display:grid;gap:6px;min-width:0}input{min-width:0;width:100%;font:inherit}.policy-mix{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}p{color:#7788a3;line-height:1.8;margin:0}@media(max-width:600px){.policy-mix{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>

<script setup lang="ts">
import { ref } from 'vue'
import { dayKey, addDays, stamp, type Lesson } from '../timetable'
const props = defineProps<{ lesson: Lesson; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
defineEmits<{ choose: [item: Lesson] }>()
type Candidate = Lesson & { location_display?: string; resource_warnings?: string[] }
const start = ref(dayKey(props.lesson.session_date)), end = ref(addDays(start.value,6)), busy = ref(false), error = ref(''), notice = ref(''), items = ref<Candidate[]>([]), open = ref(false)
async function search() {
  if (busy.value) return
  busy.value = true; error.value = ''; items.value = []
  try { const result = await props.request(`/timetable/sessions/${props.lesson.id}/candidates`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ start_date: start.value, end_date: end.value }) }) as { items: Candidate[]; notice: string }; items.value = result.items; notice.value = result.notice }
  catch (e) { error.value = e instanceof Error ? e.message : '候选搜索失败' }
  finally { busy.value = false }
}
</script>
<template><section class="schedule-candidates"><button type="button" :aria-expanded="open" @click="open=!open">查找无冲突时间与教室 {{ open?'⌃':'⌄' }}</button><form v-if="open" @submit.prevent="search"><div class="candidate-window"><label>起始日期<input v-model="start" type="date" required /></label><label>结束日期<input v-model="end" :min="start" :max="addDays(start,13)" type="date" required /></label></div><button type="submit" :disabled="busy">{{ busy?'正在检查时间、学生与场地…':'查询候选安排' }}</button><p v-if="error" role="alert">{{ error }}</p><p v-if="notice">{{ notice }}</p><button v-for="row in items" :key="row.session_date+row.location" type="button" class="candidate-option" @click="$emit('choose',row)"><strong>{{ stamp(row.session_date) }}</strong><span>{{ row.location_display || row.location }} · {{ row.duration_minutes }} 分钟</span><small v-for="(warning,j) in row.resource_warnings || []" :key="j">提醒：{{ warning }}</small><b>选入申请 / 调整表单 ↗</b></button></form></section></template>
<style scoped>.schedule-candidates{border-top:1px solid #e1e8f4;margin-top:14px;padding-top:12px;font-size:12px}button{font-size:12px}form{display:grid;gap:10px;margin-top:10px}.candidate-window{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}label{display:grid;gap:6px;min-width:0}input{width:100%;min-width:0;font:inherit}.candidate-option{display:grid;gap:5px;text-align:left;border:1px solid #dae5f6;background:#f6f9ff;padding:12px;border-radius:10px}.candidate-option span,p{color:#7586a1;line-height:1.7}.candidate-option b{font-size:11px;color:#4d6fbe}[role=alert]{color:#ad4c38}@media(max-width:360px){.candidate-window{grid-template-columns:1fr}}</style>

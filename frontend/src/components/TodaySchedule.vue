<script setup lang="ts">
import { computed, ref } from 'vue'
import { dayKey, clock, lessonEnd, timeState } from '../timetable'
type Session = { id: string; course_id: string; title: string; session_date: string; duration_minutes: number; location: string | null; schedule_status?: string }
const props = defineProps<{ sessions: Session[]; courses: { id: string; title: string }[]; now: number; busy: boolean; error: string }>()
const emit = defineEmits<{ session: [id: string]; schedule: [] }>()
const endedOpen = ref(false)
const sorted = computed(() => [...props.sessions].sort((a,b) => Date.parse(a.session_date)-Date.parse(b.session_date)))
const today = computed(() => sorted.value.filter(x => dayKey(x.session_date) === dayKey(props.now) || (dayKey(x.session_date) < dayKey(props.now) && dayKey(lessonEnd(x)) === dayKey(props.now) && Date.parse(lessonEnd(x)) > Date.parse(`${dayKey(props.now)}T00:00:00+08:00`))))
const current = computed(() => today.value.filter(x => x.schedule_status !== 'cancelled' && Date.parse(lessonEnd(x)) > props.now))
const ended = computed(() => today.value.filter(x => !current.value.includes(x)))
const next = computed(() => sorted.value.find(x => x.schedule_status !== 'cancelled' && Date.parse(x.session_date) > props.now))
const visible = computed(() => current.value.length ? current.value.slice(0,3) : next.value ? [next.value] : [])
const title = (id: string) => props.courses.find(x => x.id === id)?.title || '课程'
</script>
<template>
  <section class="today-card" aria-label="今日课程">
    <header><div><small>TODAY · {{ dayKey(now).slice(5).replace('-', ' / ') }}</small><h2>今日课程</h2></div><button type="button" @click="emit('schedule')">完整课表 ›</button></header>
    <p v-if="!busy && !error && !current.length" class="quiet">{{ next ? '今天剩余时间没有课程，下一次见面是…' : '今天没有后续课程，好好安排学习与休息。' }}</p>
    <button v-for="item in visible" :key="item.id" type="button" class="today-lesson" :class="{ live: timeState(item, now) === '正在上课' }" @click="emit('session', item.id)">
      <span class="today-time">{{ dayKey(item.session_date) !== dayKey(now) ? dayKey(item.session_date).slice(5) + ' · ' : '' }}{{ clock(item.session_date) }}—{{ clock(lessonEnd(item)) }} <b>{{ timeState(item, now) }}</b></span>
      <strong>{{ title(item.course_id) }}</strong><span>{{ item.title }}</span><small>{{ item.location || '地点待通知' }} <i>查看课次 ›</i></small>
    </button>
    <button v-if="current.length > 3" type="button" class="more" @click="emit('schedule')">还有 {{ current.length - 3 }} 节课，打开课表查看 ›</button>
    <template v-if="ended.length"><button type="button" class="more" :aria-expanded="endedOpen" @click="endedOpen = !endedOpen">今日已结束 / 停课 {{ ended.length }} 节 {{ endedOpen ? '⌃' : '⌄' }}</button><div v-if="endedOpen"><button v-for="item in ended" :key="item.id" type="button" class="ended" @click="emit('session', item.id)"><span>{{ clock(item.session_date) }} · {{ title(item.course_id) }}</span><small>{{ timeState(item, now) }} ›</small></button></div></template>
  </section>
</template>
<style scoped>
.today-card{background:white;border:1px solid #e1e8f2;border-radius:18px;min-width:0;padding:22px}.today-card header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}.today-card header small{color:#6684a7;font-size:10px;letter-spacing:.1em}.today-card h2{font-size:19px;margin:5px 0 0;color:#203857}.today-card header button,.more{background:transparent;color:#386baf;font-size:12px;padding:8px 0}.today-lesson{display:grid;width:100%;gap:8px;text-align:left;background:#f4f7fc;border:1px solid #e3eaf4;border-left:4px solid #79a0dc;color:#304965;padding:16px;margin:10px 0;border-radius:12px}.today-lesson.live{background:#edf8f4;border-left-color:#299875}.today-time{font-size:12px;color:#51739d;display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between}.today-time b{font-size:10px}.today-lesson strong{font-size:14px}.today-lesson>span:not(.today-time),.today-lesson small{font-size:12px;font-weight:400}.today-lesson small{display:flex;justify-content:space-between;color:#7a8da4;gap:8px}.today-lesson i{font-style:normal;flex:none}.quiet{font-size:12px;color:#7b8fa7;line-height:1.8}.ended{background:transparent;color:#7b8fa7;display:flex;gap:12px;justify-content:space-between;text-align:left;width:100%;padding:12px 0;font-size:12px}.ended small{flex:none}button:focus-visible{outline:3px solid #aac8ed;outline-offset:3px}@media(max-width:600px){.today-card{padding:16px}.today-card h2{font-size:17px}.today-lesson{padding:13px}}
</style>

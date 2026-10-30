<script setup lang="ts">
defineProps<{ previous: string; proposed: string; busy: boolean }>()
defineEmits<{ confirm: []; cancel: [] }>()
</script>
<template>
  <section class="feedback-replace" aria-label="替换批改评语确认">
    <header><strong>批改框已有评语，是否替换？</strong><small>只替换未保存编辑内容，不改变成绩。</small></header>
    <div><article><b>现有评语</b><p>{{ previous }}</p></article><article><b>本次整理</b><p>{{ proposed }}</p></article></div>
    <footer><button type="button" :disabled="busy" @click="$emit('cancel')">保留现有评语</button><button type="button" :disabled="busy" @click="$emit('confirm')">替换为整理评语</button></footer>
  </section>
</template>
<style scoped>
.feedback-replace{background:#f3f7ff;border:1px solid #cbdcf3;border-radius:12px;margin:16px 0;padding:16px}.feedback-replace header{display:grid;gap:7px}.feedback-replace strong{color:#405c86;font-size:13px}.feedback-replace small{color:#7289ab;font-size:11px}.feedback-replace>div{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-top:14px}.feedback-replace article{background:white;border:1px solid #dee8f5;border-radius:8px;padding:12px}.feedback-replace b{color:#667fa2;font-size:11px}.feedback-replace p{color:#526d93;font-size:12px;line-height:1.85;margin:8px 0 0;white-space:pre-wrap}.feedback-replace footer{display:flex;flex-wrap:wrap;gap:9px;justify-content:flex-end;margin-top:13px}.feedback-replace button{background:white;border:1px solid #d4e1f2;color:#617da5;font-size:12px;padding:9px 13px}.feedback-replace button:last-child{background:#5278b6;color:white}button:disabled{opacity:.5}
</style>

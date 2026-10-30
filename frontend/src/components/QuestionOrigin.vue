<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
const props=defineProps<{ questionId:string; request:(path:string,options?:RequestInit)=>Promise<unknown> }>()
type Source={title:string;spans:{page_number:number;quote:string}[];original_answer_origin?:string}
const source=ref<Source|null>(null),error=ref(''),loading=ref(false)
const controller=new AbortController()
async function load(){loading.value=true;error.value='';try{source.value=await props.request(`/api/v1/questions/${props.questionId}/source`,{signal:controller.signal}) as Source|null}catch(e){if(!controller.signal.aborted)error.value=e instanceof Error?e.message:'出处暂不可读'}finally{loading.value=false}}
onMounted(load);onBeforeUnmount(()=>controller.abort())
</script>
<template><section class="question-origin"><p v-if="loading" role="status">正在读取题目出处…</p><p v-if="error" role="alert">{{ error }} <button type="button" @click="load">重试</button></p><details v-if="source"><summary>资料出处 · {{ source.title }}</summary><p>{{ source.original_answer_origin==='missing'?'原文未提供答案，当前参考答案由教师核对补充。':'题目从资料选编，当前答案与解析以教师核对内容为准。' }}</p><article v-for="(span,i) in source.spans" :key="i"><strong>第 {{ span.page_number }} 页原文</strong><pre>{{ span.quote }}</pre></article></details></section></template>
<style scoped>.question-origin{font-size:12px;color:#6f83a0;margin-block:14px}.question-origin details{border:1px solid #e0e8f5;border-radius:12px;padding:13px}.question-origin summary{font-weight:600;color:#526e9e;cursor:pointer}.question-origin pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:240px;overflow:auto;font:inherit;background:#f6f9ff;border-radius:8px;padding:12px}.question-origin article{margin-top:12px}</style>

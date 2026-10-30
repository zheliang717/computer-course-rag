<script setup lang="ts">
import {ref} from 'vue'
import PagedList from './PagedList.vue'
type Annotation={id:string;answer_quote:string;category:string;comment:string;source_index:number|null}
const props=defineProps<{historyId:string;request:(path:string,options?:RequestInit)=>Promise<unknown>}>()
const open=ref(false)
const labels:Record<string,string>={factual:'知识点',calculation:'推演与计算',citation:'引用支撑',unclear:'讲解表达',other:'其他问题'}
const load=(page:number,size:number)=>props.request(`/api/v1/question-reviews/${props.historyId}/annotations?page=${page}&page_size=${size}`) as Promise<{items:Annotation[];total:number;page:number;page_size:number}>
</script>
<template><section class="feedback-review"><button type="button" :aria-expanded="open" @click="open=!open">查看定位反馈 {{open?'⌃':'⌄'}}</button><PagedList v-if="open" :items="[] as Annotation[]" :load-page="load" :scope="historyId" :page-size="3" label="学生定位反馈" v-slot="{items,total,loading}"><article v-for="item in items" :key="item.id"><strong>{{labels[item.category]}}<small v-if="item.source_index"> · 资料 {{item.source_index}}</small></strong><blockquote>{{item.answer_quote}}</blockquote><p>{{item.comment}}</p></article><p v-if="!loading&&!total">暂无定位反馈。</p></PagedList><small v-if="open">请结合原文核对，并通过下方审核意见或修订答案回复；学生可在“我的反馈”回看回答整体审核结果。</small></section></template>
<style scoped>.feedback-review{border:1px solid #dce6f5;background:#f7faff;border-radius:12px;padding:12px;margin-block:12px;font-size:12px}article{border-bottom:1px solid #e0e7f3;padding:10px 0}blockquote{margin:8px 0;padding-left:10px;border-left:3px solid #7893d0;white-space:pre-wrap;overflow-wrap:anywhere}p,small{line-height:1.8;color:#7386a4}button{font-size:12px}small{display:block;margin-top:8px}</style>

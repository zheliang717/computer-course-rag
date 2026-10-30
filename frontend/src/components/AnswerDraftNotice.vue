<script setup lang="ts">
import { ref } from 'vue'
import type { AnswerDraft } from '../useAnswerDraft'
defineProps<{ savedAt: string; restored: boolean; pending: boolean; error: string; previousVersion: AnswerDraft | null; otherPage: AnswerDraft | null }>()
const emit = defineEmits<{ discard: []; retry: []; overwrite: []; restoreOther: [] }>()
const confirmDiscard = ref(false)
function time(value: string) { return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
</script>

<template>
  <section class="answer-draft-notice" :class="{ warning: error }" aria-label="作答草稿">
    <div class="answer-draft-summary">
      <p role="status" aria-live="polite"><strong>{{ error ? '草稿需要处理' : pending ? '正在暂存…' : restored ? '已恢复本机草稿' : savedAt ? '草稿已暂存' : '填写后自动暂存' }}</strong><span>{{ error || (savedAt ? `${time(savedAt)} · 尚未提交` : '仅保存在当前浏览器，不代表已完成作业或练习') }}</span></p>
      <button v-if="error && !otherPage" type="button" @click="emit('retry')">重试暂存</button>
      <button v-if="savedAt && !error && !confirmDiscard" class="ghost-button" type="button" @click="confirmDiscard = true">清空草稿</button>
    </div>
    <div v-if="confirmDiscard" class="answer-draft-confirm"><span>清空当前版本的草稿和已填答案？此操作不会撤回已提交的记录。</span><button type="button" @click="confirmDiscard = false">继续填写</button><button type="button" class="danger-soft" @click="emit('discard'); confirmDiscard = false">确认清空</button></div>
    <div v-if="otherPage" class="answer-draft-confirm"><span>下方可查看另一页面的版本。选择后会替换其中一份草稿，请先复制需要保留的内容。</span><button type="button" @click="emit('overwrite')">保留本页答案并暂存</button><button type="button" @click="emit('restoreOther')">使用另一页的草稿</button></div>
    <details v-for="(draft, index) in [otherPage, previousVersion].filter(Boolean)" :key="index" class="answer-draft-older"><summary>{{ draft === otherPage ? '查看另一页面的草稿' : '题目有更新：查看旧版本草稿（未自动填入）' }}</summary><template v-if="draft"><p>{{ time(draft.savedAt) }} · 可复制内容后重新核对当前题目</p><article v-for="question in draft.questions" :key="question.id"><strong>{{ question.stem }}</strong><pre>{{ Array.isArray(draft.answers[question.id]) ? (draft.answers[question.id] as string[]).join('\n') : draft.answers[question.id] || '未填写' }}</pre></article></template></details>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
import type { CatalogCourse, CourseRecord } from '../courseCatalog'

const props = defineProps<{
  request: (path: string, options?: RequestInit) => Promise<unknown>
  revision: number; focus: 'all' | 'missing'; focusRevision: number
}>()
const emit = defineEmits<{ select: [course: CourseRecord] }>()
type Page<T> = { items: T[]; total: number; page: number; page_size: number }
const keyword = ref('')
const appliedKeyword = ref('')
const status = ref('all')
const materials = ref('all')
const queryRevision = ref(0)
const directory = ref<HTMLElement | null>(null)
const scope = computed(() => JSON.stringify([appliedKeyword.value, status.value, materials.value, queryRevision.value]))
const refreshItems = computed<CatalogCourse[]>(() => { void props.revision; return [] })
const controller = new AbortController()
const loadPage = (page: number, pageSize: number) => props.request(`/api/v1/course-catalog?${new URLSearchParams({
  page: String(page), page_size: String(pageSize), keyword: appliedKeyword.value,
  course_status: status.value, materials: materials.value,
})}`, { signal: controller.signal }) as Promise<Page<CatalogCourse>>
function search() { appliedKeyword.value = keyword.value.trim(); queryRevision.value += 1 }
function reset() { keyword.value = ''; appliedKeyword.value = ''; status.value = 'all'; materials.value = 'all'; queryRevision.value += 1 }
watch(() => props.focusRevision, async () => {
  reset()
  if (props.focus === 'missing') { status.value = 'published'; materials.value = 'missing' }
  await nextTick()
  if (props.focus === 'missing') directory.value?.scrollIntoView({ block: 'start' })
}, { immediate: true })
onBeforeUnmount(() => controller.abort())
</script>

<template>
  <section ref="directory" class="course-directory" aria-label="课程查询">
    <form class="directory-toolbar" @submit.prevent="search">
      <label class="directory-keyword">搜索课程<input v-model="keyword" maxlength="100" type="search" placeholder="课程名称、代码或学期" /></label>
      <label>课程状态<select v-model="status"><option value="all">全部状态</option><option value="published">已发布</option><option value="draft">草稿</option><option value="archived">已归档</option></select></label>
      <label>资料状态<select v-model="materials"><option value="all">全部资料状态</option><option value="available">有已发布资料</option><option value="missing">缺少已发布资料</option></select></label>
      <div class="directory-filter-actions"><button type="submit">搜索</button><button type="button" class="ghost-button" @click="reset">重置</button></div>
    </form>
    <p v-if="status === 'published' && materials === 'missing'" class="directory-scope-note" role="status">正在查看缺少已发布资料的已发布课程。打开课程详情可核对并管理资料绑定。</p>
    <PagedList :items="refreshItems" :scope="scope" :page-size="6" :load-page="loadPage" label="课程" v-slot="{ items, loading, error }">
      <div class="course-card-grid">
        <button v-for="course in items" :key="course.id" type="button" class="course-card course-directory-card" @click="emit('select', course)">
          <span class="course-card-cover" :style="course.cover_image_url ? { backgroundImage: `linear-gradient(135deg, rgba(20,29,51,.3), rgba(44,95,154,.65)), url(${course.cover_image_url})`, backgroundSize: 'cover' } : {}"><span>{{ course.code }}</span><strong>{{ course.title.slice(0, 1) }}</strong></span>
          <span class="course-card-body">
            <span class="status-badge" :class="`status-${course.status === 'published' ? 'ready' : 'pending'}`">{{ course.status === 'published' ? '已发布' : course.status === 'archived' ? '已归档' : '草稿' }}</span>
            <strong class="directory-course-title">{{ course.title }}</strong><span class="directory-course-copy">{{ course.semester || '学期待设置' }}<br />{{ course.teacher_name || '教师待安排' }}</span>
            <span class="course-material-indicator" :class="{ 'is-missing': !course.ready_document_count }">{{ course.ready_document_count ? `${course.ready_document_count} 份已发布资料` : course.knowledge_base_count ? `已绑定 ${course.knowledge_base_count} 个资料库 · 暂无已发布资料` : '尚未绑定资料库' }}</span>
            <span class="directory-course-footer"><span>{{ course.section_count }} 章节 · {{ course.student_count }} 名学习者</span><span>查看详情 ›</span></span>
          </span>
        </button>
      </div>
      <div v-if="!loading && !error && !items.length" class="directory-empty"><strong>没有符合条件的课程</strong><p>试试其他关键词，或清除筛选查看全部可访问课程。</p><button type="button" class="ghost-button" @click="reset">清除筛选</button></div>
    </PagedList>
  </section>
</template>

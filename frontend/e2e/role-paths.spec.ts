import { expect, test, type Page } from '@playwright/test'
import { execFileSync as runProcess } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { mockAnswer } from './mock-answer'
import { fileURLToPath } from 'node:url'

const authTokens = new Map<string, string>()
const apiTokens = new Map<string, string>()

async function respectReadBudget(page:Page,token:string) {
  const response=await page.request.get('/api/v1/auth/me',{headers:{Authorization:'Bearer '+token}})
  if(response.status()===429 || Number(response.headers()['x-ratelimit-remaining']||300)<160) {
    // Human workflow checks must not become a burst/load test or weaken limits.
    test.setTimeout(test.info().timeout+65_000)
    await page.waitForTimeout(30_000)
    await page.waitForTimeout(30_000)
    await page.waitForTimeout(1_000)
  }
}

const isolatedURL = process.env.E2E_BASE_URL!
// Old fixtures used the compose service/database names; translate only after a
// strict opt-in. This also protects cleanup/fault-injection helpers.
function execFileSync(command: string, args: string[], options: any) {
  if (isolatedURL !== 'http://127.0.0.1:18086' || process.env.E2E_DATABASE !== 'rag_today_dev_20261028') {
    throw new Error('Refusing SQL outside the isolated browser-test copy')
  }
  if (command !== 'docker' || args.slice(0, 5).join(' ') !== 'compose exec -T postgres psql') {
    throw new Error('Unexpected test process')
  }
  const db = args.indexOf('-d')
  if (db < 0 || args[db + 1] !== 'rag') throw new Error('Unexpected database arguments')
  const translated = [...args]; translated[db + 1] = process.env.E2E_DATABASE!
  return runProcess(command, translated, options)
}

async function apiToken(page: Page, username: string, password: string): Promise<string> {
  const cached = apiTokens.get(username)
  if (cached) { await respectReadBudget(page,cached); return cached }
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await page.request.post('/api/v1/auth/login', { data: { username, password } })
    if (response.status() === 429) {
      if (attempt === 1) throw new Error(`${username} 的接口登录在限流等待后仍未恢复`)
      const retryAfter = Number.parseInt(response.headers()['retry-after'] ?? '60', 10)
      test.setTimeout(90_000)
      await page.waitForTimeout((Math.max(1, Math.min(60, Number.isFinite(retryAfter) ? retryAfter : 60)) + 1) * 1000)
      continue
    }
    expect(response.status()).toBe(200)
    const token = (await response.json()).access_token as string
    if (!token) throw new Error(`${username} 的接口登录未返回令牌`)
    apiTokens.set(username, token)
    await respectReadBudget(page,token)
    return token
  }
  throw new Error(`${username} 的接口登录未完成`)
}

async function login(page: Page, username: string, password: string) {
  if (username==='student') username=test.info().project.name==='edge-desktop'?'student02':test.info().project.name==='chrome-mobile'?'student03':'student'
  const token=await apiToken(page,username,password)
  // Login-form interactions are covered by the pagination/CRUD suites. These
  // workflow tests start with the announcement already acknowledged.
  const owner=JSON.parse(Buffer.from(token.split('.')[0],'base64url').toString()).sub
  await page.addInitScript(({token,owner})=>{
    localStorage.setItem('rag_token',token)
    localStorage.setItem('rag_update_notice:'+owner,'2026-10-29-zhixue-assistant')
  },{token,owner})
  await page.goto('/')
  await expect(page.getByRole('navigation',{name:'平台导航'})).toBeVisible()
}

async function readStreamAnswer(response: any, page: Page) {
  const sent=response.request().postDataJSON()
  const authorization=response.request().headers()['authorization']
  for(let attempt=0;attempt<20;attempt++){
    const receipt=await page.request.get('/api/v1/answer-requests/'+sent.request_id,{headers:{Authorization:authorization}})
    expect(receipt.status()).toBe(200)
    const value=await receipt.json()
    if(value.status==='completed')return value.answer
    if(value.status!=='in_progress')throw new Error(value.message)
    await page.waitForTimeout(100)
  }
  throw new Error('Answer receipt did not complete')
}

async function apiGetList(page: Page, url: string, headers: Record<string, string>): Promise<any[]> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await page.request.get(url, { headers })
    if (response.status() === 429 && attempt === 0) {
      const retryAfter = Number.parseInt(response.headers()['retry-after'] ?? '60', 10)
      test.setTimeout(90_000)
      await page.waitForTimeout((Math.max(1, Math.min(60, Number.isFinite(retryAfter) ? retryAfter : 60)) + 1) * 1000)
      continue
    }
    expect(response.status(), `${url} 应返回列表`).toBe(200)
    const data = await response.json()
    expect(Array.isArray(data), `${url} 应返回列表而非错误对象`).toBeTruthy()
    return data
  }
  throw new Error(`${url} 在限流等待后仍未返回列表`)
}

function navigation(page: Page) {
  return page.getByRole('navigation', { name: '平台导航' })
}

async function expectUsableViewport(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow, '页面不应出现横向溢出').toBeLessThanOrEqual(2)
  await expect(page.getByText('请求过于频繁，请稍后重试。')).toHaveCount(0)
}

function cleanReviewFixture(assignmentId: string | null, draftId: string | null, title: string) {
  if (!assignmentId && !draftId) return
  const validId = (value: string | null) => !value || /^[0-9a-f-]{36}$/i.test(value)
  if (!validId(assignmentId) || !validId(draftId) || !/^讲评页面验收-[0-9a-f]{8}$/.test(title)) {
    throw new Error('临时讲评记录标识不符合清理范围，停止自动清理')
  }
  const assignmentSql = assignmentId
    ? `DELETE FROM assignments WHERE id = '${assignmentId}' AND title = '${title}';` : ''
  const draftSql = draftId
    ? `DELETE FROM teaching_drafts WHERE id = '${draftId}' AND title = '${title} · 作业讲评';` : ''
  const auditSql = `DELETE FROM audit_logs WHERE resource_id IN ('${assignmentId ?? ''}', '${draftId ?? ''}');`
  execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
    '-U', 'rag', '-d', 'rag', '-c', `BEGIN; ${assignmentSql} ${draftSql} ${auditSql} COMMIT;`],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' })
}

function cleanManualGradeFixture(assignmentId: string | null, questionId: string | null, title: string) {
  if (!assignmentId && !questionId) return
  const validId = (value: string | null) => !value || /^[0-9a-f-]{36}$/i.test(value)
  if (!validId(assignmentId) || !validId(questionId) || !/^人工批改验收-[0-9a-f]{8}$/.test(title)) {
    throw new Error('临时人工批改记录标识不符合清理范围，停止自动清理')
  }
  const assignmentSql = assignmentId
    ? `DELETE FROM assignments WHERE id = '${assignmentId}' AND title = '${title}';` : ''
  const gradeAuditSql = assignmentId
    ? `DELETE FROM audit_logs WHERE action = 'grade' AND resource_type = 'submission'
       AND resource_id IN (SELECT id::text FROM assignment_submissions WHERE assignment_id = '${assignmentId}')
       AND EXISTS (SELECT 1 FROM assignments WHERE id = '${assignmentId}' AND title = '${title}');` : ''
  const questionSql = questionId
    ? `DELETE FROM question_bank_items WHERE id = '${questionId}' AND stem LIKE '${title}%';` : ''
  const auditSql = `DELETE FROM audit_logs WHERE resource_id IN ('${assignmentId ?? ''}', '${questionId ?? ''}');`
  execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
    '-U', 'rag', '-d', 'rag', '-c', `BEGIN; ${gradeAuditSql} ${assignmentSql} ${questionSql} ${auditSql} COMMIT;`],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' })
}

function gradeAuditCount(assignmentId: string, title: string): number {
  if (!/^[0-9a-f-]{36}$/i.test(assignmentId) || !/^人工批改验收-[0-9a-f]{8}$/.test(title)) {
    throw new Error('临时评分审计查询范围不合法')
  }
  const sql = `SELECT count(*) FROM audit_logs log
    JOIN assignment_submissions submission ON log.resource_id = submission.id::text
    JOIN assignments assignment ON assignment.id = submission.assignment_id
    WHERE assignment.id = '${assignmentId}' AND assignment.title = '${title}'
    AND log.action = 'grade' AND log.resource_type = 'submission'
    AND (log.detail->>'score')::numeric = 8;`
  const output = execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql',
    '-U', 'rag', '-d', 'rag', '-Atc', sql],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' }).toString().trim()
  return Number.parseInt(output, 10)
}

function cleanLateFixture(assignmentId: string | null, questionId: string | null,
  requestId: string | null, title: string) {
  if (!assignmentId && !questionId) return
  const validId = (value: string | null) => !value || /^[0-9a-f-]{36}$/i.test(value)
  if (!validId(assignmentId) || !validId(questionId) || !validId(requestId)
    || !/^补交页面验收-[0-9a-f]{8}$/.test(title)) {
    throw new Error('临时补交记录标识不符合清理范围，停止自动清理')
  }
  const assignmentSql = assignmentId
    ? `DELETE FROM assignments WHERE id = '${assignmentId}' AND title = '${title}';` : ''
  const questionSql = questionId
    ? `DELETE FROM question_bank_items WHERE id = '${questionId}' AND stem LIKE '${title}%';` : ''
  const auditSql = `DELETE FROM audit_logs WHERE resource_id IN ('${assignmentId ?? ''}', '${questionId ?? ''}', '${requestId ?? ''}');`
  execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
    '-U', 'rag', '-d', 'rag', '-c', `BEGIN; ${assignmentSql} ${questionSql} ${auditSql} COMMIT;`],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' })
}

function cleanIsolatedStudentFixture(userId: string | null, username: string) {
  if (!userId) return
  if (!/^[0-9a-f-]{36}$/i.test(userId) || !/^e2e_(late|card|assignment)_[0-9a-f]{8}$/.test(username)) {
    throw new Error('临时学生标识不符合清理范围，停止自动清理')
  }
  const sql = `BEGIN;
    DELETE FROM audit_logs WHERE resource_type = 'user' AND resource_id = '${userId}';
    DELETE FROM audit_logs WHERE resource_type = 'course' AND detail->>'user_id' = '${userId}';
    DELETE FROM login_attempts WHERE username = '${username}';
    DELETE FROM users WHERE id = '${userId}' AND username = '${username}' RETURNING id;
    COMMIT;`
  const result = execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
    '-U', 'rag', '-d', 'rag', '-Atc', sql],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' }).toString().trim().split(/\r?\n/)
  if (!result.includes(userId)) throw new Error('临时学生账号未按精确 ID 清理')
}

function cleanAdminActionFixture(userId: string | null, username: string) {
  if (!userId) return
  if (!/^[0-9a-f-]{36}$/i.test(userId) || !/^e2e_adminflow_[0-9a-f]{8}$/.test(username)) {
    throw new Error('临时管理员操作账号标识不符合清理范围，停止自动清理')
  }
  const sql = `BEGIN;
    DELETE FROM audit_logs WHERE resource_type = 'user' AND resource_id = '${userId}';
    DELETE FROM login_attempts WHERE username = '${username}';
    DELETE FROM users WHERE id = '${userId}' AND username = '${username}' RETURNING id;
    COMMIT;`
  const result = execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
    '-U', 'rag', '-d', 'rag', '-Atc', sql],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' }).toString().trim().split(/\r?\n/)
  if (!result.includes(userId)) throw new Error('临时管理员操作账号未按精确 ID 清理')
}

function expireIsolatedLateApproval(assignmentId: string, requestId: string, title: string) {
  if (!/^[0-9a-f-]{36}$/i.test(assignmentId) || !/^[0-9a-f-]{36}$/i.test(requestId)
    || !/^补交页面验收-[0-9a-f]{8}$/.test(title)) {
    throw new Error('临时补交记录标识不符合到期模拟范围')
  }
  const sql = `UPDATE late_submission_requests SET approved_until = now() - interval '1 hour'
    WHERE id = '${requestId}' AND assignment_id = '${assignmentId}' AND status = 'approved'
    AND EXISTS (SELECT 1 FROM assignments WHERE id = '${assignmentId}' AND title = '${title}') RETURNING id;`
  const changed = execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql',
    '-U', 'rag', '-d', 'rag', '-Atc', sql],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' }).toString().trim().split(/\r?\n/)
  if (!changed.includes(requestId) || !changed.includes('UPDATE 1')) {
    throw new Error('只允许将当前隔离补交批准设置为已过期')
  }
}

function cleanHistoryCardFixture(sessionId: string | null, conversationId: string | null,
  sessionTitle: string, question: string) {
  if (!sessionId && !conversationId) return
  const validId = (value: string | null) => !value || /^[0-9a-f-]{36}$/i.test(value)
  if (!validId(sessionId) || !validId(conversationId)
    || !/^历史卡片验收-[0-9a-f]{8}$/.test(sessionTitle)
    || question !== `这门课下一节课是什么？${sessionTitle}`) {
    throw new Error('临时历史卡片记录标识不符合清理范围，停止自动清理')
  }
  const historySql = conversationId
    ? `DELETE FROM question_records WHERE conversation_id = '${conversationId}' AND question = '${question}';
       DELETE FROM tutor_conversations WHERE id = '${conversationId}' AND title = '${question}'
       AND NOT EXISTS (SELECT 1 FROM question_records WHERE conversation_id = '${conversationId}');` : ''
  const sessionSql = sessionId
    ? `DELETE FROM course_sessions WHERE id = '${sessionId}' AND title = '${sessionTitle}';` : ''
  execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
    '-U', 'rag', '-d', 'rag', '-c', `BEGIN; ${historySql} ${sessionSql} COMMIT;`],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' })
}

function cleanAssignmentCardFixture(assignmentId: string | null, questionId: string | null,
  conversationId: string | null, title: string, question: string) {
  if (!assignmentId && !questionId && !conversationId) return
  const validId = (value: string | null) => !value || /^[0-9a-f-]{36}$/i.test(value)
  if (!validId(assignmentId) || !validId(questionId) || !validId(conversationId)
    || !/^作业卡片验收-[0-9a-f]{8}$/.test(title) || question !== `下一个作业是什么？${title}`) {
    throw new Error('临时作业卡片记录标识不符合清理范围，停止自动清理')
  }
  const historySql = conversationId
    ? `DELETE FROM question_records WHERE conversation_id = '${conversationId}' AND question = '${question}';
       DELETE FROM tutor_conversations WHERE id = '${conversationId}' AND title = '${question}'
       AND NOT EXISTS (SELECT 1 FROM question_records WHERE conversation_id = '${conversationId}');` : ''
  const assignmentSql = assignmentId
    ? `DELETE FROM assignments WHERE id = '${assignmentId}' AND title = '${title}';` : ''
  const questionSql = questionId
    ? `DELETE FROM question_bank_items WHERE id = '${questionId}' AND stem LIKE '${title}%';` : ''
  const auditSql = `DELETE FROM audit_logs WHERE resource_id IN ('${assignmentId ?? ''}', '${questionId ?? ''}');`
  execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
    '-U', 'rag', '-d', 'rag', '-c', `BEGIN; ${historySql} ${assignmentSql} ${questionSql} ${auditSql} COMMIT;`],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), stdio: 'pipe' })
}

test('学生：首页、课程详情、作业与 AI 助手入口', async ({ page }) => {
  await login(page, 'student', 'student123')
  await expect(navigation(page).getByRole('button', { name: '首页' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '分课程学习进度' })).toBeVisible()
  await navigation(page).getByRole('button', { name: '我的课程' }).click()
  await expect(page.locator('.course-card').first()).toBeVisible()
  await page.locator('.course-card').first().click()
  await expect(page.locator('dialog:has(nav[aria-label="课程详情栏目"])')).toBeVisible()
  await expect(page.locator('dialog:has(nav[aria-label="课程详情栏目"]) .course-facts')).toBeVisible()
  await page.locator('dialog:has(nav[aria-label="课程详情栏目"]) .detail-close').click()
  await navigation(page).getByRole('button', { name: '我的作业' }).click()
  await page.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
  await expect(page.getByRole('region',{name:'我的作业查询'})).toBeVisible()
  await page.locator('.task-directory-row').first().click()
  await expect(page.locator('.assignment-sheet').getByRole('heading').first()).toBeVisible()
  await page.locator('.assignment-sheet > header button').click()
  await navigation(page).getByRole('button', { name: 'AI 课程导师' }).click()
  await expect(page.getByRole('button', { name: '发送 ↗' })).toBeVisible()
  await expect(page.locator('.topbar-status')).toHaveCount(0)
  await expectUsableViewport(page)
})

test('学生：中文 HTTP 资料可从课程打开并核对来源与主题页', async ({ page }) => {
  await login(page, 'student04', 'student123')
  await navigation(page).getByRole('button', { name: '我的课程' }).click()
  await page.getByLabel('搜索课程').fill('计算机网络')
  await page.locator('.course-directory').getByRole('button',{name:'搜索',exact:true}).click()
  await page.locator('.course-card').filter({ hasText: '计算机网络' }).first().click()
  await page.getByRole('navigation',{name:'课程详情栏目'}).getByRole('button',{name:'资料与知识点'}).click()
  const material = page.locator('dialog:has(nav[aria-label="课程详情栏目"]) .course-detail-item')
    .filter({ hasText: 'MDN Web Docs：HTTP 概述（中文文字摘编）' })
  await expect(material).toBeVisible()
  await material.click()
  const preview = page.locator('dialog:has(.document-reading-page)')
  await expect(preview.getByRole('heading', { name: 'MDN Web Docs：HTTP 概述（中文文字摘编）' })).toBeVisible()
  await preview.getByRole('button',{name:'资料信息',exact:true}).click()
  await expect(preview.locator('.document-source-note')).toContainText('CC BY-SA 2.5')
  await expect(preview.locator('.document-source-note')).toContainText('本系统页码不是原文页码')
  await expect(preview.getByRole('link', { name: '查看来源' })).toHaveAttribute('href', /13bc56a75ee7f979f3ceb36913b4366a63b6ac48/)
  await expect(preview.getByRole('link', { name: '查看许可' })).toHaveAttribute('href', /^https:\/\/creativecommons\.org\//)
  await preview.getByRole('button',{name:'原文阅读',exact:true}).click()
  await preview.getByLabel('资料跳转页码').fill('4')
  await preview.getByRole('button',{name:'跳转',exact:true}).click()
  await expect(preview.locator('[data-document-page="4"]')).toContainText('无状态')
  await preview.getByLabel('资料跳转页码').fill('6')
  await preview.getByRole('button',{name:'跳转',exact:true}).click()
  await expect(preview.locator('[data-document-page="6"]')).toContainText('Mozilla 贡献者')
  await expectUsableViewport(page)
})

test('教师：教学课程、题库作业与 AI 教学助理', async ({ page }) => {
  await login(page, 'teacher', 'teacher123')
  await navigation(page).getByRole('button', { name: '教学课程' }).click()
  await expect(page.locator('.course-card').first()).toBeVisible()
  await navigation(page).getByRole('button', { name: '作业管理' }).click()
  await page.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
  await expect(page.getByRole('button', { name: '补交审批',exact:true })).toBeVisible()
  await page.locator('.task-directory-row').first().click()
  await page.locator('.assignment-sheet').getByRole('button',{name:'作业讲评',exact:true}).click()
  await expect(page.getByRole('heading', { name: '作业讲评' })).toBeVisible()
  await page.locator('.assignment-sheet > header button').click()
  await navigation(page).getByRole('button', { name: 'AI 教学助理' }).click()
  await expect(page.getByRole('button', { name: '发送 ↗' })).toBeVisible()
  await expect(page.locator('.topbar-status')).toHaveCount(0)
  await expectUsableViewport(page)
})

test('教师：讲评发布结果在审核弹层内可见', async ({ page }) => {
  const draftId = 'fef097ae-386b-4e63-a1c7-92e94a1966a1'
  const draft = {
    id: draftId, course_id: 'c197f257-b643-42fb-a4fb-fdd216a1f098', course_title: '数据结构',
    creator_id: 'aabbe061-736d-4250-a038-80399b7ff846', draft_type: 'review',
    title: '回归测试讲评草稿', content: '## 讲评\n\n教师已核对。', questions: [],
    source_context: { origin: 'assignment_review', assignment_id: 'c90d2dbe-8590-4be0-bbb1-6582c6b95f1c',
      submission_count: 1, graded_count: 1, pending_review_count: 0, average_percent: 80 },
    status: 'confirmed', confirmed_at: '2026-10-02T00:00:00Z',
    created_at: '2026-10-02T00:00:00Z', updated_at: '2026-10-02T00:00:00Z',
  }
  await page.route('**/api/v1/paged/drafts?*', (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const params = new URL(route.request().url()).searchParams
    const pageIndex = Number(params.get('page') ?? 1)
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      items: pageIndex === 1 ? [draft] : [], total: 1, page: pageIndex, page_size: Number(params.get('page_size') ?? 10),
    }) })
  })
  await page.route('**/api/v1/teaching-drafts/'+draftId, route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(draft)}))
  await login(page, 'teacher', 'teacher123')
  await navigation(page).getByRole('button', { name: '教学课程' }).click()
  await page.locator('.teaching-draft-list button').filter({ hasText: draft.title }).click()
  const sheet = page.locator('dialog:has(nav[aria-label="教学草稿视图"])')
  await expect(sheet.getByRole('heading', { name: draft.title })).toBeVisible()
  await page.route(`**/api/v1/teaching-drafts/${draftId}/publish-review`, (route) => route.fulfill({
    status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '提交或批改已变化，请重新生成讲评草稿。' }),
  }))
  await sheet.getByRole('button', { name: '发布讲评给已提交学生' }).click()
  await expect(sheet.getByRole('alert')).toContainText('提交或批改已变化')
  await page.unroute(`**/api/v1/teaching-drafts/${draftId}/publish-review`)
  await page.route(`**/api/v1/teaching-drafts/${draftId}/publish-review`, (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ ...draft, status: 'published' }),
  }))
  await sheet.getByRole('button', { name: '发布讲评给已提交学生' }).click()
  await expect(sheet.getByRole('status')).toContainText('作业讲评已发布')
  await expect(sheet.getByRole('button', { name: '发布讲评给已提交学生' })).toHaveCount(0)
  await expectUsableViewport(page)
})

test('教师：不勾选资料外发也能生成站内统计讲评提纲', async ({ page }) => {
  await page.route('**/api/v1/assignments/*/submissions', (route) => route.request().method() === 'GET'
    ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{
      id: '4fb2a282-5c19-4dc0-a820-e99aa94cc0c2', student_name: '测试学生',
      status: 'graded', score: 10, max_score: 10, answers: {}, submitted_at: '2026-10-02T00:00:00Z',
    }]) }) : route.continue())
  let sentPayload: { local_only?: boolean; confirm_external_analysis?: boolean } | null = null
  await page.route('**/api/v1/assignments/*/review-drafts', (route) => {
    sentPayload = route.request().postDataJSON()
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({
      id: 'c7d32744-aa9b-4f82-94d3-d3e1a78b869d',
      course_id: 'c197f257-b643-42fb-a4fb-fdd216a1f098', course_title: '数据结构',
      creator_id: 'aabbe061-736d-4250-a038-80399b7ff846', draft_type: 'review',
      title: '站内统计讲评提纲', content: '## 讲评提纲\n\n当前未使用在线模型。', questions: [],
      source_context: { origin: 'assignment_review', model: 'local-statistics',
        submission_count: 1, graded_count: 1, pending_review_count: 0, average_percent: 100 },
      status: 'draft', confirmed_at: null, created_at: '2026-10-02T00:00:00Z', updated_at: '2026-10-02T00:00:00Z',
    }) })
  })
  await login(page, 'teacher', 'teacher123')
  await navigation(page).getByRole('button', { name: '作业管理' }).click()
  await page.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
  await page.locator('.task-directory-row').first().click()
  const assignment = page.locator('.assignment-sheet')
  await assignment.getByRole('button',{name:'作业讲评',exact:true}).click()
  await expect(assignment.getByRole('button', { name: '仅用站内统计生成提纲' })).toBeEnabled()
  await assignment.getByRole('button', { name: '仅用站内统计生成提纲' }).click()
  await expect(page.locator('dialog:has(nav[aria-label="教学草稿视图"])')).toBeVisible()
  expect(sentPayload).toEqual({ local_only: true, confirm_external_analysis: false,include_student_answers:false })
  await expect(page.locator('dialog:has(nav[aria-label="教学草稿视图"])')).toContainText('站内统计提纲 · 未使用在线模型')
  await expect(page.locator('dialog:has(nav[aria-label="教学草稿视图"])').getByRole('status')).toContainText('未调用在线模型')
  await expectUsableViewport(page)
})

test('教师与学生：隔离作业讲评在真实页面发布并在新提交后失效', async ({ page, browser }) => {
  const title = `讲评页面验收-${randomUUID().slice(0, 8)}`
  let assignmentId: string | null = null
  let draftId: string | null = null
  const studentContext = await browser.newContext({ baseURL: isolatedURL })
  const studentPage = await studentContext.newPage()
  try {
    await login(page, 'teacher', 'teacher123')
    await login(studentPage, 'student', 'student123')
    const teacherToken = await page.evaluate(() => localStorage.getItem('rag_token'))
    const studentToken = await studentPage.evaluate(() => localStorage.getItem('rag_token'))
    if (!teacherToken || !studentToken) throw new Error('测试账号未取得访问令牌')
    const teacherHeaders = { Authorization: `Bearer ${teacherToken}` }
    const studentHeaders = { Authorization: `Bearer ${studentToken}` }
    const otherStudent = test.info().project.name === 'edge-desktop' ? 'student03' : 'student02'
    const otherHeaders = { Authorization: `Bearer ${await apiToken(page, otherStudent, 'student123')}` }
    const teacherCourses = await apiGetList(page, '/api/v1/courses', teacherHeaders)
    const studentCourses = await apiGetList(page, '/api/v1/courses', studentHeaders)
    const otherCourses = await apiGetList(page, '/api/v1/courses', otherHeaders)
    const questions = await apiGetList(page, '/api/v1/questions', teacherHeaders)
    const sharedIds = new Set(studentCourses.map((item: { id: string }) => item.id)
      .filter((id: string) => otherCourses.some((item: { id: string }) => item.id === id)))
    const course = teacherCourses.find((item: { id: string }) => sharedIds.has(item.id)
      && questions.some((question: { course_id: string; question_type: string }) =>
        question.course_id === item.id && question.question_type === 'single_choice'))
    if (!course) throw new Error('没有三账号共享且含单选题的演示课程')
    const question = questions.find((item: { course_id: string; question_type: string }) =>
      item.course_id === course.id && item.question_type === 'single_choice')
    const created = await page.request.post('/api/v1/assignments', { headers: teacherHeaders,
      data: { course_id: course.id, title, question_ids: [question.id], status: 'draft' } })
    expect(created.status()).toBe(201)
    assignmentId = (await created.json()).id as string
    const publishedAssignment = await page.request.patch(`/api/v1/assignments/${assignmentId}/status`, {
      headers: teacherHeaders, data: { status: 'published' },
    })
    expect(publishedAssignment.ok()).toBeTruthy()
    const answers = { [question.id]: question.correct_answer }
    const submitted = await page.request.post(`/api/v1/assignments/${assignmentId}/submit`, {
      headers: studentHeaders, data: { answers },
    })
    expect(submitted.ok()).toBeTruthy()
    expect((await submitted.json()).status).toBe('graded')

    await page.reload()
    await navigation(page).getByRole('button', { name: '作业管理' }).click()
  await page.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await page.getByLabel('查找作业').fill(title)
    await page.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await page.locator('.task-directory-row').filter({ hasText: title }).click()
    await page.locator('.assignment-sheet').getByRole('button',{name:'作业讲评',exact:true}).click()
    const draftResponse = page.waitForResponse((response) => response.url().includes(`/api/v1/assignments/${assignmentId}/review-drafts`)
      && response.request().method() === 'POST')
    await page.locator('.assignment-sheet').getByRole('button', { name: '仅用站内统计生成提纲' }).click()
    const createdDraft = await draftResponse
    expect(createdDraft.status()).toBe(201)
    draftId = (await createdDraft.json()).id as string
    const sheet = page.locator('dialog:has(nav[aria-label="教学草稿视图"])')
    await expect(sheet).toBeVisible()
    expect((await createdDraft.json()).source_context.model).toBe('local-statistics')
    await sheet.getByRole('button',{name:'流程与依据',exact:true}).click()
    await expect(sheet).toContainText('站内统计提纲 · 未使用在线模型')
    await sheet.getByRole('button',{name:'编辑内容',exact:true}).click()
    await sheet.getByRole('textbox', { name: '讲评正文（Markdown）' }).fill('## 教师讲评\n\n请复习本题的关键概念。')
    await sheet.getByRole('button', { name: '保存修改' }).click()
    await expect(sheet.getByRole('status')).toContainText('修改已保存')
    await sheet.getByRole('button', { name: '确认内容' }).click()
    await expect(sheet.getByRole('status')).toContainText('已经教师确认')
    await sheet.getByRole('button', { name: '发布讲评给已提交学生' }).click()
    await expect(sheet.getByRole('status')).toContainText('作业讲评已发布')

    await studentPage.reload()
    await navigation(studentPage).getByRole('button', { name: '我的作业' }).click()
  await studentPage.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await studentPage.getByLabel('查找作业').fill(title)
    await studentPage.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await studentPage.locator('.task-directory-row').filter({ hasText: title }).click()
    await expect(studentPage.locator('.assignment-sheet .assignment-review-result')).toContainText('请复习本题的关键概念')
    const secondSubmission = await page.request.post(`/api/v1/assignments/${assignmentId}/submit`, {
      headers: otherHeaders, data: { answers },
    })
    expect(secondSubmission.ok()).toBeTruthy()
    await studentPage.locator('.assignment-sheet > header button').click()
    await studentPage.getByLabel('查找作业').fill(title)
    await studentPage.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await studentPage.locator('.task-directory-row').filter({ hasText: title }).click()
    await expect(studentPage.locator('.assignment-sheet .assignment-review-result')).toHaveCount(0)
    await expectUsableViewport(page)
    await expectUsableViewport(studentPage)
  } finally {
    await studentContext.close()
    cleanReviewFixture(assignmentId, draftId, title)
  }
})

test('学生与教师：简答题待批改、最终成绩与评语按状态显示', async ({ page, browser }) => {
  const title = `人工批改验收-${randomUUID().slice(0, 8)}`
  let assignmentId: string | null = null
  let questionId: string | null = null
  const studentContext = await browser.newContext({ baseURL: isolatedURL })
  const studentPage = await studentContext.newPage()
  try {
    await login(page, 'teacher', 'teacher123')
    await login(studentPage, 'student', 'student123')
    const teacherToken = await page.evaluate(() => localStorage.getItem('rag_token'))
    const studentToken = await studentPage.evaluate(() => localStorage.getItem('rag_token'))
    if (!teacherToken || !studentToken) throw new Error('测试账号未取得访问令牌')
    const teacherHeaders = { Authorization: `Bearer ${teacherToken}` }
    const studentHeaders = { Authorization: `Bearer ${studentToken}` }
    const teacherCourses = await apiGetList(page, '/api/v1/courses', teacherHeaders)
    const studentCourses = await apiGetList(page, '/api/v1/courses', studentHeaders)
    const course = teacherCourses.find((item: { id: string; status: string }) => item.status === 'published'
      && studentCourses.some((studentCourse: { id: string }) => studentCourse.id === item.id))
    if (!course) throw new Error('没有师生共享的已发布课程')
    const createdQuestion = await page.request.post('/api/v1/questions', { headers: teacherHeaders, data: {
      course_id: course.id, question_type: 'short_answer', stem: `${title}：解释递归终止条件。`,
      options: [], correct_answer: '递归必须有基础情况。', explanation: '基础情况可防止无限递归。',
      knowledge_point: '递归',
    } })
    expect(createdQuestion.status()).toBe(201)
    questionId = (await createdQuestion.json()).id as string
    const createdAssignment = await page.request.post('/api/v1/assignments', { headers: teacherHeaders, data: {
      course_id: course.id, title, question_ids: [questionId], status: 'draft',
    } })
    expect(createdAssignment.status()).toBe(201)
    assignmentId = (await createdAssignment.json()).id as string
    const published = await page.request.patch(`/api/v1/assignments/${assignmentId}/status`, {
      headers: teacherHeaders, data: { status: 'published' },
    })
    expect(published.ok()).toBeTruthy()

    await studentPage.reload()
    await navigation(studentPage).getByRole('button', { name: '我的作业' }).click()
  await studentPage.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await studentPage.getByLabel('查找作业').fill(title)
    await studentPage.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await studentPage.locator('.task-directory-row').filter({ hasText: title }).click()
    const studentSheet = studentPage.locator('.assignment-sheet')
    await studentSheet.locator('.task-written-answer textarea').fill('到达基础情况时返回，不再递归调用。')
    await studentSheet.getByRole('button', { name: '检查并提交',exact:true }).click()
    await studentPage.getByRole('dialog',{name:'检查并提交作业',exact:true}).getByRole('button',{name:'确认提交',exact:true}).click()
    await expect(studentSheet.locator('.assignment-submission-state')).toContainText('已提交 · 待教师批改')
    await expect(studentSheet).toContainText('最终成绩与参考答案将在教师批改后显示')
    await expect(studentSheet.locator('.answer-review')).toHaveCount(0)
    await studentSheet.getByRole('button',{name:'查看我的作答'}).click()
    await expect(studentSheet.locator('.task-written-answer textarea')).toHaveValue('到达基础情况时返回，不再递归调用。')
    await expect(studentSheet.locator('.task-written-answer textarea')).toBeDisabled()
    await expect(studentSheet.getByRole('button', { name: '检查并提交',exact:true })).toHaveCount(0)
    await expect(studentPage.locator('.task-directory-row').filter({ hasText: title })).toContainText('待批改')
    const duplicate = await studentPage.request.post(`/api/v1/assignments/${assignmentId}/submit`, {
      headers: studentHeaders, data: { answers: { [questionId]: '重复提交' } },
    })
    expect(duplicate.status()).toBe(409)

    await page.reload()
    await navigation(page).getByRole('button', { name: '作业管理' }).click()
  await page.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await page.getByLabel('查找作业').fill(title)
    await page.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await page.locator('.task-directory-row').filter({ hasText: title }).click()
    const teacherSheet = page.locator('.assignment-sheet')
    await teacherSheet.getByRole('button',{name:'学生作答与批改',exact:true}).click()
    await expect(teacherSheet.locator('.grading-roster-list')).toContainText('待批改')
    if(!(await teacherSheet.locator('.grading-student-row').first().isVisible()))await teacherSheet.getByRole('button',{name:/选择学生/}).click()
    await teacherSheet.locator('.grading-student-row').first().click()
    await expect(teacherSheet.locator('.grading-saved-score')).toContainText('待批改')
    await teacherSheet.getByRole('spinbutton', { name: '最终成绩' }).fill('8')
    await teacherSheet.getByRole('textbox', { name: '教师评语' }).fill('思路正确，请补充一个具体例子。')
    await teacherSheet.getByRole('button', { name: '保存批改' }).click()
    await expect(teacherSheet.locator('.grading-roster-list')).toContainText('已批改')
    expect(gradeAuditCount(assignmentId, title)).toBe(1)

    await studentSheet.locator('header button').first().click()
    await studentPage.getByLabel('查找作业').fill(title)
    await studentPage.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await studentPage.locator('.task-directory-row').filter({ hasText: title }).click()
    await expect(studentSheet.locator('.assignment-submission-state')).toContainText('8/10')
    await expect(studentSheet.locator('.assignment-submission-state')).toContainText('思路正确，请补充一个具体例子。')
    await studentSheet.getByRole('button',{name:'查看我的作答'}).click()
    await studentSheet.getByText('查看参考答案与解析',{exact:true}).click()
    await expect(studentSheet.locator('.task-answer-explanation')).toContainText('递归必须有基础情况。')
    await expect(studentSheet.locator('.task-written-answer textarea')).toHaveValue('到达基础情况时返回，不再递归调用。')
    await expect(studentPage.locator('.task-directory-row').filter({ hasText: title })).toContainText('8/10')
    await expectUsableViewport(page)
    await expectUsableViewport(studentPage)
  } finally {
    await studentContext.close()
    cleanManualGradeFixture(assignmentId, questionId, title)
  }
})

test('学生与教师：补交批准过期后重新申请、审批并完成提交', async ({ page, browser }) => {
  const title = `补交页面验收-${randomUUID().slice(0, 8)}`
  const studentUsername = `e2e_late_${randomUUID().slice(0, 8)}`
  const studentPassword = `e2e-Late-${randomUUID()}`
  let assignmentId: string | null = null
  let questionId: string | null = null
  let requestId: string | null = null
  let studentId: string | null = null
  const studentContext = await browser.newContext({ baseURL: isolatedURL })
  const studentPage = await studentContext.newPage()
  try {
    await login(page, 'teacher', 'teacher123')
    const teacherToken = await page.evaluate(() => localStorage.getItem('rag_token'))
    if (!teacherToken) throw new Error('教师测试账号未取得访问令牌')
    const teacherHeaders = { Authorization: `Bearer ${teacherToken}` }
    const adminToken = await apiToken(page, 'admin', 'admin123')
    const createdStudent = await page.request.post('/api/v1/admin/users', {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: { username: studentUsername, display_name: '补交隔离测试学生', role: 'student', password: studentPassword },
    })
    expect(createdStudent.status()).toBe(201)
    studentId = (await createdStudent.json()).id as string
    const teacherCourses = await apiGetList(page, '/api/v1/courses', teacherHeaders)
    const course = teacherCourses.find((item: { id: string; status: string }) => item.status === 'published')
    if (!course) throw new Error('教师没有已发布的演示课程')
    const enrollment = await page.request.post(`/api/v1/courses/${course.id}/members`, {
      headers: teacherHeaders, data: { username: studentUsername },
    })
    expect(enrollment.status()).toBe(201)
    await login(studentPage, studentUsername, studentPassword)
    const questionCreated = await page.request.post('/api/v1/questions', { headers: teacherHeaders, data: {
      course_id: course.id, question_type: 'single_choice', stem: `${title}：1 + 1 等于多少？`,
      options: ['A. 2', 'B. 3'], correct_answer: 'A', explanation: '1 + 1 = 2。', knowledge_point: '基础运算',
    } })
    expect(questionCreated.status()).toBe(201)
    questionId = (await questionCreated.json()).id as string
    const created = await page.request.post('/api/v1/assignments', { headers: teacherHeaders, data: {
      course_id: course.id, title, question_ids: [questionId], status: 'draft',
      due_at: new Date(Date.now() - 86400000).toISOString(),
    } })
    expect(created.status()).toBe(201)
    assignmentId = (await created.json()).id as string
    const published = await page.request.patch(`/api/v1/assignments/${assignmentId}/status`, {
      headers: teacherHeaders, data: { status: 'published' },
    })
    expect(published.ok()).toBeTruthy()

    await studentPage.reload()
    await navigation(studentPage).getByRole('button', { name: '我的作业' }).click()
  await studentPage.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await studentPage.getByLabel('查找作业').fill(title)
    await studentPage.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await studentPage.locator('.task-directory-row').filter({ hasText: title }).click()
    const studentSheet = studentPage.locator('.assignment-sheet')
    await expect(studentSheet.locator('.late-request-box')).toContainText('作业已截止，请查看补交安排')
    await studentSheet.locator('.late-request-box textarea').fill('隔离页面验收：申请补交')
    const requestResponse = studentPage.waitForResponse((response) => response.url().includes(`/api/v1/assignments/${assignmentId}/late-requests`)
      && response.request().method() === 'POST')
    await studentSheet.getByRole('button', { name: '提交补交申请' }).click()
    const requested = await requestResponse
    expect(requested.status()).toBe(201)
    requestId = (await requested.json()).id as string
    await expect(studentSheet.locator('.late-request-box')).toContainText('补交申请等待教师审批')

    await page.reload()
    await navigation(page).getByRole('button', { name: '作业管理' }).click()
  await page.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await page.getByRole('button',{name:'补交审批',exact:true}).click()
    const approval = page.locator('.late-approval-panel .late-request-row').filter({ hasText: title })
    await expect(approval).toContainText('待审批')
    await approval.getByRole('button', { name: '批准 7 天' }).click()
    await expect(approval).toContainText('已批准')

    await studentPage.reload()
    await navigation(studentPage).getByRole('button', { name: '我的作业' }).click()
  await studentPage.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await studentPage.getByLabel('查找作业').fill(title)
    await studentPage.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await studentPage.locator('.task-directory-row').filter({ hasText: title }).click()
    await expect(studentSheet.locator('.late-approved-note')).toContainText('补交已批准')
    expireIsolatedLateApproval(assignmentId, requestId, title)

    await studentPage.reload()
    await navigation(studentPage).getByRole('button', { name: '我的作业' }).click()
  await studentPage.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await studentPage.getByLabel('查找作业').fill(title)
    await studentPage.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await studentPage.locator('.task-directory-row').filter({ hasText: title }).click()
    await expect(studentSheet.locator('.late-approved-note')).toHaveCount(0)
    await expect(studentSheet.locator('.late-request-box')).toContainText('补交批准已过期')
    await expect(studentSheet.getByRole('button', { name: '提交获批补交' })).toHaveCount(0)
    await studentSheet.locator('.late-request-box textarea').fill('隔离页面验收：批准已过期，请重新审批')
    const renewedResponse = studentPage.waitForResponse((response) => response.url().includes(`/api/v1/assignments/${assignmentId}/late-requests`)
      && response.request().method() === 'POST')
    await studentSheet.getByRole('button', { name: '提交补交申请' }).click()
    const renewed = await renewedResponse
    expect(renewed.status()).toBe(201)
    expect((await renewed.json()).id).toBe(requestId)
    await expect(studentSheet.locator('.late-request-box')).toContainText('补交申请等待教师审批')

    await page.reload()
    await navigation(page).getByRole('button', { name: '作业管理' }).click()
  await page.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    const renewedApproval = page.locator('.late-approval-panel .late-request-row').filter({ hasText: title })
    await page.getByRole('button',{name:'补交审批',exact:true}).click()
    await expect(renewedApproval).toContainText('待审批')
    await renewedApproval.getByRole('button', { name: '批准 7 天' }).click()
    await expect(renewedApproval).toContainText('已批准')

    await studentPage.reload()
    await navigation(studentPage).getByRole('button', { name: '我的作业' }).click()
  await studentPage.getByRole('navigation',{name:'作业状态'}).getByRole('button',{name:/^全部/}).click()
    await studentPage.getByLabel('查找作业').fill(title)
    await studentPage.locator('.task-directory-filters').getByRole('button',{name:'查询',exact:true}).click()
    await studentPage.locator('.task-directory-row').filter({ hasText: title }).click()
    await expect(studentSheet.locator('.late-approved-note')).toContainText('补交已批准')
    await studentSheet.getByRole('radio', { name: 'A. 2' }).check()
    await studentSheet.getByRole('button', { name: '检查并提交',exact:true }).click()
    await studentPage.getByRole('dialog',{name:'检查并提交作业',exact:true}).getByRole('button',{name:'确认提交',exact:true}).click()
    await expect(studentSheet.locator('.assignment-submission-state')).toContainText('10/10')
    await expect(studentSheet.locator('.late-request-box')).toHaveCount(0)
    await expectUsableViewport(page)
    await expectUsableViewport(studentPage)
  } finally {
    await studentContext.close()
    try {
      cleanLateFixture(assignmentId, questionId, requestId, title)
    } finally {
      cleanIsolatedStudentFixture(studentId, studentUsername)
    }
  }
})

test('学生：课表操作卡片刷新后从助手历史恢复并打开课程', async ({ page, browser }) => {
  const sessionTitle = `历史卡片验收-${randomUUID().slice(0, 8)}`
  const question = `这门课下一节课是什么？${sessionTitle}`
  const studentUsername = `e2e_card_${randomUUID().slice(0, 8)}`
  const studentPassword = `e2e-Card-${randomUUID()}`
  let sessionId: string | null = null
  let conversationId: string | null = null
  let studentId: string | null = null
  const teacherContext = await browser.newContext({ baseURL: isolatedURL })
  const teacherPage = await teacherContext.newPage()
  try {
    await login(teacherPage, 'teacher', 'teacher123')
    const teacherToken = await teacherPage.evaluate(() => localStorage.getItem('rag_token'))
    if (!teacherToken) throw new Error('教师测试账号未取得访问令牌')
    const teacherHeaders = { Authorization: `Bearer ${teacherToken}` }
    const adminToken = await apiToken(teacherPage, 'admin', 'admin123')
    const createdStudent = await teacherPage.request.post('/api/v1/admin/users', {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: { username: studentUsername, display_name: '卡片权限隔离测试学生', role: 'student', password: studentPassword },
    })
    expect(createdStudent.status()).toBe(201)
    studentId = (await createdStudent.json()).id as string
    const teacherCourses = await apiGetList(teacherPage, '/api/v1/courses', teacherHeaders)
    const course = teacherCourses.find((item: { id: string; status: string }) => item.status === 'published')
    if (!course) throw new Error('教师没有已发布的演示课程')
    const enrollment = await teacherPage.request.post(`/api/v1/courses/${course.id}/members`, {
      headers: teacherHeaders, data: { username: studentUsername },
    })
    expect(enrollment.status()).toBe(201)
    await login(page, studentUsername, studentPassword)
    const studentToken = await page.evaluate(() => localStorage.getItem('rag_token'))
    if (!studentToken) throw new Error('临时学生未取得访问令牌')
    const studentHeaders = { Authorization: `Bearer ${studentToken}` }
    const adminFixtureHeaders = {Authorization:'Bearer '+await apiToken(teacherPage,'admin','admin123')}
    const created = await teacherPage.request.post(`/api/v1/courses/${course.id}/sessions`, {
      headers: adminFixtureHeaders, data: { title: sessionTitle,
        session_date: new Date(new Date().setHours(22,0,0,0)).toISOString(), duration_minutes: 30,
        location: '临时验收教室' },
    })
    expect(created.status()).toBe(201)
    sessionId = (await created.json()).id as string

    await page.locator('.assistant-fab').click()
    const assistant = page.locator('#global-ai-assistant')
    if(!(await assistant.getByLabel('选择学习课程').isVisible()))await assistant.locator('.assistant-context-toggle').click()
    await assistant.getByLabel('选择学习课程').selectOption(course.id)
    await assistant.getByLabel('向 AI 助手提问').fill(question)
    const answerResponse = page.waitForResponse((response) => response.url().includes('/api/v1/questions/ask')
      && response.request().method() === 'POST')
    await assistant.getByRole('button', { name: '发送 ↗' }).click()
    const answered = await answerResponse
    expect(answered.ok()).toBeTruthy()
    const answer = await readStreamAnswer(answered,page)
    conversationId = answer.conversation_id as string
    expect(answer.model).toBe('platform-data')
    const courseAction = answer.actions?.find((item: { kind: string }) => item.kind === 'course')
    expect(courseAction?.target_id).toBe(course.id)
    await expect(assistant.locator('.assistant-result-actions button').filter({ hasText: courseAction.title })).toBeVisible()

    await page.reload()
    await page.locator('.assistant-fab').click()
    await assistant.getByRole('navigation', { name: '助手功能' }).getByRole('button', { name: '历史' }).click()
    const historyRecord = assistant.locator('.assistant-history-item').filter({ hasText: question })
    await expect(historyRecord).toBeVisible()
    await historyRecord.click()
    const restoredAction = assistant.locator('.assistant-result-actions button').filter({ hasText: courseAction.title })
    await expect(restoredAction).toBeVisible()
    const removed = await teacherPage.request.patch(`/api/v1/courses/${course.id}/members/${studentId}`, {
      headers: teacherHeaders, data: { status: 'removed' },
    })
    expect(removed.status()).toBe(200)
    expect((await removed.json()).status).toBe('removed')
    expect((await page.request.get(`/api/v1/courses/${course.id}`, { headers: studentHeaders })).status()).toBe(404)
    await restoredAction.click()
    await expect(assistant.getByRole('alert')).toContainText('当前用户无权访问')
    await expect(assistant).toBeVisible()
    await expect(page.locator('dialog:has(nav[aria-label="课程详情栏目"])')).toHaveCount(0)
    const reenrolled = await teacherPage.request.patch(`/api/v1/courses/${course.id}/members/${studentId}`, {
      headers: teacherHeaders, data: { status: 'active' },
    })
    expect(reenrolled.status()).toBe(200)
    expect((await reenrolled.json()).status).toBe('active')
    await restoredAction.click()
    await expect(assistant).toHaveCount(0)
    await expect(page.locator('dialog:has(nav[aria-label="课程详情栏目"])')).toBeVisible()
    await expect(page.locator('dialog:has(nav[aria-label="课程详情栏目"])')).toContainText(course.title)
    await expectUsableViewport(page)
  } finally {
    await teacherContext.close()
    try {
      cleanHistoryCardFixture(sessionId, conversationId, sessionTitle, question)
    } finally {
      cleanIsolatedStudentFixture(studentId, studentUsername)
    }
  }
})

test('学生：历史作业卡片在选课移除后拒绝打开并可恢复重试', async ({ page, browser }) => {
  const title = `作业卡片验收-${randomUUID().slice(0, 8)}`
  const question = `下一个作业是什么？${title}`
  const studentUsername = `e2e_assignment_${randomUUID().slice(0, 8)}`
  const studentPassword = `e2e-Assignment-${randomUUID()}`
  let studentId: string | null = null
  let questionId: string | null = null
  let assignmentId: string | null = null
  let conversationId: string | null = null
  const teacherContext = await browser.newContext({ baseURL: isolatedURL })
  const teacherPage = await teacherContext.newPage()
  try {
    await login(teacherPage, 'teacher', 'teacher123')
    const teacherToken = await teacherPage.evaluate(() => localStorage.getItem('rag_token'))
    if (!teacherToken) throw new Error('教师测试账号未取得访问令牌')
    const teacherHeaders = { Authorization: `Bearer ${teacherToken}` }
    const adminToken = await apiToken(teacherPage, 'admin', 'admin123')
    const createdStudent = await teacherPage.request.post('/api/v1/admin/users', {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: { username: studentUsername, display_name: '作业卡片隔离测试学生', role: 'student', password: studentPassword },
    })
    expect(createdStudent.status()).toBe(201)
    studentId = (await createdStudent.json()).id as string
    const teacherCourses = await apiGetList(teacherPage, '/api/v1/courses', teacherHeaders)
    const course = teacherCourses.find((item: { id: string; status: string }) => item.status === 'published')
    if (!course) throw new Error('教师没有已发布的演示课程')
    const enrollment = await teacherPage.request.post(`/api/v1/courses/${course.id}/members`, {
      headers: teacherHeaders, data: { username: studentUsername },
    })
    expect(enrollment.status()).toBe(201)
    await login(page, studentUsername, studentPassword)
    const studentToken = await page.evaluate(() => localStorage.getItem('rag_token'))
    if (!studentToken) throw new Error('临时学生未取得访问令牌')
    const studentHeaders = { Authorization: `Bearer ${studentToken}` }
    const questionCreated = await teacherPage.request.post('/api/v1/questions', { headers: teacherHeaders, data: {
      course_id: course.id, question_type: 'single_choice', stem: `${title}：1 + 1 等于多少？`,
      options: ['A. 2', 'B. 3'], correct_answer: 'A', explanation: '1 + 1 = 2。', knowledge_point: '基础运算',
    } })
    expect(questionCreated.status()).toBe(201)
    questionId = (await questionCreated.json()).id as string
    const assignmentCreated = await teacherPage.request.post('/api/v1/assignments', { headers: teacherHeaders, data: {
      course_id: course.id, title, question_ids: [questionId], status: 'draft',
      due_at: new Date(Date.now() + 2 * 60_000).toISOString(),
    } })
    expect(assignmentCreated.status()).toBe(201)
    assignmentId = (await assignmentCreated.json()).id as string
    const published = await teacherPage.request.patch(`/api/v1/assignments/${assignmentId}/status`, {
      headers: teacherHeaders, data: { status: 'published' },
    })
    expect(published.status()).toBe(200)

    await page.reload()
    await page.locator('.assistant-fab').click()
    const assistant = page.locator('#global-ai-assistant')
    if(!(await assistant.getByLabel('选择学习课程').isVisible()))await assistant.locator('.assistant-context-toggle').click()
    await assistant.getByLabel('选择学习课程').selectOption(course.id)
    await assistant.getByLabel('向 AI 助手提问').fill(question)
    const answerResponse = page.waitForResponse((response) => response.url().includes('/api/v1/questions/ask')
      && response.request().method() === 'POST')
    await assistant.getByRole('button', { name: '发送 ↗' }).click()
    const answered = await answerResponse
    expect(answered.ok()).toBeTruthy()
    const answer = await readStreamAnswer(answered,page)
    conversationId = answer.conversation_id as string
    expect(answer.model).toBe('platform-data')
    const action = answer.actions?.find((item: { kind: string; target_id: string }) =>
      item.kind === 'assignment' && item.target_id === assignmentId)
    expect(action?.title).toBe(title)

    await page.reload()
    await page.locator('.assistant-fab').click()
    await assistant.getByRole('navigation', { name: '助手功能' }).getByRole('button', { name: '历史' }).click()
    const historyRecord = assistant.locator('.assistant-history-item').filter({ hasText: question })
    await expect(historyRecord).toBeVisible()
    await historyRecord.click()
    const restoredAction = assistant.locator('.assistant-result-actions button').filter({ hasText: title })
    await expect(restoredAction).toBeVisible()
    const withdrawn = await teacherPage.request.patch(`/api/v1/courses/${course.id}/members/${studentId}`, {
      headers: teacherHeaders, data: { status: 'removed' },
    })
    expect(withdrawn.status()).toBe(200)
    expect((await page.request.get(`/api/v1/assignments/${assignmentId}`, { headers: studentHeaders })).status()).toBe(404)
    await restoredAction.click()
    await expect(assistant.getByRole('alert')).toContainText('作业不存在或当前用户无权访问')
    await expect(page.locator('.assignment-sheet')).toHaveCount(0)
    const republished = await teacherPage.request.post(`/api/v1/courses/${course.id}/members`, {
      headers: teacherHeaders, data: { username: studentUsername },
    })
    expect(republished.status()).toBe(201)
    await restoredAction.click()
    await expect(assistant).toHaveCount(0)
    await expect(page.locator('.assignment-sheet')).toContainText(title)
    await expectUsableViewport(page)
  } finally {
    await teacherContext.close()
    try {
      cleanAssignmentCardFixture(assignmentId, questionId, conversationId, title, question)
    } finally {
      cleanIsolatedStudentFixture(studentId, studentUsername)
    }
  }
})

test('学生：助手历史可以逐页加载更多对话', async ({ page }) => {
  await login(page, 'student04', 'student123')
  const records = Array.from({ length: 21 }, (_, index) => ({
    id: randomUUID(), knowledge_base_id: null, title: `分页验收对话 ${String(index + 1).padStart(2, '0')}`,
    message_count: 1, created_at: new Date(Date.now() - index * 60_000).toISOString(),
    updated_at: new Date(Date.now() - index * 60_000).toISOString(),
  }))
  await page.route('**/api/v1/tutor/conversations?*', (route) => {
    const params = new URL(route.request().url()).searchParams
    const before = params.get('before')
    const pageRecords = params.get('query') ? records.filter(row=>row.title.includes(params.get('query')!)) : before === null ? records.slice(0, 20)
      : before === records[19].id ? records.slice(20) : []
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(pageRecords) })
  })
  await page.locator('.assistant-fab').click()
  const assistant = page.locator('#global-ai-assistant')
  await assistant.getByRole('navigation', { name: '助手功能' }).getByRole('button', { name: '历史' }).click()
  await expect(assistant.locator('.assistant-history-item')).toHaveCount(20)
  await expect(assistant.getByText('分页验收对话 21')).toHaveCount(0)
  await assistant.getByRole('button', { name: '加载更多对话' }).click()
  await expect(assistant.locator('.assistant-history-item')).toHaveCount(21)
  await expect(assistant.getByRole('button', { name: '加载更多对话' })).toHaveCount(0)
  await assistant.getByLabel('搜索全部历史对话').fill('分页验收对话 21')
  await expect(assistant.locator('.assistant-history-item')).toHaveCount(1)
  await expectUsableViewport(page)
})

test('管理员：管理控制台、模型设置与 AI 管理助理', async ({ page }) => {
  await login(page, 'admin', 'admin123')
  await navigation(page).getByRole('button', { name: '管理控制台' }).click()
  await expect(page.getByRole('heading', { name: '待处理事项' })).toBeVisible()
  await page.locator('.admin-tabs').getByRole('button', { name: '模型与 RAG' }).click()
  await expect(page.getByRole('heading', { name: '模型与 RAG' })).toBeVisible()
  await navigation(page).getByRole('button', { name: 'AI 管理助理' }).click()
  await expect(page.getByRole('button', { name: '发送 ↗' })).toBeVisible()
  await expectUsableViewport(page)
})

test('管理员：从助手建议到账号启用须确认并留下审计', async ({ page }) => {
  const username = `e2e_adminflow_${randomUUID().slice(0, 8)}`
  let userId: string | null = null
  try {
    await login(page, 'admin', 'admin123')
    const adminToken = await page.evaluate(() => localStorage.getItem('rag_token'))
    if (!adminToken) throw new Error('管理员登录未取得令牌')
    const adminHeaders = { Authorization: `Bearer ${adminToken}` }
    const created = await page.request.post('/api/v1/admin/users', { headers: adminHeaders, data: {
      username, display_name: `临时治理账号 ${username.slice(-8)}`, role: 'student', password: 'E2eAdminFlow123!',
    } })
    expect(created.status()).toBe(201)
    userId = (await created.json()).id as string
    const path = `/api/v1/admin/users/${userId}`
    const deactivated = await page.request.patch(path, { headers: adminHeaders,
      data: { active: false, confirmed: true } })
    expect(deactivated.status()).toBe(200)
    const studentToken = await apiToken(page, 'student', 'student123')
    const denied = await page.request.patch(path, { headers: { Authorization: `Bearer ${studentToken}` },
      data: { active: true, confirmed: true } })
    expect(denied.status()).toBe(403)
    const unconfirmed = await page.request.patch(path, { headers: adminHeaders, data: { active: true } })
    expect(unconfirmed.status()).toBe(409)

    await page.reload()
    await navigation(page).getByRole('button', { name: '管理控制台' }).click()
    const suggestion = page.locator('.admin-insight-grid').getByRole('button', { name: /账号处于停用状态/ })
    await expect(suggestion).toBeVisible()
    await suggestion.click()
    await page.getByRole('button',{name:'原账号管理页 ↗',exact:true}).click()
    await expect(page.getByRole('heading', { name: '平台用户' })).toBeVisible()
    const filter = page.locator('.user-directory-toolbar')
    await filter.getByRole('combobox',{name:'账号状态'}).selectOption('inactive')
    await filter.getByRole('button',{name:'搜索',exact:true}).click()
    const row = page.locator('.admin-user-list article').filter({ hasText: username })
    await expect(row).toContainText('已停用')
    await row.getByRole('button', { name: '启用' }).click()
    const dialog = page.getByRole('alertdialog', { name: '确认启用账号？' })
    await expect(dialog).toContainText(username)
    await dialog.getByRole('button', { name: '取消',exact:true }).click()
    await expect(row).toContainText('已停用')
    await row.getByRole('button', { name: '启用' }).click()
    await dialog.getByRole('button', { name: '确认执行' }).click()
    await expect(row).toHaveCount(0)
    await filter.getByRole('combobox',{name:'账号状态'}).selectOption('all')
    await filter.getByRole('button',{name:'搜索',exact:true}).click()
    await filter.getByRole('searchbox',{name:'搜索用户'}).fill(username)
    await filter.getByRole('button',{name:'搜索',exact:true}).click()
    await expect(row).toContainText('正常')
    const users = await apiGetList(page, '/api/v1/admin/users', adminHeaders)
    expect(users.find((item: { id: string }) => item.id === userId)?.active).toBe(true)
    const audits = await apiGetList(page, '/api/v1/admin/audit-logs?limit=100', adminHeaders)
    const actions = audits.filter((item: { resource_id: string; action: string }) => item.resource_id === userId)
    expect(actions.map((item: { action: string }) => item.action).sort()).toEqual(['activate', 'create', 'deactivate'])
    expect(actions.find((item: { action: string }) => item.action === 'activate')?.detail.confirmed).toBe(true)
    await expectUsableViewport(page)
  } finally {
    cleanAdminActionFixture(userId, username)
  }
})

test('管理员：模型额度草稿须说明原因并二次确认', async ({ page }) => {
  await login(page, 'admin', 'admin123')
  await navigation(page).getByRole('button', { name: '管理控制台' }).click()
  await page.locator('.admin-tabs').getByRole('button', { name: '调用额度' }).click()
  const studentQuota = page.locator('.model-quota-grid article').filter({ hasText: '学生' })
  const input = studentQuota.getByRole('spinbutton', { name: '设置学生每日模型额度' })
  const original = Number(await input.inputValue())
  const nextLimit = original === 100000 ? original - 1 : original + 1
  const adminToken = await page.evaluate(() => localStorage.getItem('rag_token'))
  if (!adminToken) throw new Error('管理员登录未取得令牌')
  const studentToken = await apiToken(page, 'student', 'student123')
  const body = { daily_limit: nextLimit, reason: '课程试用期间调整每日调用额度', confirmed: true }
  const denied = await page.request.put('/api/v1/admin/model-quotas/student', {
    headers: { Authorization: `Bearer ${studentToken}` }, data: body,
  })
  expect(denied.status()).toBe(403)
  const unconfirmed = await page.request.put('/api/v1/admin/model-quotas/student', {
    headers: { Authorization: `Bearer ${adminToken}` }, data: { ...body, confirmed: false },
  })
  expect(unconfirmed.status()).toBe(409)
  let updates = 0
  await page.route('**/api/v1/admin/model-quotas/student', async (route) => {
    if (route.request().method() !== 'PUT') return route.continue()
    const body = route.request().postDataJSON() as { daily_limit: number; reason: string; confirmed: boolean }
    expect(body).toEqual({ daily_limit: nextLimit, reason: '课程试用期间调整每日调用额度', confirmed: true })
    updates += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ role: 'student', daily_limit: nextLimit }) })
  })
  await input.fill(String(nextLimit))
  await studentQuota.getByRole('button', { name: '保存额度' }).click()
  const dialog = page.getByRole('alertdialog', { name: '确认修改学生模型额度？' })
  await expect(dialog).toContainText(`${original} 次改为 ${nextLimit} 次`)
  await expect(dialog.getByRole('button', { name: '确认执行' })).toBeDisabled()
  await dialog.getByRole('button', { name: '取消',exact:true }).click()
  expect(updates).toBe(0)
  await expect(input).toHaveValue(String(nextLimit))
  await studentQuota.getByRole('button', { name: '保存额度' }).click()
  await dialog.getByRole('textbox', { name: '修改原因' }).fill('课程试用期间调整每日调用额度')
  await dialog.getByRole('button', { name: '确认执行' }).click()
  await expect.poll(() => updates).toBe(1)
  await expect(page.locator('.platform-message').filter({visible:true}).first()).toContainText('额度已保存并立即生效')
  await expectUsableViewport(page)
})

test('管理员：评测页按最新门禁和资料覆盖展示状态', async ({ page }) => {
  await login(page, 'admin', 'admin123')
  const token = await page.evaluate(() => localStorage.getItem('rag_token'))
  if (!token) throw new Error('管理员登录未取得令牌')
  const runs = await apiGetList(page, '/api/v1/admin/evaluations', { Authorization: `Bearer ${token}` })
  const latest = runs[0] as { dataset_version: string; metrics: { quality_gate?: boolean; source_coverage?: {
    covered_cases: number; missing_cases: number; positive_cases: number; missing_documents: string[]
  } } }
  if (!latest) throw new Error('当前没有评测记录')
  await navigation(page).getByRole('button', { name: '管理控制台' }).click()
  await page.locator('.admin-tabs').getByRole('button', { name: '质量评测' }).click()
  const report=page.locator('.eval-report').first()
  await expect(report).toContainText(latest.dataset_version)
  const metrics=latest.metrics as Record<string,any>
  if(metrics.gate_details) await expect(report).toContainText(metrics.gate_details.passed?'达到当前门槛':'未达到当前门槛')
  else await expect(report).toContainText('历史标准，请重新评测')
  await report.getByRole('button',{name:'指标详情'}).click()
  const detail=page.getByRole('dialog',{name:'评测指标详情'})
  await expect(detail).toContainText('引用精度')
  const coverage=latest.metrics.source_coverage
  if(coverage) {
    await expect(detail).toContainText(`${coverage.covered_cases} / ${coverage.positive_cases}`)
    for(const document of coverage.missing_documents||[])await expect(detail).toContainText(document)
  }
  await page.keyboard.press('Escape')
  await expectUsableViewport(page)
})

test('学生：从课程原文保存摘录、返回原文并清理笔记', async ({ page }) => {
  await login(page, 'student', 'student123')
  let createdNoteId: string | null = null
  let noteDeleted = false
  try {
    await navigation(page).getByRole('button', { name: '我的课程' }).click()
    await page.getByLabel('搜索课程').fill('DSA-2026')
    await page.locator('.course-directory').getByRole('button',{name:'搜索',exact:true}).click()
    await page.locator('.course-card').first().click()
    await page.getByRole('navigation',{name:'课程详情栏目'}).getByRole('button',{name:'资料与知识点'}).click()
    await page.getByRole('navigation',{name:'课程详情栏目'}).getByRole('button',{name:'资料与知识点'}).click()
  const material = page.locator('.course-detail-grid > section').nth(1).locator('.course-detail-item').first()
    await expect(material).toBeVisible()
    await material.click()
    const preview = page.locator('dialog:has(.document-reading-page)')
    await expect(preview).toBeVisible()
    const excerpt = await preview.locator('.document-reading-page pre').first().evaluate((element) => {
      const textNode = element.firstChild
      if (!textNode || textNode.nodeType !== Node.TEXT_NODE || !textNode.textContent || textNode.textContent.length < 20) {
        throw new Error('测试资料首页没有可选的正文')
      }
      const range = document.createRange()
      range.setStart(textNode, 0)
      range.setEnd(textNode, Math.min(textNode.textContent.length, 100))
      const selection = window.getSelection()
      selection?.removeAllRanges()
      selection?.addRange(range)
      element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      return selection?.toString().trim() ?? ''
    })
    expect(excerpt.length).toBeGreaterThanOrEqual(10)
    await expect(preview.getByRole('button', { name: '保存摘录' })).toBeVisible()
    await page.route('**/api/v1/study-notes', (route) => route.request().method() === 'POST'
      ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '临时无法保存，请重试' }) })
      : route.continue())
    await preview.getByRole('button', { name: '保存摘录' }).click()
    await expect(preview.getByRole('alert')).toContainText('临时无法保存，请重试')
    await expect(preview.getByRole('button', { name: '保存摘录' })).toBeEnabled()
    await page.unroute('**/api/v1/study-notes')
    const noteResponse = page.waitForResponse((response) => response.url().includes('/api/v1/study-notes') && response.request().method() === 'POST')
    await preview.getByRole('button', { name: '保存摘录' }).click()
    const saved = await noteResponse
    expect(saved.status()).toBe(201)
    createdNoteId = (await saved.json()).id as string
    await expect(preview.getByRole('status')).toContainText('已保存')
    await preview.locator('header button').click()
    await page.locator('dialog:has(nav[aria-label="课程详情栏目"]) .detail-close').click()
    await page.locator('.assistant-fab').click()
    await page.getByRole('navigation', { name: '助手功能' }).getByRole('button', { name: '学习工具' }).click()
    const note = page.locator('.study-note-card').first()
    await expect(note).toContainText(excerpt.slice(0, 30))
    await note.getByRole('button', { name: '查看原文' }).click()
    await expect(page.locator('dialog:has(.document-reading-page) .document-reading-page')).toBeVisible()
    await page.locator('dialog:has(.document-reading-page) .detail-close').click()
    await page.locator('.assistant-fab').click()
    await page.getByRole('navigation', { name: '助手功能' }).getByRole('button', { name: '学习工具' }).click()
    page.once('dialog', (dialog) => dialog.accept())
    await page.locator('.study-note-card').first().getByRole('button', { name: '删除' }).click()
    await expect(page.locator('#global-ai-assistant').getByText('学习笔记已删除。')).toBeVisible()
    const token = await page.evaluate(() => localStorage.getItem('rag_token'))
    const remaining = await page.request.get('/api/v1/study-notes', { headers: { Authorization: `Bearer ${token}` } })
    expect(remaining.ok()).toBeTruthy()
    expect((await remaining.json()).some((item: { id: string }) => item.id === createdNoteId)).toBeFalsy()
    noteDeleted = true
    await expectUsableViewport(page)
  } finally {
    if (createdNoteId && !noteDeleted) {
      const token = await page.evaluate(() => localStorage.getItem('rag_token'))
      if (token) await page.request.delete(`/api/v1/study-notes/${createdNoteId}`, { headers: { Authorization: `Bearer ${token}` } })
    }
  }
})

test('学生：未核准资料保留摘录入口，不误触发选段 AI 外发', async ({ page }) => {
  await login(page, 'student', 'student123')
  await navigation(page).getByRole('button', { name: '我的课程' }).click()
  await page.getByLabel('搜索课程').fill('DSA-2026')
  await page.locator('.course-directory').getByRole('button',{name:'搜索',exact:true}).click()
  await page.locator('.course-card').first().click()
  await page.getByRole('navigation',{name:'课程详情栏目'}).getByRole('button',{name:'资料与知识点'}).click()
  await page.locator('.course-detail-grid > section').nth(1).locator('.course-detail-item').first().click()
  const preview = page.locator('dialog:has(.document-reading-page)')
  await expect(preview).toBeVisible()
  await expect(preview.getByText(/仅供站内阅读与检索|在线 AI 模型不可用/)).toBeVisible()
  await preview.locator('.document-reading-page pre').first().evaluate((element) => {
    const textNode = element.firstChild
    if (!textNode || textNode.nodeType !== Node.TEXT_NODE || !textNode.textContent || textNode.textContent.length < 20) {
      throw new Error('测试资料首页没有可选的正文')
    }
    const range = document.createRange()
    range.setStart(textNode, 0)
    range.setEnd(textNode, Math.min(textNode.textContent.length, 100))
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  })
  const askRequests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/questions/ask')) askRequests.push(request.url())
  })
  await preview.getByRole('button', { name: '解释选段' }).click()
  await expect(preview.getByRole('alert')).toContainText(/暂不能生成选段讲解/)
  await expect(preview).toBeVisible()
  await expect(preview.getByRole('button', { name: '保存摘录' })).toBeEnabled()
  expect(askRequests).toHaveLength(0)
  await expect(page.locator('.global-assistant-panel')).toHaveCount(0)
  await expectUsableViewport(page)
})

test('学生：本地证据回答明确标为非 AI 讲解', async ({ page }) => {
  await login(page, 'student', 'student123')
  await mockAnswer(page, (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      accepted: true, message: '已阻止将未核准的课程资料发送至外部模型。',
      answer: '### 本地资料证据\n\n这里只显示原文片段。', model: 'local-evidence',
      answer_mode: 'hybrid', history_id: null, conversation_id: null, actions: [],
      citations: [{ document_id: null, chunk_id: null, document_name: '课程讲义', page_number: 1,
        chapter: '地址空间', text: '这里只显示原文片段。', score: 0.8 }],
    }),
  }))
  await page.locator('.assistant-fab').click()
  await page.getByRole('textbox', { name: '向 AI 助手提问' }).fill('解释虚拟地址')
  await page.getByRole('button', { name: '发送 ↗' }).click()
  const response = page.locator('.assistant-response')
  await expect(response.locator('.assistant-answer-heading small')).toContainText('本地资料证据 · 未经 AI 讲解')
  await expect(response.locator('.assistant-evidence-note')).toContainText('并非 AI 归纳或讲解')
  await expect(response.locator('.assistant-note-editor')).toHaveCount(0)
  await expectUsableViewport(page)
})

test('学生：模型超时明确提示且可原问题重试', async ({ page }) => {
  await login(page, 'student', 'student123')
  let attempts = 0
  await mockAnswer(page, (route) => {
    attempts += 1
    if (attempts === 1) {
      return route.fulfill({ status: 504, contentType: 'application/json',
        body: JSON.stringify({ detail: '模型响应超时，本次未生成回答；请稍后重试。' }) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({
        accepted: true, message: '回答已生成', answer: '虚拟地址经过页表映射得到物理地址。',
        model: 'test-model', answer_mode: 'general', history_id: randomUUID(),
        conversation_id: randomUUID(), actions: [], citations: [],
      }) })
  })
  await page.locator('.assistant-fab').click()
  const assistant = page.locator('.global-assistant-panel')
  await assistant.getByLabel('向 AI 助手提问').fill('解释虚拟地址')
  await assistant.getByRole('button', { name: '发送 ↗' }).click()
  const failure = assistant.locator('.assistant-turn-error')
  await expect(failure).toContainText('本次未生成回答')
  await expect(assistant.locator('.assistant-response')).toHaveCount(0)
  await failure.getByRole('button', { name: '重新尝试' }).click()
  await expect(assistant.locator('.assistant-response')).toContainText('虚拟地址经过页表映射得到物理地址。')
  await expect(failure).toHaveCount(0)
  expect(attempts).toBe(2)
  await expectUsableViewport(page)
})

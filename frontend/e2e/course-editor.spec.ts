import { expect, test, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'

test.beforeAll(async({request})=>{await expect.poll(async()=>{try{return(await request.get('/health')).status()}catch{return 0}},{timeout:45000}).toBe(200)})

function pdfFixture() {
  const stream = 'BT /F1 12 Tf 50 750 Td (Binary search requires sorted input. Maintain the search interval and compare the middle element.) Tj ET\n'
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>', `<< /Length ${stream.length} >>\nstream\n${stream}endstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
  let text = '%PDF-1.4\n'; const offsets = [0]
  objects.forEach((object, index) => { offsets.push(text.length); text += `${index + 1} 0 obj\n${object}\nendobj\n` })
  const xref = text.length
  text += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(x => String(x).padStart(10, '0') + ' 00000 n \n').join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(text, 'ascii')
}

async function auth(page: Page, role: 'teacher' | 'admin' | 'student') {
  const response = await page.request.post('/api/v1/auth/login', { data: { username: role, password: role + '123' } })
  expect(response.status()).toBe(200)
  return (await response.json()).access_token as string
}
async function enter(page: Page, token: string) {
  const owner = JSON.parse(Buffer.from(token.split('.')[0]!, 'base64url').toString()).sub
  await page.addInitScript(({ token, owner }) => {
    localStorage.setItem('rag_token', token)
    localStorage.setItem('rag_update_notice:' + owner, '2026-10-29-zhixue-assistant')
  }, { token, owner })
  await page.goto('/')
  await expect(page.getByRole('navigation', { name: '平台导航' })).toBeVisible()
}
async function openCourse(page: Page, name: string, admin = false) {
  await page.getByRole('navigation', { name: '平台导航' }).getByRole('button', { name: admin ? '课程与资料' : '教学课程' }).click()
  await page.locator('.directory-toolbar').getByLabel('搜索课程').fill(name)
  await page.locator('.directory-toolbar').getByRole('button', { name: '搜索', exact: true }).click()
  await page.locator('.course-directory-card').filter({ hasText: name }).click()
  const detail = page.getByRole('dialog', { name, exact: true })
  await detail.getByRole('button', { name: '编辑课程', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑课程', exact: true })
  await expect(editor.getByLabel('课程名称', { exact: true })).toHaveValue(name)
  return { detail, editor }
}

test('课程草稿、章节知识点资料绑定、预览发布及学生回读', async ({ page }, info) => {
  test.setTimeout(90_000)
  const teacher = await auth(page, 'teacher'), student = await auth(page, 'student')
  const headers = { Authorization: 'Bearer ' + teacher }
  const suffix = randomUUID().slice(0, 8), name = '课程编辑验收-' + suffix
  const created = await page.request.post('/api/v1/courses', { headers, data: { title: name, code: 'EDIT-' + suffix, description: '原课程介绍', semester: '2026-2027 第一学期', status: 'published' } })
  expect(created.status()).toBe(201)
  const course = await created.json()
  const member = await page.request.post(`/api/v1/courses/${course.id}/members`, { headers, data: { username: 'student' } })
  expect(member.status()).toBe(201)
  const baseResponse = await page.request.post('/api/v1/knowledge-bases', { headers, data: { name: '算法课程选读-' + suffix, course: name } })
  expect(baseResponse.status()).toBe(201)
  const base = await baseResponse.json()
  await enter(page, teacher)
  const { detail, editor } = await openCourse(page, name)
  await editor.getByLabel('课程介绍', { exact: true }).fill('更新后的课程介绍')
  await editor.getByLabel('学习目标', { exact: true }).fill('- 理解时间复杂度\n- 能够分析二分查找')
  await editor.getByLabel('考核方式', { exact: true }).fill('实验 40%，作业 30%，期末 30%。')
  await editor.getByRole('button', { name: '教学大纲', exact: true }).click()
  await editor.getByRole('button', { name: '＋ 添加章节', exact: true }).click()
  await editor.getByLabel('章节名称', { exact: true }).fill('算法基础')
  await expect(editor.getByLabel('章节内容', { exact: true })).toBeVisible()
  await editor.getByLabel('章节内容', { exact: true }).fill('复杂度与二分查找')
  await editor.getByRole('button', { name: '知识点', exact: true }).click()
  await editor.getByRole('button', { name: '＋ 添加知识点', exact: true }).click()
  await editor.getByLabel('知识点名称', { exact: true }).fill('二分查找边界')
  await editor.getByRole('combobox', { name: '所属章节', exact: true }).selectOption({ label: '算法基础' })
  await editor.getByLabel('知识点解释', { exact: true }).fill('维护搜索区间与循环不变式。')
  await editor.getByRole('button', { name: '课程资料', exact: true }).click()
  await editor.getByLabel('查找资料库', { exact: true }).fill(base.name)
  await editor.locator('.course-editor-search').filter({ has: page.getByLabel('查找资料库', { exact: true }) }).getByRole('button', { name: '查询', exact: true }).click()
  await editor.locator('.course-editor-choice').filter({ hasText: base.name }).click()
  const saved = page.waitForResponse(r => r.url().endsWith('/editor') && r.request().method() === 'PUT')
  await editor.getByRole('button', { name: '保存草稿', exact: true }).click()
  expect((await saved).status()).toBe(200)
  await expect(editor).toContainText('课程草稿已保存')
  const liveBefore = await (await page.request.get(`/api/v1/courses/${course.id}`, { headers: { Authorization: 'Bearer ' + student } })).json()
  expect(liveBefore.description).toBe('原课程介绍')
  expect(liveBefore.sections).toHaveLength(0)
  expect(liveBefore.learning_objectives).toBe('')
  await editor.getByRole('button', { name: '关闭窗口', exact: true }).click()
  await detail.getByRole('button', { name: '编辑课程', exact: true }).click()
  await expect(editor.getByLabel('学习目标', { exact: true })).toHaveValue('- 理解时间复杂度\n- 能够分析二分查找')
  await editor.getByRole('button', { name: '发布预览', exact: true }).first().click()
  await expect(editor.getByRole('button', { name: '确认发布内容', exact: true })).toBeDisabled()
  await editor.getByRole('checkbox', { name: '已核对课程内容，确认更新课程展示内容' }).check()
  const overflow = await editor.evaluate(root => [...root.querySelectorAll<HTMLElement>('nav,fieldset,.detail-dialog-frame,.detail-dialog-footer')].filter(x => x.getClientRects().length).map(x => ({ w: x.clientWidth, s: x.scrollWidth })))
  expect(overflow.filter(x => x.s > x.w + 2)).toEqual([])
  const layout = await page.evaluate(() => ({ inner: innerWidth, root: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth, visual: visualViewport?.width, dialogs: [...document.querySelectorAll('dialog[open]')].map(x => ({ width: x.getBoundingClientRect().width, height: x.getBoundingClientRect().height, position: getComputedStyle(x).position })) }))
  await info.attach('layout.json', { body: JSON.stringify({ viewport: page.viewportSize(), ...layout }), contentType: 'application/json' })
  expect(layout.root).toBeLessThanOrEqual(page.viewportSize()!.width + 2)
  expect(layout.scroll).toBeLessThanOrEqual(page.viewportSize()!.width + 2)
  await page.screenshot({ path: info.outputPath('course-editor-preview.png') })
  const published = page.waitForResponse(r => r.url().endsWith('/editor/publish'))
  await editor.getByRole('button', { name: '确认发布内容', exact: true }).click()
  expect((await published).status()).toBe(200)
  await expect(editor).toContainText('课程内容已更新')
  await editor.getByRole('button', { name: '关闭窗口', exact: true }).click()
  await expect(detail.locator('.course-intro').filter({ hasText: '学习目标' })).toBeVisible()
  const live = await (await page.request.get(`/api/v1/courses/${course.id}`, { headers: { Authorization: 'Bearer ' + student } })).json()
  expect(live.description).toBe('更新后的课程介绍')
  expect(live.sections[0].title).toBe('算法基础')
  expect(live.assessment).toContain('40%')
  expect((await page.request.get(`/api/v1/courses/${course.id}/editor`, { headers: { Authorization: 'Bearer ' + student } })).status()).toBe(404)
  await detail.getByRole('button', { name: '编辑课程', exact: true }).first().click()
  await editor.getByRole('button', { name: '课程资料', exact: true }).click()
  await editor.getByLabel('选择 PDF', { exact: true }).setInputFiles({ name: '算法基础课程讲义.pdf', mimeType: 'application/pdf', buffer: pdfFixture() })
  await editor.getByRole('button', { name: '上传并索引', exact: true }).click()
  await expect(editor.getByRole('status').filter({ hasText: '资料已上传并索引' })).toBeVisible({ timeout: 60000 })
  const docs = await (await page.request.get(`/api/v1/knowledge-bases/${base.id}/documents`, { headers })).json()
  expect(docs).toHaveLength(1)
  expect(docs[0].name).toBe('算法基础课程讲义')
  await editor.getByRole('button', { name: '关闭窗口', exact: true }).click()
})

test('管理员可分页查找授课教师，未保存修改关闭时需确认', async ({ page }) => {
  const teacher = await auth(page, 'teacher'), admin = await auth(page, 'admin')
  const suffix = randomUUID().slice(0, 8), name = '教师分配验收-' + suffix
  const created = await page.request.post('/api/v1/courses', { headers: { Authorization: 'Bearer ' + teacher }, data: { title: name, code: 'OWN-' + suffix } })
  expect(created.status()).toBe(201)
  await enter(page, admin)
  const { editor } = await openCourse(page, name, true)
  await editor.getByText(/分配授课教师 ·/).click()
  await editor.getByLabel('查找教师',{exact:true}).fill('teacher')
  await editor.getByLabel('查找教师',{exact:true}).press('Enter')
  await expect(editor.locator('.course-editor-choice').filter({ hasText: 'teacher' }).first()).toBeVisible()
  await editor.getByLabel('课程介绍', { exact: true }).fill('未保存介绍')
  page.once('dialog', dialog => dialog.dismiss())
  await editor.getByRole('button', { name: '关闭窗口', exact: true }).click()
  await expect(editor).toBeVisible()
  page.once('dialog', dialog => dialog.accept())
  await editor.getByRole('button', { name: '关闭窗口', exact: true }).click()
  await expect(editor).toHaveCount(0)
})

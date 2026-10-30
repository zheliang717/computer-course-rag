import { expect, test, type Page } from '@playwright/test'

async function login(page: Page, username: string, password: string) {
  if (username === 'student') username = test.info().project.name === 'edge-desktop' ? 'student02'
    : test.info().project.name === 'chrome-mobile' ? 'student03' : 'student'
  await page.goto('/')
  await page.getByLabel('账号').fill(username)
  await page.getByPlaceholder('输入登录密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录课程空间', exact: true }).click()
  await expect(page.getByRole('navigation', { name: '平台导航' })).toBeVisible()
}

test('管理员：用户筛选、日志翻页及失败重试', async ({ page }) => {
  let releaseInitialLoad = () => {}
  let releaseOldPage = () => {}
  let pageTwoRequests = 0
  const initialLoadGate = new Promise<void>(resolve => { releaseInitialLoad = resolve })
  const oldPageGate = new Promise<void>(resolve => { releaseOldPage = resolve })
  await page.route('**/api/v1/admin/model-config', async route => {
    await initialLoadGate
    await route.continue()
  })
  await page.route('**/api/v1/admin/assistant-tasks/users?*', async route => {
    if (new URL(route.request().url()).searchParams.get('page') === '2') {
      pageTwoRequests += 1
      if (pageTwoRequests === 1) await oldPageGate
    }
    await route.continue()
  })
  try {
  await login(page, 'admin', 'admin123')
  await page.getByRole('navigation', { name: '平台导航' }).getByRole('button', { name: '管理控制台' }).click()
  await page.getByRole('button', { name: '用户管理', exact: true }).click()
  const users = page.locator('.admin-user-list')
  await users.getByLabel('平台用户每页条数').selectOption('5')
  await expect(users.locator(':scope > article')).toHaveCount(5)
  await users.getByRole('button', { name: '下一页' }).click()
  await expect.poll(() => pageTwoRequests).toBe(1)
  releaseInitialLoad()
  releaseOldPage()
  await expect(users.getByRole('navigation', { name: '平台用户分页' })).toContainText('第 2 /')
  await page.getByRole('combobox',{name:'账号状态',exact:true}).selectOption('inactive')
  await page.locator('.user-directory-toolbar').getByRole('button',{name:'搜索',exact:true}).click()
  await expect(users).not.toContainText('第 2 /')

  let failOnce = true
  await page.route('**/api/v1/paged/audits?*', async route => {
    if (failOnce) {
      failOnce = false
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '暂时无法读取日志' }) })
    } else await route.continue()
  })
  await page.getByRole('button', { name: '审计日志', exact: true }).click()
  expect(await page.locator('.admin-tabs').getByRole('button', { name: '审计日志', exact: true }).evaluate(element => {
    const style = getComputedStyle(element)
    return style.whiteSpace === 'nowrap' && element.getBoundingClientRect().height < 60
  })).toBeTruthy()
  const audit = page.locator('.audit-list')
  await expect(audit.getByRole('alert')).toContainText('暂时无法读取日志')
  await audit.getByRole('button', { name: '重试' }).click()
  await expect(audit.getByRole('alert')).toHaveCount(0)
  await audit.getByLabel('审计日志每页条数').selectOption('5')
  await expect(audit.getByRole('button', { name: '下一页' })).toBeEnabled()
  failOnce = true
  await audit.getByRole('button', { name: '下一页' }).click()
  await expect(audit.getByRole('alert')).toContainText('暂时无法读取日志')
  await audit.getByRole('button', { name: '重试' }).click()
  await expect(audit.getByRole('navigation', { name: '审计日志分页' })).toContainText('第 2 /')
  await audit.getByLabel('审计日志跳转页码').fill('3')
  await audit.getByRole('button', { name: '跳转', exact: true }).click()
  await expect(audit.getByRole('navigation', { name: '审计日志分页' })).toContainText('第 3 /')
  const jumpButton = audit.getByRole('button', { name: '跳转', exact: true })
  await jumpButton.scrollIntoViewIfNeeded()
  expect(await jumpButton.evaluate(element => {
    const bounds = element.getBoundingClientRect()
    const hit = document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)
    return element === hit || element.contains(hit)
  })).toBeTruthy()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(2)
  await page.evaluate(() => window.scrollTo({ top: 0 }))
  await page.screenshot({ path: `test-results/pagination-admin-${test.info().project.name}.png`, fullPage: true })
  } finally {
    releaseInitialLoad()
    releaseOldPage()
  }
})

test('学生：课程课次与资料可翻页并保持详情入口', async ({ page }) => {
  await login(page, 'student', 'student123')
  await page.getByRole('navigation', { name: '平台导航' }).getByRole('button', { name: '我的课程' }).click()
  await page.getByLabel('搜索课程').fill('DSA-2026')
  await page.locator('.course-directory').getByRole('button',{name:'搜索',exact:true}).click()
  await page.locator('.course-card').filter({ hasText: '数据结构与算法' }).first().click()
  const detail = page.locator('dialog:has(.course-detail-tabs)')
  await detail.getByRole('button',{name:'课次安排',exact:true}).click()
  const sessions = detail.locator('.session-list')
  await sessions.getByLabel('课程课次每页条数').selectOption('5')
  await expect(sessions.locator(':scope > article')).toHaveCount(5)
  await sessions.getByRole('button', { name: '下一页' }).click()
  await expect(sessions.getByRole('navigation', { name: '课程课次分页' })).toContainText('第 2 /')
  await detail.getByRole('button',{name:'资料与知识点',exact:true}).click()
  await detail.locator('.course-detail-grid .course-detail-item').filter({ hasText: '页 ·' }).first().click()
  await expect(page.locator('dialog:has(.document-reading-page)')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(2)
})

test('临时读取故障保留登录，重新加载可恢复', async ({ page }) => {
  await login(page, 'admin', 'admin123')
  const savedToken = await page.evaluate(() => localStorage.getItem('rag_token'))
  for (const status of [429, 503]) {
    let failOnce = true
    await page.route('**/api/v1/auth/me', async route => {
      if (failOnce) {
        failOnce = false
        await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ detail: '临时读取失败，请重试' }) })
      } else await route.continue()
    })
    await page.reload()
    await expect(page.locator('.startup-error')).toContainText('临时读取失败')
    expect(await page.evaluate(() => localStorage.getItem('rag_token'))).toBe(savedToken)
    await page.getByRole('button', { name: '重新加载课程空间' }).click()
    await expect(page.getByRole('navigation', { name: '平台导航' })).toBeVisible()
    await page.unroute('**/api/v1/auth/me')
  }
})

test('登录已确认后的初始化失败不退出账号', async ({ page }) => {
  await login(page, 'admin', 'admin123')
  const savedToken = await page.evaluate(() => localStorage.getItem('rag_token'))
  let failOnce = true
  await page.route('**/api/v1/paged/jobs?*', async route => {
    if (failOnce) {
      failOnce = false
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '任务服务暂时不可用' }) })
    } else await route.continue()
  })
  await page.reload()
  await expect(page.getByRole('navigation', { name: '平台导航' })).toBeVisible()
  await expect(page.locator('.startup-error')).toContainText('任务服务暂时不可用')
  expect(await page.evaluate(() => localStorage.getItem('rag_token'))).toBe(savedToken)
  await page.getByRole('button', { name: '重新加载课程空间' }).click()
  await expect(page.locator('.startup-error')).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: '平台导航' })).toBeVisible()
})

test('真正失效的登录清理令牌并要求重新登录', async ({ page }) => {
  await login(page, 'admin', 'admin123')
  await page.route('**/api/v1/auth/me', route => route.fulfill({
    status: 401, contentType: 'application/json', body: JSON.stringify({ detail: '请先登录。' }),
  }))
  await page.reload()
  await expect(page.getByRole('heading', { name: '欢迎回到课程空间' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('登录已过期')
  expect(await page.evaluate(() => localStorage.getItem('rag_token'))).toBeNull()
})

import {expect,test,type Page} from '@playwright/test'
import {randomUUID} from 'node:crypto'

async function login(page:Page,role:string){
  await page.goto('/');await page.getByLabel('登录账号',{exact:true}).fill(role)
  await page.getByPlaceholder('输入登录密码',{exact:true}).fill(role+'123')
  await page.getByRole('checkbox',{name:'7天免登录'}).check()
  await page.getByRole('button',{name:'登录课程空间',exact:true}).click()
  await expect(page.getByRole('navigation',{name:'平台导航'})).toBeVisible()
  const budget=await page.request.get('/api/v1/auth/me')
  if(budget.status()===429||Number(budget.headers()['x-ratelimit-remaining']||300)<160){
    test.setTimeout(test.info().timeout+65000)
    await page.waitForTimeout(30000);await page.waitForTimeout(30000);await page.waitForTimeout(1000)
    await page.reload();await expect(page.getByRole('navigation',{name:'平台导航'})).toBeVisible()
  }
  await page.keyboard.press('Escape')
}
async function fit(page:Page){expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy()}
test('浏览器免登录续期、设备列表和注销',async({page})=>{
  await login(page,'student');expect(await page.evaluate(()=>localStorage.getItem('rag_token'))).toBeNull()
  const cookies=await page.context().cookies();expect(cookies.some(c=>c.name.startsWith('rag_refresh_')&&c.httpOnly)).toBeTruthy()
  await page.reload();await expect(page.getByRole('navigation',{name:'平台导航'})).toBeVisible()
  await page.getByRole('button',{name:'打开个人中心',exact:true}).click()
  const center=page.getByRole('dialog',{name:'个人中心',exact:true});await expect(center.getByRole('heading',{name:'登录设备'})).toBeVisible()
  await expect(center.locator('.device-sessions article').filter({hasText:'当前设备'})).toBeVisible();await fit(page)
  await center.getByRole('button',{name:'关闭窗口',exact:true}).click()
  await page.getByRole('button',{name:'退出',exact:true}).click()
  await expect(page.getByRole('button',{name:'登录课程空间',exact:true})).toBeVisible()
  expect((await page.request.post('/api/v1/auth/refresh')).status()).toBe(401)
})
test('管理员评测等待提示、报告下载和筛选日志导出',async({page})=>{
  test.setTimeout(120000);await login(page,'admin')
  await page.getByRole('navigation',{name:'平台导航'}).getByRole('button',{name:'管理控制台'}).click()
  await page.getByRole('button',{name:'质量评测',exact:true}).click()
  const work=page.locator('.evaluation-workbench');await expect(work.getByRole('combobox',{name:'评测题集'})).toBeVisible()
  await work.getByRole('combobox',{name:'评测题集'}).selectOption('http')
  let delayed=false
  await page.route('**/api/v1/admin/evaluation-tasks',async route=>{if(route.request().method()==='POST'&&!delayed){delayed=true;await new Promise(r=>setTimeout(r,1400))}await route.continue()})
  await work.getByRole('button',{name:'开始评测',exact:true}).click();await expect(work.getByText('正在处理…',{exact:true})).toBeVisible()
  await expect(work.locator('.eval-tasks').getByText('报告已保存').first()).toBeVisible({timeout:90000})
  await expect(work.locator('.eval-report').first()).toContainText('mdn-http')
  const download=page.waitForEvent('download');await work.locator('.eval-report').first().getByRole('button',{name:'下载报告',exact:true}).click();expect((await download).suggestedFilename()).toMatch(/^evaluation-.*\.json$/)
  await work.locator('.eval-report').first().getByRole('button',{name:'指标详情'}).click();await expect(page.getByRole('dialog',{name:'评测指标详情'})).toContainText('引用精度');await page.keyboard.press('Escape');await fit(page)
  await page.getByRole('button',{name:'安全与运行',exact:true}).click()
  const exports=page.locator('.data-exports');await exports.getByLabel('操作人或操作名称').fill('start_evaluation')
  const logs=page.waitForEvent('download');await exports.getByRole('button',{name:'下载日志 CSV'}).click();expect((await logs).suggestedFilename()).toBe('audit-logs.csv');await fit(page)
})
test('教师资料版本预览与恢复、课程成绩导出',async({page})=>{
  test.setTimeout(90000);await login(page,'teacher')
  const context=await page.evaluate(()=>({cookie:document.cookie}));expect(context.cookie).not.toContain('rag_refresh_')
  async function post(path:string,data:any){const r=await page.request.post('/api/v1'+path,{data});expect(r.ok(),path).toBeTruthy();return r.json()}
  const id=randomUUID().slice(0,8),title='资料版本验收'+id
  const course=await post('/courses',{code:'REM-'+id,title,status:'published'})
  const base=await post('/knowledge-bases',{name:title,course:title})
  await post(`/courses/${course.id}/knowledge-bases`,{knowledge_base_id:base.id})
  let doc:any
  for(const text of ['Version one: stack uses last-in first-out order.','Version two: queue uses first-in first-out order.'])doc=(await post(`/knowledge-bases/${base.id}/text-documents`,{document_id:'rem-'+id,title:'版本验证教材',source_url:'https://example.org/isolated',license_name:'隔离验收自写文本',license_url:'https://example.org/isolated',version_label:'test',publication_status:'published',pages:[{page_number:1,text}]})).document
  await page.reload();await expect(page.getByRole('navigation',{name:'平台导航'})).toBeVisible()
  await page.getByRole('navigation',{name:'平台导航'}).getByRole('button',{name:'教学课程'}).click()
  await page.locator('.course-directory').getByPlaceholder('课程名称、代码或学期').fill(title)
  await page.locator('.course-directory').getByRole('button',{name:'搜索',exact:true}).click()
  await page.locator('.course-card').filter({hasText:title}).click()
  const courseDialog=page.locator('dialog:has(nav[aria-label="课程详情栏目"])')
  const download=page.waitForEvent('download');await courseDialog.getByRole('button',{name:'导出作业成绩'}).click();expect((await download).suggestedFilename()).toContain('course-grades-')
  await page.getByRole('navigation',{name:'课程详情栏目'}).getByRole('button',{name:'资料与知识点'}).click()
  await courseDialog.locator('.course-detail-item').filter({hasText:'版本验证教材'}).click()
  await page.getByRole('button',{name:'资料信息',exact:true}).click()
  await page.getByRole('button',{name:'版本记录与恢复'}).click()
  const versions=page.getByRole('dialog',{name:'资料版本记录',exact:true});await expect(versions.locator('.version-list article')).toHaveCount(2)
  await versions.locator('.version-list article').filter({hasText:'内容版本 1'}).getByRole('button',{name:'查看',exact:true}).click();await expect(versions).toContainText('Version one')
  await versions.getByRole('button',{name:'恢复这个版本'}).click();await page.getByRole('dialog',{name:'恢复资料内容？'}).getByRole('button',{name:'确认恢复内容'}).click()
  await expect(versions).not.toBeVisible();await page.getByRole('button',{name:'原文阅读',exact:true}).click();await expect(page.locator('.document-reading-page')).toContainText('Version one');await fit(page)
  const r=await page.request.get(`/api/v1/documents/${doc.id}/versions`);expect((await r.json()).current_revision).toBe(3)
})

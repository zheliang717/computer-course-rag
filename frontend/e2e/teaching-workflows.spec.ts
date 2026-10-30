import { expect, test, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { dayKey, addDays, monday } from '../src/timetable'

test.beforeAll(async({request})=>{await expect.poll(async()=>{try{return (await request.get('/health')).status()}catch{return 0}},{timeout:45000}).toBe(200)})

const pageTokens=new WeakMap<Page,Map<string,string>>()
async function token(page:Page,role:string) {
  let cache=pageTokens.get(page);if(!cache){cache=new Map();pageTokens.set(page,cache)}
  if(cache.has(role))return cache.get(role)!
  let username=role,password=role+'123'
  if(role==='teacher') {
    // Each scenario gets a distinct timetable owner. Retained prior QA sessions
    // must not fill this teacher's candidate window or weaken conflict checks.
    const a=await token(page,'admin');username='workflow_'+randomUUID().slice(0,8);password='isolated-workflow-2026'
    const created=await page.request.post('/api/v1/admin/users',{headers:headers(a),data:{username,password,display_name:'工作流核对教师',role:'teacher'}})
    expect(created.status()).toBe(201)
  }
  const r=await page.request.post('/api/v1/auth/login',{data:{username,password}})
  expect(r.status()).toBe(200);const value=(await r.json()).access_token as string;cache.set(role,value);return value
}
const headers=(value:string)=>({Authorization:'Bearer '+value})
async function enter(page:Page,value:string) {
  const owner=JSON.parse(Buffer.from(value.split('.')[0]!,'base64url').toString()).sub
  await page.addInitScript(({value,owner})=>{localStorage.setItem('rag_token',value);localStorage.setItem('rag_update_notice:'+owner,'2026-10-29-zhixue-assistant')},{value,owner})
  await page.goto('/');await expect(page.getByRole('navigation',{name:'平台导航'})).toBeVisible()
}
async function create(page:Page,teacher:string) {
  const suffix=randomUUID().slice(0,8),name='教学工作验收-'+suffix,semester='工作流学期-'+suffix
  const r=await page.request.post('/api/v1/courses',{headers:headers(teacher),data:{title:name,code:'WORK-'+suffix,semester,status:'published',description:'原课程介绍'}})
  expect(r.status()).toBe(201);return {...await r.json(),semester}
}
async function open(page:Page,course:any,admin=false,schedule=false) {
  await page.getByRole('navigation',{name:'平台导航'}).getByRole('button',{name:admin?'课程与资料':'教学课程'}).click()
  await page.getByRole('button',{name:schedule?(admin?'AI 辅助排课':'AI 调课申请'):'资料选题与课程 AI 工具',exact:true}).click()
  const work=page.getByRole('dialog',{name:admin?'AI 管理工作间':'AI 教学工作间',exact:true})
  await work.getByRole('combobox',{name:'当前课程',exact:true}).selectOption(course.id)
  return work
}
function pdf() {
  const lines=['1. Which structure uses LIFO?','A. Stack','B. Queue','2. Explain binary search.']
  const stream='BT /F1 12 Tf 50 750 Td '+lines.map((x,i)=>(i?'0 -20 Td ':'')+'('+x+') Tj').join('\n')+' ET\n'
  const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',`<< /Length ${stream.length} >>\nstream\n${stream}endstream`,'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
  let text='%PDF-1.4\n';const offsets:number[]=[]
  objects.forEach((x,i)=>{offsets.push(text.length);text+=`${i+1} 0 obj\n${x}\nendobj\n`})
  const xref=text.length;text+=`xref\n0 6\n0000000000 65535 f \n${offsets.map(x=>String(x).padStart(10,'0')+' 00000 n \n').join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(text,'ascii')
}
async function fit(page:Page,dialog:any,info:any,name:string) {
  const width=page.viewportSize()!.width
  const actual=await page.evaluate(()=>({root:document.documentElement.scrollWidth,dialogs:[...document.querySelectorAll('dialog[open]')].map(x=>x.getBoundingClientRect().width)}))
  expect(actual.root).toBeLessThanOrEqual(width+2)
  expect(actual.dialogs.every(x=>x<=width+2)).toBeTruthy()
  await page.screenshot({path:info.outputPath(name+'.png')})
}

test('教师专用PDF原题识别、修订选编、确认入库与原文出处',async({page},info)=>{
  test.setTimeout(120000)
  const t=await token(page,'teacher'),student=await token(page,'student'),course=await create(page,t)
  await enter(page,t);const work=await open(page,course)
  await work.getByRole('button',{name:'上传教师资料',exact:true}).click()
  await work.getByLabel('资料名称',{exact:true}).fill('数据结构课程习题选编')
  await work.getByLabel('文字型 PDF',{exact:true}).setInputFiles({name:'exercises.pdf',mimeType:'application/pdf',buffer:pdf()})
  await work.getByRole('button',{name:'保存教师资料',exact:true}).click()
  await expect(work.getByRole('status').filter({hasText:'教师资料已保存'})).toBeVisible()
  const list=await (await page.request.get(`/api/v1/courses/${course.id}/teacher-resources`,{headers:headers(t)})).json()
  const resource=list.items[0]
  expect(resource.title).toBe('数据结构课程习题选编')
  expect((await page.request.get(`/api/v1/courses/${course.id}/teacher-resources`,{headers:headers(student)})).status()).toBe(404)
  expect(await (await page.request.get(`/api/v1/courses/${course.id}/knowledge-bases`,{headers:headers(t)})).json()).toEqual([])
  await work.getByRole('button',{name:'识别所选页原题',exact:true}).click()
  await expect(work.locator('.work-candidate')).toHaveCount(2,{timeout:45000})
  const row=work.locator('.work-candidate').filter({hasText:'Which structure uses LIFO?'})
  await row.locator('.work-candidate-heading button').click()
  await row.getByLabel('参考答案',{exact:true}).fill('A')
  await row.getByLabel('解析',{exact:true}).fill('A stack follows last-in-first-out order.')
  await row.getByRole('checkbox',{name:/选择题目/}).check()
  await work.getByRole('checkbox',{name:'已核对所选原题，保存为待审核题目草稿'}).check()
  await fit(page,work,info,'material-question-review')
  const saved=page.waitForResponse(r=>r.url().endsWith('/questions')&&r.request().method()==='POST'&&r.url().includes('/teaching-workflows/'))
  await work.getByRole('button',{name:'保存所选 1 题到草稿',exact:true}).click()
  const response=await saved;expect(response.status()).toBe(200);const {draft_id}=await response.json()
  await expect(work).toHaveCount(0)
  await expect(page.getByRole('dialog',{name:'数据结构课程习题选编 · 题目选编',exact:true})).toBeVisible()
  const update=await page.request.patch(`/api/v1/teaching-drafts/${draft_id}`,{headers:headers(t),data:{status:'confirmed'}})
  expect(update.status()).toBe(200)
  const published=await page.request.post(`/api/v1/teaching-drafts/${draft_id}/publish-questions`,{headers:headers(t)})
  expect(published.status()).toBe(200)
  const qs=await (await page.request.get(`/api/v1/questions?course_id=${course.id}`,{headers:headers(t)})).json()
  const q=qs.find((x:any)=>x.stem.includes('Which structure uses LIFO'))
  expect(q).toBeTruthy()
  const origin=await (await page.request.get(`/api/v1/questions/${q.id}/source`,{headers:headers(t)})).json()
  expect(origin.title).toBe('数据结构课程习题选编');expect(origin.spans[0].page_number).toBe(1)
  expect((await page.request.get(`/api/v1/questions/${q.id}/source`,{headers:headers(student)})).status()).toBe(404)
})

test('课程AI建议选择采纳、课程草稿及章节归档恢复',async({page},info)=>{
  test.setTimeout(120000)
  const t=await token(page,'teacher'),course=await create(page,t)
  await enter(page,t);const work=await open(page,course)
  await work.getByRole('button',{name:'课程完善',exact:true}).click()
  await work.getByLabel('希望 AI 帮你完善什么',{exact:true}).fill('完善课程学习目标和教学大纲，原课程介绍保留。')
  await work.getByRole('button',{name:'生成课程完善建议',exact:true}).click()
  await expect(work.getByLabel('建议学习目标',{exact:true})).toBeVisible({timeout:45000})
  await work.getByLabel('建议学习目标',{exact:true}).fill('- 能解释检索与证据定位')
  await work.getByRole('checkbox',{name:'采纳学习目标',exact:true}).check()
  await work.getByRole('checkbox',{name:/追加以下章节与知识点/}).check()
  await work.getByRole('checkbox',{name:'已核对勾选内容，写入课程草稿'}).check()
  await work.getByRole('button',{name:'采纳到课程草稿',exact:true}).click()
  await expect(work).toContainText('建议已写入课程草稿，尚未发布。')
  const live=await (await page.request.get(`/api/v1/courses/${course.id}`,{headers:headers(t)})).json()
  expect(live.learning_objectives).toBe('');expect(live.description).toBe('原课程介绍')
  await work.getByRole('button',{name:'前往课程草稿核对与发布 ↗',exact:true}).click()
  const editor=page.getByRole('dialog',{name:'编辑课程',exact:true})
  await expect(editor.getByLabel('学习目标',{exact:true})).toHaveValue('- 能解释检索与证据定位')
  await editor.getByRole('button',{name:'教学大纲',exact:true}).click()
  await editor.locator('.course-editor-card>summary:visible').filter({hasText:'检索与证据基础'}).click()
  await editor.getByRole('button',{name:'归档章节',exact:true}).click()
  await editor.getByRole('button',{name:'保存草稿',exact:true}).click()
  await editor.getByRole('button',{name:'发布预览',exact:true}).first().click()
  await editor.getByRole('checkbox',{name:'已核对课程内容，确认更新课程展示内容'}).check()
  await fit(page,editor,info,'course-ai-draft-archive')
  await editor.getByRole('button',{name:'确认发布内容',exact:true}).click()
  await expect(editor).toContainText('课程内容已更新')
  expect((await (await page.request.get(`/api/v1/courses/${course.id}`,{headers:headers(t)})).json()).sections).toHaveLength(0)
  await editor.getByRole('button',{name:'教学大纲',exact:true}).click()
  await editor.getByRole('button',{name:'恢复章节',exact:true}).click()
  await editor.getByRole('button',{name:'保存草稿',exact:true}).click()
  await editor.getByRole('button',{name:'发布预览',exact:true}).first().click()
  await editor.getByRole('checkbox',{name:'已核对课程内容，确认更新课程展示内容'}).check()
  await editor.getByRole('button',{name:'确认发布内容',exact:true}).click()
  await expect(editor).toContainText('课程内容已更新')
  expect((await (await page.request.get(`/api/v1/courses/${course.id}`,{headers:headers(t)})).json()).sections).toHaveLength(1)
})

async function rooms(page:Page,admin:string,course:any) {
  const h=headers(admin),code='WL-'+course.code.slice(-8),name='教学机房-'+course.code.slice(-8)
  const calendar=await page.request.put('/api/v1/timetable/calendar',{headers:h,data:{semester:course.semester,start_date:monday(dayKey()),end_date:addDays(dayKey(),20),holidays:[],rooms:[name],expected_revision:0}})
  expect(calendar.status(),await calendar.text()).toBe(200)
  const resource=await page.request.put('/api/v1/timetable/resources',{headers:h,data:{semester:course.semester,expected_revision:0,resource_mode:'advisory',rooms:[{code,name,capacity:40,equipment:['计算机','投影'],kind:'computer_lab',specialty:'计算机'}],availability:[],requirements:[]}})
  expect(resource.status()).toBe(200);return {code,name}
}

test('管理员AI排课方案不自动生效，确认后新增课次并通知',async({page},info)=>{
  test.setTimeout(120000)
  const t=await token(page,'teacher'),a=await token(page,'admin'),course=await create(page,t)
  await rooms(page,a,course);await enter(page,a);const work=await open(page,course,true,true)
  await work.getByLabel('排课需求',{exact:true}).fill('请优先机房，安排两次课程，避开现有课程。')
  await work.getByRole('button',{name:'让 AI 准备排课方案',exact:true}).click()
  await expect(work.locator('.work-plan')).not.toHaveCount(0,{timeout:45000})
  const before=await (await page.request.get(`/api/v1/courses/${course.id}/sessions`,{headers:headers(a)})).json()
  expect(before).toHaveLength(0)
  await work.getByRole('button',{name:'核对条件 / 重新计算预览',exact:true}).click()
  await work.getByLabel('预览开始时间',{exact:true}).fill('09:00')
  await work.getByRole('button',{name:'重新计算方案',exact:true}).click()
  await expect(work).toContainText('已重新计算预览，课表尚未改变。')
  await expect(work.locator('.work-conditions')).toContainText('09:00')
  await expect(work.locator('.work-plan-lesson')).toHaveCount(2)
  await work.getByLabel('调整说明',{exact:true}).fill('管理员核对新增课程安排')
  await work.getByRole('checkbox',{name:'已核对所有课次与影响，确认更新课表'}).check()
  await fit(page,work,info,'ai-schedule-preview')
  await work.getByRole('button',{name:'确认应用排课方案',exact:true}).click()
  await expect(work).toContainText('已按确认方案更新课表')
  const after=await (await page.request.get(`/api/v1/courses/${course.id}/sessions`,{headers:headers(a)})).json()
  expect(after).toHaveLength(2)
  const notices=await (await page.request.get(`/api/v1/courses/${course.id}/announcements`,{headers:headers(a)})).json()
  expect(notices.some((x:any)=>x.title==='课程安排更新')).toBeTruthy()
})

test('教师AI调课只提交申请，管理员审批后才修改课表',async({page},info)=>{
  test.setTimeout(120000)
  const t=await token(page,'teacher'),a=await token(page,'admin'),course=await create(page,t),room=await rooms(page,a,course)
  const created=await page.request.post(`/api/v1/courses/${course.id}/sessions`,{headers:headers(a),data:{title:'待调课次',session_date:addDays(dayKey(),15)+'T21:00:00+08:00',duration_minutes:60,location:room.name}})
  expect(created.status()).toBe(201);const lesson=await created.json()
  await enter(page,t);const work=await open(page,course,false,true)
  await work.locator('.work-lesson').filter({hasText:'待调课次'}).getByRole('checkbox').check()
  await work.getByLabel('候选开始日期',{exact:true}).fill(addDays(dayKey(),3))
  await work.getByLabel('候选结束日期',{exact:true}).fill(addDays(dayKey(),7))
  await work.getByRole('button',{name:'让 AI 准备调课方案',exact:true}).click()
  await expect(work.locator('.work-plan')).not.toHaveCount(0,{timeout:45000})
  await work.getByLabel('调整说明',{exact:true}).fill('教师教学安排需要调整')
  await work.getByRole('checkbox',{name:'已核对方案，确认提交调课申请'}).check()
  await fit(page,work,info,'teacher-schedule-request')
  const applied=page.waitForResponse(r=>r.url().includes('/teaching-workflows/')&&r.url().endsWith('/schedule')&&r.request().method()==='POST')
  await work.getByRole('button',{name:'确认提交调课申请',exact:true}).click()
  const response=await applied;expect(response.status()).toBe(200);const body=await response.json()
  await expect(work).toContainText('待管理员审批；课表尚未改变')
  const pending=await (await page.request.get(`/api/v1/courses/${course.id}/sessions`,{headers:headers(t)})).json()
  expect(pending[0].session_date).toBe(lesson.session_date)
  const approval=await page.request.post(`/api/v1/timetable/requests/${body.request_id}/review`,{headers:headers(a),data:{approved:true,reason:'管理员核对后批准调课',confirmed:true}})
  expect(approval.status()).toBe(200)
  const after=await (await page.request.get(`/api/v1/courses/${course.id}/sessions`,{headers:headers(t)})).json()
  expect(after[0].session_date).not.toBe(lesson.session_date)
})

test('管理员助手自然语言需求进入排课工作流，不假称已经执行',async({page})=>{
  const a=await token(page,'admin');await enter(page,a)
  await page.locator('.assistant-fab').click()
  const assistant=page.locator('#global-ai-assistant')
  await assistant.getByLabel('向 AI 助手提问',{exact:true}).fill('请帮我安排课程，优先机房并避开已有课程。')
  await assistant.getByRole('button',{name:'发送 ↗',exact:true}).click()
  const work=page.getByRole('dialog',{name:'AI 管理工作间',exact:true})
  await expect(work.getByLabel('排课需求',{exact:true})).toHaveValue('请帮我安排课程，优先机房并避开已有课程。')
  await expect(work.locator('.workbench-tabs button.active')).toHaveText('排课助手')
  await expect(work).toContainText('确认前不更改任何课表。')
})

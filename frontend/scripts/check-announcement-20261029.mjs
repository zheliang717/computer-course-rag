// Read-only announcement publication checks. Never creates academic data.
import { chromium, expect } from '@playwright/test'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'

const root=fileURLToPath(new URL('../../',import.meta.url))
const report=root+'reports/update-announcement-20261029/'
mkdirSync(report,{recursive:true})
const markdown=readFileSync(root+'docs/changelog/2026-10-29.md','utf8')
const accounts=Object.fromEntries(JSON.parse(readFileSync(root+'.private/funnel/accounts.json','utf8')).map(u=>[u.username,u.password]))
const releaseId='2026-10-29-zhixue-assistant'
if(/本机|公网|测试|未完善|未完成|待完成|迁移|回归|验收|部署|UX\d|V0\./.test(markdown))throw new Error('Announcement includes internal content')
const browser=await chromium.launch({channel:'chrome',headless:true})
const checks=[]
try {
  for(const [target,base]of [['local','http://127.0.0.1:5173'],['https','https://zhixue-preview.taile00702.ts.net']]){
    for(const role of ['student','teacher','admin']){
      const mobile=target==='https'&&role==='student'
      const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,hasTouch:mobile})
      try{
        const login=await context.request.post(base+'/api/v1/auth/login',{data:{username:role,password:target==='https'?accounts[role]:role+'123'}})
        if(login.status()!==200)throw new Error(`Login check failed: ${role} ${target} ${login.status()}`)
        const data=await login.json(),owner=data.user.id
        await context.addInitScript(({owner})=>{
          const key='rag_update_notice:'+owner
          if(localStorage.getItem(key)===null)localStorage.setItem(key,'2026-10-28-zhixue-assistant')
        },{owner})
        const page=await context.newPage();page.setDefaultTimeout(15000)
        await page.goto(base,{waitUntil:'commit',timeout:45000})
        const dialog=page.getByRole('dialog',{name:'智学助手更新公告',exact:true})
        await expect(dialog).toBeVisible({timeout:90000})
        await expect(dialog.locator('.answer-markdown')).toContainText('个人中心新增“登录设备”',{timeout:45000})
        await expect(page.locator('.platform-update-entry')).toContainText('10月29日')
        expect(await page.evaluate(owner=>localStorage.getItem('rag_update_notice:'+owner),owner)).toBe(releaseId)
        expect(await dialog.locator('details, .answer-outline').count()).toBe(0)
        const downloadPromise=page.waitForEvent('download')
        await dialog.getByRole('link',{name:'下载更新日志'}).click()
        const download=await downloadPromise
        expect(download.suggestedFilename()).toBe('智学助手_更新日志_2026-10-29.md')
        expect(readFileSync(await download.path(),'utf8')).toBe(markdown)
        const layout=await dialog.evaluate(node=>({width:innerWidth,scroll:document.documentElement.scrollWidth,frame:node.querySelector('.detail-dialog-frame')?.getBoundingClientRect().width}))
        expect(layout.scroll).toBeLessThanOrEqual(layout.width+1)
        const close=dialog.getByRole('button',{name:'关闭更新公告',exact:true}),first=await close.boundingBox()
        await dialog.locator('.detail-dialog-body').evaluate(node=>{node.scrollTop=node.scrollHeight})
        const last=await close.boundingBox();expect(Math.abs(first.y-last.y)).toBeLessThanOrEqual(2)
        if(target==='https'&&role==='student'||target==='local'&&role==='admin')await page.screenshot({path:report+(mobile?'announcement-mobile.png':'announcement-desktop.png'),fullPage:true})
        await dialog.getByRole('button',{name:'知道了',exact:true}).click()
        await expect(dialog).toHaveCount(0)
        await page.reload({waitUntil:'commit',timeout:45000})
        await expect(page.getByRole('navigation',{name:'平台导航'})).toBeVisible({timeout:90000})
        await expect(page.locator('.page-loading-feedback')).toHaveCount(0,{timeout:45000})
        await expect(dialog).toHaveCount(0)
        await page.locator('.platform-update-entry').click()
        await expect(dialog).toBeVisible();await expect(dialog).toContainText('请刷新页面加载本次更新。')
        await context.request.post(base+'/api/v1/auth/logout')
        checks.push({target,role,mobile,old_notice_replaced:true,acknowledgement_persists:true,reopen:true,download_matches:true,no_outline:true,close_fixed:true,layout,status:'passed'})
        console.log(`Announcement verified: ${target} ${role}${mobile?' mobile':''}`)
      } finally{await context.request.post(base+'/api/v1/auth/logout').catch(()=>{});await context.close()}
    }
  }
}finally{
  writeFileSync(report+'check.json',JSON.stringify({passed:checks.length===6,frontend:'UX19.1',api:'0.30.57',migration:'20261029_0045',announcement_id:releaseId,document:'docs/changelog/2026-10-29.md',content_sha256:createHash('sha256').update(markdown).digest('hex'),checked_at:new Date().toISOString(),checks},null,2))
  await browser.close()
}

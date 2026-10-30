import { chromium, expect } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'

const base='http://127.0.0.1:18086', report='../reports/project-audit-20261029'
const browser=await chromium.launch({channel:'chrome',headless:true})
const setup=await browser.newContext()
const login=async(name,password)=>{
  const r=await setup.request.post(base+'/api/v1/auth/login',{data:{username:name,password}})
  expect(r.status()).toBe(200);return(await r.json()).access_token
}
const root=await login('admin','admin123'),suffix=randomUUID().slice(0,8),password='isolated responsive audit 2026'
const rows=[],issues=[]
try {
  for(const role of ['student','teacher','admin']) {
    const name='responsive_'+role+'_'+suffix
    const created=await setup.request.post(base+'/api/v1/admin/users',{headers:{Authorization:'Bearer '+root},data:{username:name,display_name:'界面核对'+role,role,password,confirmed:true}})
    expect(created.status()).toBe(201)
    const token=await login(name,password),owner=JSON.parse(Buffer.from(token.split('.')[0],'base64url').toString()).sub
    for(const viewport of [{width:320,height:640},{width:390,height:844},{width:844,height:390}]) {
      const context=await browser.newContext({viewport,isMobile:true,hasTouch:true})
      await context.addInitScript(({token,owner})=>{localStorage.setItem('rag_token',token);localStorage.setItem('rag_update_notice:'+owner,'2026-10-28-zhixue-assistant')},{token,owner})
      const page=await context.newPage();page.setDefaultTimeout(10000)
      const row={role,viewport,checks:[],issues:[]};rows.push(row)
      try {
        await page.goto(base)
        await expect(page.getByRole('navigation',{name:'平台导航'})).toBeVisible({timeout:45000})
        await expect(page.locator('.page-loading-feedback')).toHaveCount(0,{timeout:45000})
        row.homeOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)
        if(row.homeOverflow>2)row.issues.push('homepage horizontal overflow')
        await page.locator('button.profile-entry:visible').first().click()
        const profile=page.getByRole('dialog',{name:'个人中心',exact:true})
        await expect(profile.getByLabel('姓名',{exact:true})).toBeVisible()
        if(viewport.width===390) {
          await profile.getByLabel('姓名',{exact:true}).fill('界面资料核对'+role)
          await profile.getByRole('button',{name:'保存资料',exact:true}).click()
          await expect(profile.getByRole('status')).toContainText('已保存')
          await profile.getByLabel('选择头像图片',{exact:true}).setInputFiles('../reports/update-announcement-20261028/announcement-mobile.png')
          await expect(profile.getByRole('button',{name:'保存头像',exact:true})).toBeVisible()
          await profile.getByRole('button',{name:'保存头像',exact:true}).click()
          await expect(profile.getByRole('button',{name:'恢复默认',exact:true})).toBeVisible()
          await profile.getByRole('button',{name:'恢复默认',exact:true}).click()
          await page.getByRole('dialog',{name:'恢复默认头像？',exact:true}).getByRole('button',{name:'确认恢复默认',exact:true}).click()
          await expect(profile.getByRole('button',{name:'恢复默认',exact:true})).toHaveCount(0)
          row.checks.push('profile edit / avatar crop save / default restore')
        }
        await profile.getByRole('button',{name:'关闭窗口',exact:true}).click()
        await page.locator('.assistant-fab').click()
        const assistant=page.locator('#global-ai-assistant')
        await expect(assistant).toBeVisible()
        row.assistant=await assistant.evaluate(e=>{
          const box=e.getBoundingClientRect(),chat=e.querySelector('.assistant-chat-scroll').getBoundingClientRect(),composer=e.querySelector('.assistant-composer').getBoundingClientRect()
          return {width:box.width,height:box.height,scrollWidth:e.scrollWidth,chatHeight:chat.height,chatRatio:chat.height/innerHeight,composerBottom:composer.bottom}
        })
        if(row.assistant.chatHeight<150||row.assistant.chatRatio<.4)row.issues.push('assistant conversation area too short')
        if(row.assistant.composerBottom>viewport.height+2)row.issues.push('assistant composer below viewport')
        if(row.assistant.scrollWidth>row.assistant.width+2)row.issues.push('assistant horizontal overflow')
        let release;const gate=new Promise(resolve=>release=resolve)
        await page.route('**/api/v1/questions/ask/stream',async route=>{await gate;await route.abort()})
        await assistant.getByRole('textbox',{name:'向 AI 助手提问',exact:true}).fill('请解释一下栈的后进先出')
        await assistant.getByRole('button',{name:'发送 ↗',exact:true}).click()
        await expect(assistant.locator('.assistant-thinking')).toBeVisible()
        row.animation=await assistant.locator('.assistant-thinking .assistant-typing-dots i').first().evaluate(e=>({name:getComputedStyle(e).animationName,duration:getComputedStyle(e).animationDuration}))
        await page.screenshot({path:`${report}/responsive-${role}-${viewport.width}x${viewport.height}.png`})
        if(row.animation.name==='none')row.issues.push('waiting indicator has no animation')
        release();row.checks.push('assistant open / waiting indicator / visible composer')
      } catch(error) {
        row.issues.push(error.name+': '+error.message.split('\n')[0])
        await page.screenshot({path:`${report}/responsive-${role}-${viewport.width}x${viewport.height}-failure.png`}).catch(()=>{})
      } finally {await context.close()}
      if(row.issues.length)issues.push({role,viewport,issues:row.issues})
    }
  }
} finally {
  await setup.close();await browser.close()
  writeFileSync(report+'/responsive.json',JSON.stringify({rows,issues,cloud_calls:0,scope:'fresh isolated accounts; empty-state home, account/avatar and assistant at three viewports'},null,2))
}
console.log(JSON.stringify({scenarios:rows.length,issues},null,2))

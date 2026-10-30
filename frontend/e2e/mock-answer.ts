import type { Page, Route } from '@playwright/test'
import { randomUUID } from 'node:crypto'

/** Model fault fixtures speak the real SSE + durable-receipt protocol. */
export async function mockAnswer(page: Page, handler: (route: Route) => unknown) {
  const receipts=new Map<string,unknown>()
  await page.route('**/api/v1/answer-requests/*', route=>{
    const id=new URL(route.request().url()).pathname.split('/').at(-1)!
    return receipts.has(id) ? route.fulfill({contentType:'application/json',body:JSON.stringify(receipts.get(id))}) : route.continue()
  })
  await page.route('**/api/v1/questions/ask/stream', route=>handler(new Proxy(route,{
    get(target,key){
      if(key==='fulfill')return async (options: {status?:number;body?:string;contentType?:string})=>{
        const body=route.request().postDataJSON(), id=body.request_id, value=JSON.parse(options.body || '{}')
        if((options.status || 200)>=400){
          receipts.set(id,{request_id:id,status:'failed',question:body.question,context:body,answer:null,
            error_status:options.status,message:value.detail,can_retry:true,created_at:new Date().toISOString(),updated_at:new Date().toISOString(),finished_at:new Date().toISOString()})
          return route.fulfill(options)
        }
        value.history_id ||= randomUUID()
        return route.fulfill({status:200,contentType:'text/event-stream',body:'event: stage\ndata: '+JSON.stringify({label:'正在生成…'})+'\n\nevent: delta\ndata: '+JSON.stringify({text:value.answer})+'\n\nevent: done\ndata: '+JSON.stringify(value)+'\n\n'})
      }
      const value=Reflect.get(target,key);return typeof value==='function'?value.bind(target):value
    }
  })))
}

/** Retain only a UUID + digest through an uncertain POST, never teaching data. */
export async function prepareTeacherTask(owner: string, body: Record<string, unknown>) {
  const payload = JSON.stringify({kind:body.kind || 'teaching_draft',payload:body.payload})
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(payload))
  const digest=Array.from(new Uint8Array(bytes)).map(v=>v.toString(16).padStart(2,'0')).join('')
  const key='rag:pending-teacher-task:'+owner+':'+String(body.kind || 'teaching_draft')
  let previous: {id?:string;digest?:string}|null=null
  try {previous=JSON.parse(sessionStorage.getItem(key)||'null')}catch{/* Optional browser storage. */}
  const id=previous?.digest===digest && /^[0-9a-f-]{36}$/i.test(previous.id || '') ? previous.id! : crypto.randomUUID()
  try{sessionStorage.setItem(key,JSON.stringify({id,digest}))}catch{/* The server still guards this UUID. */}
  return {body:JSON.stringify({...body,request_id:id}),acknowledge:()=>{
    try{if(JSON.parse(sessionStorage.getItem(key)||'null')?.id===id)sessionStorage.removeItem(key)}catch{/* Optional storage. */}
  }}
}

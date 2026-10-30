export async function downloadFile(base:string,token:string,path:string){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),60000)
  try{const r=await fetch(base+'/api/v1'+path,{headers:{Authorization:'Bearer '+token},signal:controller.signal})
    if(!r.ok){const d=await r.json().catch(()=>null);throw new Error(typeof d?.detail==='string'?d.detail:'下载失败，请重试。')}
    const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url
    a.download=/filename="([^"]+)"/.exec(r.headers.get('content-disposition')||'')?.[1]||'report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000)
  }catch(e){if(e instanceof DOMException&&e.name==='AbortError')throw new Error('下载超时，请缩小范围后重试。');throw e}finally{clearTimeout(timer)}
}

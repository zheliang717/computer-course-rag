from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

class Restore(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=0)
    expected_revision:int=Field(ge=0)
    confirmed:bool=False

def document_version_router(service,current_user,catalog,base_access):
    router=APIRouter(prefix='/api/v1/documents')
    def manager(docid,user):
        if user.role not in ('teacher','admin'):raise HTTPException(403,'资料版本由教师或管理员维护。')
        if service is None or catalog is None:raise HTTPException(503,'资料版本需要持久化存储。')
        doc=catalog.get_document(docid)
        if not doc:raise HTTPException(404,'资料不存在。')
        base_access(doc[0].knowledge_base_id,user)
    def call(fn):
        try:return fn()
        except LookupError as e:raise HTTPException(404,str(e)) from e
        except ValueError as e:raise HTTPException(409,str(e)) from e
    @router.get('/{docid}/versions')
    def listing(docid:UUID,page:int=Query(1,ge=1),page_size:int=Query(6,ge=1,le=30),user=Depends(current_user)):
        manager(docid,user);return call(lambda:service.list(docid,page,page_size))
    @router.get('/{docid}/versions/{revision}')
    def content(docid:UUID,revision:int,page:int=Query(1,ge=1),page_size:int=Query(6,ge=1,le=30),user=Depends(current_user)):
        manager(docid,user);v=call(lambda:service.get(docid,revision));start=(page-1)*page_size
        return {**service.brief(v),'items':v.pages[start:start+page_size],'total':len(v.pages),'page':page,'page_size':page_size}
    @router.get('/{docid}/versions/{revision}/download')
    def download(docid:UUID,revision:int,user=Depends(current_user)):
        manager(docid,user);v=call(lambda:service.get(docid,revision))
        filename=v.filename+f'_v{revision}'+('.pdf' if v.source_payload else '.md')
        body=v.source_payload or ('# '+v.filename+'\n\n'+'\n\n'.join(f"## 第{p['page_number']}页\n\n{p['content']}" for p in v.pages)).encode('utf-8')
        return Response(body,media_type='application/pdf' if v.source_payload else 'text/markdown;charset=utf-8',headers={'Cache-Control':'private, no-store','Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename)})
    @router.post('/{docid}/versions/restore')
    def restore(docid:UUID,data:Restore,user=Depends(current_user)):
        manager(docid,user)
        if not data.confirmed:raise HTTPException(409,'请确认回退资料内容。')
        return call(lambda:service.restore(docid,data.revision,data.expected_revision,user))
    return router

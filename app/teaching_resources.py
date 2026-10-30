"""Faculty-only PDFs live outside documents/chunks and all student RAG paths."""
from uuid import UUID, uuid4
import re
import pymupdf
from sqlalchemy import select
from app.accounts import AccountService
from app.models import TeacherResource, Document, DocumentPage, CourseKnowledgeBase, AuditLog
from app.pagination import sql_page


class TeachingResources:
    def __init__(self, sessions): self.sessions = sessions

    @staticmethod
    def metadata(row):
        return dict(id=str(row.id), course_id=str(row.course_id), title=row.title, status=row.status,
            page_count=len(row.pages), external_allowed=row.external_allowed, revision=row.revision, created_at=row.created_at)

    @staticmethod
    def owned(s, principal, course_id, resource_id):
        actor = AccountService.actor(s, principal, {'teacher', 'admin'})
        AccountService.manager(s, actor, course_id)
        row = s.scalar(select(TeacherResource).where(TeacherResource.id==resource_id).with_for_update())
        if not row or row.course_id != course_id: raise PermissionError('教师资料不存在或无权访问。')
        return actor, row

    def create(self, principal, course_id, title, payload, external_allowed=False, identifier=None):
        with self.sessions.begin() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'}); AccountService.manager(s, actor, course_id)
        if len(payload) > 30 * 1024 * 1024: raise ValueError('每份教师资料最大30 MB。')
        if not payload.startswith(b'%PDF-'): raise ValueError('请选择有效的文字型 PDF。')
        pages, total = [], 0
        try:
            with pymupdf.open(stream=payload, filetype='pdf') as pdf:
                if pdf.needs_pass or not 1 <= len(pdf) <= 1000: raise ValueError('资料须为未加密、1—1000页的 PDF。')
                for index, page in enumerate(pdf):
                    text = page.get_text('text', sort=True).strip(); total += len(text)
                    if total > 2_000_000: raise ValueError('文字内容过多，请拆分资料后上传。')
                    pages.append(dict(page_number=index + 1, content=text))
        except ValueError: raise
        except Exception as exc: raise ValueError('PDF 无法读取，请检查文件是否完整。') from exc
        if not any(x['content'] for x in pages): raise ValueError('未读到文字；扫描版请先转为可复制文字的 PDF，当前不提供 OCR。')
        title = re.sub(r'\.pdf$', '', title.strip(), flags=re.I).strip()[:200] or '课程出题资料'
        identifier = identifier or uuid4()
        with self.sessions.begin() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'}); AccountService.manager(s, actor, course_id)
            old = s.get(TeacherResource, identifier)
            if old:
                if old.course_id != course_id or old.creator_id != actor.id or old.payload != payload:
                    raise ValueError('上传编号已用于其他资料，请重新选择文件。')
                return self.metadata(old)
            row = TeacherResource(id=identifier, course_id=course_id, creator_id=actor.id, title=title,
                payload=payload, pages=pages, status='ready', external_allowed=external_allowed, revision=1)
            s.add(row); s.flush()
            s.add(AuditLog(actor_id=actor.id, actor_name=actor.display_name, action='upload_teacher_resource',
                resource_type='teacher_resource', resource_id=str(row.id), detail={'course_id':str(course_id), 'page_count':len(pages)}))
            return self.metadata(row)

    def list(self, principal, course_id, keyword, archived, page, size):
        with self.sessions.begin() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'}); AccountService.manager(s, actor, course_id)
            query = select(TeacherResource).where(TeacherResource.course_id == course_id,
                TeacherResource.status == ('archived' if archived else 'ready'))
            if keyword: query = query.where(TeacherResource.title.ilike('%' + keyword + '%'))
            return sql_page(s, query.order_by(TeacherResource.created_at.desc(), TeacherResource.id), page=page, page_size=size, mapper=self.metadata)

    def get(self, principal, course_id, resource_id, first_page=1, last_page=1):
        with self.sessions.begin() as s:
            _, row = self.owned(s, principal, course_id, resource_id)
            return {**self.metadata(row), 'pages': [x for x in row.pages if first_page <= x['page_number'] <= last_page]}

    def edit(self, principal, course_id, resource_id, data):
        with self.sessions.begin() as s:
            actor, row = self.owned(s, principal, course_id, resource_id)
            if row.revision != data.revision: raise ValueError('资料已修改，请重新读取。')
            row.title = re.sub(r'\.pdf$', '', data.title, flags=re.I).strip() or '课程出题资料'
            if data.external_allowed is not None: row.external_allowed=data.external_allowed
            if data.archived is not None: row.status='archived' if data.archived else 'ready'
            row.revision += 1
            AccountService.audit(s, actor, 'edit_teacher_resource', row.id, archived=data.archived, external_allowed=data.external_allowed)
            return self.metadata(row)

    def pdf(self, principal, course_id, resource_id):
        with self.sessions.begin() as s:
            _, row = self.owned(s, principal, course_id, resource_id)
            return row.payload

    def documents(self,principal,course_id,keyword,page,size):
        with self.sessions.begin() as s:
            actor=AccountService.actor(s,principal,{'teacher','admin'});AccountService.manager(s,actor,course_id)
            query=select(Document).join(CourseKnowledgeBase,CourseKnowledgeBase.knowledge_base_id==Document.knowledge_base_id).where(
                CourseKnowledgeBase.course_id==course_id,Document.status=='ready',Document.publication_status=='published')
            if keyword: query=query.where(Document.filename.ilike('%'+keyword+'%'))
            return sql_page(s,query.order_by(Document.filename,Document.id),page=page,page_size=size,
                mapper=lambda x:dict(id=str(x.id),title=x.filename,page_count=x.page_count or 0,external_allowed=x.external_model_allowed))

    def source_pages(self,principal,course_id,data):
        with self.sessions.begin() as s:
            actor=AccountService.actor(s,principal,{'teacher','admin'})
            pages,source=self.source(s,actor,course_id,data)
            return dict(pages=pages,source=source)

    @staticmethod
    def source(s, actor, course_id, data, *, online=False):
        """Read the exact authorized selected pages; never substitute another book."""
        AccountService.manager(s, actor, course_id)
        if data.resource_id:
            row = s.get(TeacherResource, data.resource_id)
            if not row or row.course_id != course_id or row.status != 'ready': raise ValueError('教师资料已归档或不可访问。')
            pages, allowed = row.pages, row.external_allowed
            label = dict(resource_id=str(row.id), document_id=None, title=row.title, revision=row.revision)
        elif data.document_id:
            row = s.get(Document, data.document_id)
            if not row or row.status != 'ready' or row.publication_status != 'published' or not s.scalar(select(CourseKnowledgeBase.course_id).where(
                    CourseKnowledgeBase.course_id == course_id, CourseKnowledgeBase.knowledge_base_id == row.knowledge_base_id)):
                raise ValueError('请选择本课程已发布且完成索引的资料。')
            pages = [dict(page_number=x.page_number, content=x.content) for x in s.scalars(select(DocumentPage).where(
                DocumentPage.document_id == row.id, DocumentPage.page_number.between(data.first_page, data.last_page)).order_by(DocumentPage.page_number))]
            allowed = row.external_model_allowed
            label = dict(resource_id=None, document_id=str(row.id), title=row.filename, revision=row.version_label)
        else: return [], None
        if online and (not allowed or not data.allow_external): raise ValueError('所选资料未允许外发，或本次没有确认使用在线模型。')
        selected = [dict(x) for x in pages if data.first_page <= x['page_number'] <= data.last_page]
        if not selected or not any(x['content'].strip() for x in selected): raise ValueError('所选页码范围没有可读取文字。')
        if sum(len(x['content']) for x in selected) > 100000: raise ValueError('选段文字过多，请缩小页码范围。')
        return selected, {**label, 'first_page':data.first_page, 'last_page':data.last_page}

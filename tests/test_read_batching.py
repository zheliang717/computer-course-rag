from uuid import UUID
from sqlalchemy import event,select
from app.auth import principal_from_user
from app.analytics import AnalyticsService
from app.assessment import AssessmentService
from app.learning import LearningService
from app.models import User,Course,CourseSection,CourseEnrollment,Assignment,AssignmentQuestion,AssignmentSubmission,SubmissionReview,QuestionBankItem


def test_bulk_course_assignment_and_reports_match_reference_with_bounded_queries(postgres_sessions):
    sessions=postgres_sessions
    with sessions.begin() as s:
        teacher=User(username='batch_t',display_name='教师',role='teacher',password_hash='test',active=True)
        student=User(username='batch_s',display_name='学生',role='student',password_hash='test',active=True)
        s.add_all([teacher,student]);s.flush();tid,uid=teacher.id,student.id
        for i in range(6):
            c=Course(code='B'+str(i),title='批量课程'+str(i),owner_id=tid,status='published');s.add(c);s.flush()
            sections=[CourseSection(course_id=c.id,title='章节'+str(j),position=j+1) for j in range(2)]
            s.add_all(sections);s.flush()
            s.add(CourseEnrollment(course_id=c.id,user_id=uid,status='active'))
            for j in range(3):
                q=QuestionBankItem(course_id=c.id,section_id=sections[j%2].id,stem='题目'+str(j),question_type='true_false',options=['正确','错误'],correct_answer='正确')
                a=Assignment(course_id=c.id,creator_id=tid,title='作业'+str(j),status='published')
                s.add_all([q,a]);s.flush()
                s.add(AssignmentQuestion(assignment_id=a.id,question_id=q.id,position=1,points=10))
                if j%2==0:
                    sub=AssignmentSubmission(assignment_id=a.id,student_id=uid,answers={str(q.id):'正确'},score=10,max_score=10,status='graded')
                    s.add(sub);s.flush()
                    s.add(SubmissionReview(submission_id=sub.id,teacher_id=tid,score=8,feedback='已核对'))
    analytics=AnalyticsService(sessions);learning=LearningService(sessions);assessment=AssessmentService(sessions)
    engine=sessions.kw['bind']
    def counted(fn,limit):
        queries=[]
        def before(conn,cursor,statement,parameters,context,executemany):
            if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
        event.listen(engine,'before_cursor_execute',before)
        try:result=fn()
        finally:event.remove(engine,'before_cursor_execute',before)
        assert len(queries)<=limit
        return result
    reports=counted(lambda:analytics.student_reports(uid),9)
    with sessions() as s:
        expected=[analytics._student_course_report(s,c,uid) for c in s.scalars(select(Course))]
    assert sorted(reports,key=lambda x:x['course_id'])==sorted(expected,key=lambda x:x['course_id'])
    for role,identifier in [('student',uid),('teacher',tid)]:
        courses=counted(lambda:learning.list_courses(user_id=identifier,role=role),7)
        with sessions() as s:
            for overview in courses:
                old=learning._overview(s,s.get(Course,overview.course.id))
                assert (overview.section_count,overview.class_count,overview.student_count,overview.teacher_name)==(old.section_count,old.class_count,old.student_count,old.teacher_name)
        assignments=counted(lambda:assessment.list_assignments(user_id=identifier,role=role),9)
        with sessions() as s:
            for item in assignments:assert item==assessment._single_assignment_dict(s,s.get(Assignment,UUID(item['id'])),user_id=identifier)

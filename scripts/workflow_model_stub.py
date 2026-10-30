"""Loopback-only model fixture. Refuses to run outside the disposable test DB."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os

assert os.environ.get('DATABASE_URL','').endswith('/rag_today_dev_20261028'), 'Only the named isolated API may run this fixture'


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        try:
            assert self.path=='/v1/chat/completions'
            assert self.headers.get('Authorization')=='Bearer isolated-workflow-test'
            length=int(self.headers.get('Content-Length','0'));assert 0<length<400000
            value=json.loads(self.rfile.read(length));assert value['model']=='workflow-test-only'
            prompt='\n'.join(x['content'] for x in value['messages'])
            if '\n事实：' in prompt:
                facts=json.loads(prompt.split('\n事实：',1)[1].split('\n需求',1)[0])
                rooms=facts['rooms']; preferred=[r['code'] for r in rooms if r.get('kind') in {'computer_lab','specialized_lab'}] or [r['code'] for r in rooms]
                bounds=facts['hard_window']
                content=dict(day_start=bounds['day_start'][:5],day_end=bounds['day_end'][:5],weekdays=bounds['weekdays'],rooms=preferred,
                    explanation='优先选择已登记机房，时间与师生冲突交由排课程序检查。此段仅为隔离测试模型输出。')
            elif 'learning_objectives、assessment、sections' in prompt:
                content=dict(description='课程内容建议：结合基础概念与实践应用。',learning_objectives='- 理解检索与证据\n- 能够分析算法边界',assessment='平时练习与实践考核的建议，等待教师核对。',
                    sections=[dict(title='检索与证据基础',description='理解索引、检索与引用。',knowledge_points=['证据定位','检索流程'])])
            else: raise ValueError('Unknown fixture request')
            raw=json.dumps(dict(id='isolated-workflow',choices=[dict(message=dict(role='assistant',content=json.dumps(content,ensure_ascii=False)),finish_reason='stop')],usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200)),ensure_ascii=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        except Exception:
            self.send_response(400);self.end_headers()


if __name__=='__main__': ThreadingHTTPServer(('127.0.0.1',18091),Handler).serve_forever()

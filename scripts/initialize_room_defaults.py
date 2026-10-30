"""Add editable advisory catalogs only where no admin configuration exists."""
import argparse
import json
from pathlib import Path
import httpx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',choices=['local','preview'],required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    password='admin123'
    if args.target=='preview':
        password=next(r['password'] for r in json.loads((root/'.private/funnel/accounts.json').read_text(encoding='utf-8')) if r['username']=='admin')
    with httpx.Client(base_url='http://127.0.0.1:'+('5173' if args.target=='local' else '18080')+'/api/v1',timeout=30,trust_env=False) as client:
        response=client.post('/auth/login',json={'username':'admin','password':password});response.raise_for_status()
        client.headers['Authorization']='Bearer '+response.json()['access_token']
        version=client.get('/system');version.raise_for_status()
        # This read-only capability check fails on an older API before any PUT.
        capability=client.get('/timetable/resource-suggestions',params={'semester':'__capability_check__'})
        assert capability.status_code in (200,400,404), 'Resource API unavailable; deploy the verified implementation first.'
        assert 'Not Found' not in capability.text, 'Resource API route is not installed.'
        response=client.get('/courses');response.raise_for_status()
        semesters=sorted({r['semester'] for r in response.json() if r.get('semester')})
        rows=[]
        for semester in semesters:
            current=client.get('/timetable/resources',params={'semester':semester});current.raise_for_status()
            state=current.json()
            if state['resources'] is not None:
                rows.append({'semester':semester,'status':'preserved_existing','revision':state['revision']});continue
            response=client.get('/timetable/resource-suggestions',params={'semester':semester});response.raise_for_status()
            payload=response.json();payload.pop('notice',None)
            assert payload['resource_mode']=='advisory' and not payload['availability']
            response=client.put('/timetable/resources',json={**payload,'expected_revision':state['revision']});response.raise_for_status()
            rows.append({'semester':semester,'status':'initialized_editable_default','rooms':len(response.json()['resources']['rooms'])})
    output=root/'reports/today-goals-20261028'/('room-defaults-'+args.target+'.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'target':args.target,'lessons_moved':0,'resource_mode':'advisory','catalogs':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(args.target+': room defaults initialized or existing admin catalogs preserved; no lessons moved.')


if __name__=='__main__':main()

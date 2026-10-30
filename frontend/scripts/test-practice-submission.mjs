import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'
const source=await readFile(new URL('../src/practiceSubmission.ts',import.meta.url),'utf8')
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const {createPracticeSubmissionTracker}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)
const values=new Map()
const storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)}
const tracker=createPracticeSubmissionTracker(()=>storage)
const first=await tracker.prepare('student1','q1','A')
assert.deepEqual(await tracker.prepare('student1','q1','A'),first)
const reload=createPracticeSubmissionTracker(()=>storage)
assert.deepEqual(await reload.prepare('student1','q1','A'),first)
assert.notEqual((await tracker.prepare('student2','q1','A')).requestId,first.requestId)
assert.notEqual((await tracker.prepare('student1','q1','B')).requestId,first.requestId)
tracker.complete(first)
assert.notEqual((await reload.prepare('student1','q1','A')).requestId,first.requestId)
const blocked=createPracticeSubmissionTracker(()=>{throw new Error('blocked')})
const inPage=await blocked.prepare('student1','q1','A')
assert.deepEqual(await blocked.prepare('student1','q1','A'),inPage)
console.log('Practice retry tracker: same submission/reload/owner isolation/new attempt/blocked storage passed.')

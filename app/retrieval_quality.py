"""Versioned retrieval gates. Passing is not semantic teaching approval."""
POLICY='evidence-v2-20261029'
LIMITS={'recall_at_5':.75,'mrr':.60,'refusal_accuracy':.80,'citation_accuracy':.85,'page_recall_at_5':.80,'page_citation_accuracy':.80}
def gate_details(metrics,coverage=None):
    checks={key:isinstance(metrics.get(key),(int,float)) and metrics[key]>=value for key,value in LIMITS.items() if not key.startswith('page_') or metrics.get('page_scoped_cases',0)>0}
    checks['latency_p95_ms']=isinstance(metrics.get('latency_p95_ms'),(int,float)) and 0<=metrics['latency_p95_ms']<=1000
    checks['source_coverage']=coverage is None or coverage.get('missing_cases')==0
    return dict(policy=POLICY,passed=all(checks.values()),checks=checks,limits={**LIMITS,'latency_p95_ms':1000})
def quality_gate(metrics,coverage=None):return gate_details(metrics,coverage)['passed']

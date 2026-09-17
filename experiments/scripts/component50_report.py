"""Audit retained component-study evidence and export complete paired results."""
import csv
import json
from pathlib import Path
import random
import statistics
import sys
from collections import Counter, defaultdict
from component50 import covered

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'experiment_results/component_studies/component_planning_50'
MODELS = ['v4','v32','qwen36','gpt4o']
ARMS = ['full','no_elaboration','no_rank','no_exact_match']

def write_csv(path, rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def interval(groups):
    rng=random.Random(20260911)
    samples=[]
    size=sum(len(g) for g in groups)
    for _ in range(10000):
        samples.append(sum(sum(rng.choices(g,k=len(g))) for g in groups)/size)
    samples.sort()
    return samples[249],samples[9749]

def main():
    output=PACKAGE/'statistics';output.mkdir(exist_ok=True)
    rows=[];tasks=[];calls=[];reuse_verified=0;seen_slots=set();seen_responses=set()
    for batch in sorted((PACKAGE/'raw_batches').iterdir()):
        state=json.loads((batch/'batch.json').read_text())
        assert state['status']=='completed' and all(w['returncode']==0 for w in state['workers'])
        batch_tasks=json.loads((batch/'tasks.json').read_text());tasks+=batch_tasks
        index={t['id']:t for t in batch_tasks}
        for path in sorted((batch/'results').glob('*/*/*/record.json')):
            r=json.loads(path.read_text());task=index[r['task']]
            slot=(r['model'],r['task'],r['arm']);assert slot not in seen_slots;seen_slots.add(slot)
            assert r['golden_components']==task['golden_components']
            arm=r['arm'];unit=path.parent.parent
            candidates_path=unit/('no_elaboration' if arm=='no_elaboration' else 'full')/'candidates.json'
            candidates=json.loads(candidates_path.read_text())['candidates'];assert len(candidates)==3
            valid=[c for c in candidates if c['data']]
            selected=candidates[0] if arm=='no_rank' else max(valid,key=lambda c:c['score']) if valid else None
            assert r['selected_index']==(selected['index'] if selected else None)
            assert r['format_parse']==bool(selected and selected['data'])
            retrieved=json.loads((path.parent/'retrieved.json').read_text())
            bindings=[x['result']['data'] for x in retrieved if x['result']['status']=='success']
            matched=[g for g in task['golden_components'] if covered(g,bindings)]
            assert r['matched']==matched and abs(r['component_recall']-len(matched)/len(task['golden_components']))<1e-12
            assert abs(r['retrieval_hit_rate']-(len(bindings)/len(retrieved) if retrieved else 0))<1e-12
            assert r['planned_components']==len(retrieved) and r['retrieved_components']==len(bindings)
            if selected and selected['data']:
                assert [c['search_query'] for c in selected['data']['components']]==[x['query'] for x in retrieved]
            rows.append({**{k:r[k] for k in ('model','task','arm','format_parse','selected_index','component_recall','retrieval_hit_rate','planned_components','retrieved_components')},
                         'stratum':'electrical20' if task['stratum']=='electrical20' else 'board30',
                         'matched_count':len(matched),'gold_count':len(task['golden_components']),
                         'record':str(path.relative_to(PACKAGE))})
        for request in sorted((batch/'results').glob('*/*/*/calls/call_*/request.json')):
            response=request.with_name('response.json');assert response.exists(),str(request)
            req=json.loads(request.read_text());rsp=json.loads(response.read_text())
            relative=request.relative_to(batch/'results');model,task,arm=relative.parts[:3]
            reused=(request.parents[2]/'reused_provider.json').exists()
            if reused:
                source=ROOT/'experiment_results/final/records/units'/model/task/'1/planning_calls'/request.parent.name
                assert json.loads((source/'request.json').read_text())==req
                assert json.loads((source/'response.json').read_text())==rsp
                reuse_verified+=1
            rid=rsp.get('id');duplicate=bool(rid and rid in seen_responses)
            if rid:seen_responses.add(rid)
            calls.append({'model':model,'task':task,'arm':arm,'call':request.parent.name,
                          'reused':reused,'requested_model':req['model'],'returned_model':rsp['model'],
                          'response_id':rid,'duplicate_response_id':duplicate,
                          'tokens':(rsp.get('usage') or {}).get('total_tokens'),
                          'request':str(request.relative_to(PACKAGE))})
    ids={t['id'] for t in tasks}
    assert len(tasks)==len(ids)==50
    assert len({' '.join(t['user_requirement'].lower().split()) for t in tasks})==50
    assert seen_slots=={(m,t,a) for m in MODELS for t in ids for a in ARMS} and len(rows)==800
    assert len(calls)==1400 and reuse_verified==320
    (output/'tasks.json').write_text(json.dumps(tasks,ensure_ascii=False,indent=2)+'\n')
    write_csv(output/'trials.csv',rows);write_csv(output/'calls.csv',calls)
    summary=[];paired=[];pair_rows=[]
    for model in MODELS:
        full={r['task']:r for r in rows if r['model']==model and r['arm']=='full'}
        for arm in ARMS:
            for stratum in ('all50','board30','electrical20'):
                rs=[r for r in rows if r['model']==model and r['arm']==arm and (stratum=='all50' or r['stratum']==stratum)]
                summary.append({'model':model,'arm':arm,'stratum':stratum,'tasks':len(rs),
                    **{k:statistics.mean(float(r[k]) for r in rs) for k in ('component_recall','retrieval_hit_rate','format_parse')}})
                if arm=='full':continue
                groups=defaultdict(list)
                for r in rs:groups[r['stratum']].append(full[r['task']]['component_recall']-r['component_recall'])
                differences=[d for g in groups.values() for d in g]
                low,high=interval(list(groups.values()))
                paired.append({'model':model,'control':arm,'stratum':stratum,'tasks':len(rs),
                  'full_minus_control_recall':statistics.mean(differences),'ci_low':low,'ci_high':high,
                  'positive_tasks':sum(d>1e-12 for d in differences),'negative_tasks':sum(d< -1e-12 for d in differences),
                  'ties':sum(abs(d)<=1e-12 for d in differences)})
                if stratum=='all50':
                    for r in rs:pair_rows.append({'model':model,'control':arm,'task':r['task'],'stratum':r['stratum'],
                        'full_recall':full[r['task']]['component_recall'],'control_recall':r['component_recall'],
                        'difference':full[r['task']]['component_recall']-r['component_recall']})
    write_csv(output/'summary.csv',summary);write_csv(output/'paired_summary.csv',paired);write_csv(output/'paired_tasks.csv',pair_rows)
    resources=[]
    for model in MODELS:
        for kind in (True,False):
            cs=[c for c in calls if c['model']==model and c['reused']==kind]
            resources.append({'model':model,'reused':kind,'responses':len(cs),
               'known_tokens':sum(c['tokens'] for c in cs if c['tokens'] is not None),
               'unknown_usage':sum(c['tokens'] is None for c in cs),
               'returned_models':dict(Counter(c['returned_model'] for c in cs))})
    (output/'resources.json').write_text(json.dumps(resources,indent=2)+'\n')
    audit={'component_records':800,'unique_tasks':50,'settings':16,'planning_candidate_bundles':400,
           'returned_response_files':1400,'verified_reused_responses':reuse_verified,'new_response_files':1080,
           'duplicate_response_ids':sum(c['duplicate_response_id'] for c in calls),
           'record_selection_and_retrieval_recomputed':True,
           'category_pool_ablation':'not implemented; no independent module in this snapshot',
           'interval':'paired task bootstrap, 10000 resamples, seed 20260911; all50 resamples within strata, unadjusted exploratory intervals',
           'interpretation':'board30 exact library labels; electrical20 coarse role coverage. Pooled recall is a mixed-granularity coverage index, not a homogeneous exact-match metric.'}
    (output/'verification.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit))
    for r in summary:
        if r['stratum']=='all50':print(r)
    for r in paired:
        if r['stratum']=='all50':print(r)

if __name__=='__main__':main()

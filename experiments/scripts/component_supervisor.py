"""Two background workers; one compact status file, no agent polling loop."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def save(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--env',required=True);a=ap.parse_args()
    root=a.root.resolve();state=root/'batch.json'
    if state.exists():raise RuntimeError('batch already submitted; inspect recorded processes before resuming')
    expected=len(json.loads((root/'tasks.json').read_text()))*16
    batch={'status':'running','pid':os.getpid(),'started':time.time(),'models':['v4','v32','qwen36','gpt4o'],'expected_records':expected}
    save(state,batch)
    def run(model):
        with (root/(model+'.log')).open('w') as log:
            proc=subprocess.Popen([sys.executable,str(root/'component50.py'),'--root',str(root),'--env',a.env,'--model',model],stdout=log,stderr=subprocess.STDOUT)
            save(root/(model+'.worker.json'),{'pid':proc.pid,'status':'running'})
            code=proc.wait()
            row={'model':model,'pid':proc.pid,'returncode':code,'status':'completed' if code==0 else 'needs_attention'}
            save(root/(model+'.worker.json'),row)
            return row
    with ThreadPoolExecutor(max_workers=2) as pool:workers=list(pool.map(run,batch['models']))
    rows=[json.loads(p.read_text()) for p in (root/'results').glob('*/*/*/record.json')]
    summary=[]
    for model in batch['models']:
        for arm in ('full','no_elaboration','no_rank','no_exact_match'):
            for stratum in ('all','board29','electrical20'):
                subset=[r for r in rows if r['model']==model and r['arm']==arm and (stratum=='all' or r['stratum']==stratum)]
                if subset:summary.append({'model':model,'arm':arm,'stratum':stratum,'n':len(subset),**{k:sum(r[k] for r in subset)/len(subset) for k in ('component_recall','retrieval_hit_rate','format_parse')}})
    save(root/'summary.json',summary)
    batch.update(status='completed' if len(rows)==expected and all(w['returncode']==0 for w in workers) else 'needs_attention',records=len(rows),finished=time.time(),workers=workers)
    save(state,batch)

if __name__=='__main__':main()

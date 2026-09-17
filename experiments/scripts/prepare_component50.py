"""Freeze requirement-derived labels and reuse returned planning calls only."""
import argparse
import json
from pathlib import Path
import shutil

ROLES = {
 'eda_005':['opamp','resistor','ground','power','connector'],
 'eda_006':['opamp','resistor','capacitor','connector','power'],
 'eda_007':['npn','resistor','capacitor'],
 'eda_008':['microphone','resistor','capacitor','opamp','connector'],
 'eda_009':['connector','resistor','capacitor','ground'],
 'eda_010':['opamp','resistor','capacitor','power','connector'],
 'eda_016':['resistor','zener','ground','capacitor','connector'],
 'eda_024':['opamp','capacitor','resistor','connector'],
 'eda_027':['opamp','resistor','capacitor','connector','ground'],
 'eda_037':['opamp','nmos','resistor','connector','capacitor'],
 'eda_201':['opamp','resistor','power'],
 'eda_202':['opamp','resistor','power'],
 'eda_203':['npn','resistor','capacitor','power'],
 'eda_204':['npn','resistor','capacitor','power'],
 'eda_205':['resistor','capacitor','opamp','power'],
 'eda_206':['resistor','capacitor','opamp','power'],
 'eda_207':['zener','resistor','power'],
 'eda_208':['zener','npn','resistor','power'],
 'eda_209':['opamp','nmos','resistor','capacitor','power','led'],
 'eda_210':['npn','resistor','led','power'],
}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 repo=args.repo.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 board=json.loads((repo/'experiments/datasets/test_cases_extended.json').read_text())
 electric=json.loads((repo/'revision/benchmark/synthesis_20.json').read_text())['cases']
 tasks=[{**x,'id':'board_'+x['id'],'stratum':'board29','seed':261100000+i} for i,x in enumerate(board) if x['id']!='test_5']
 tasks += [{'id':c['id'],'user_requirement':c['user_requirement'],'stratum':'electrical20',
            'golden_components':['@'+r for r in ROLES[c['id']]],
            'seed':260910001+int(c['id'].split('_')[1])*10} for c in electric]
 assert len(tasks)==49 and len({x['id'] for x in tasks})==49
 assert len({' '.join(x['user_requirement'].lower().split()) for x in tasks})==49
 (out/'tasks.json').write_text(json.dumps(tasks,ensure_ascii=False,indent=2)+'\n')
 (out/'framework').mkdir();(out/'support').mkdir()
 for name in ('circuit_planner_v.py','retriever_final_merged.py'):
  shutil.copy2(repo/'framework'/name,out/'framework'/name)
 for name in ('alignment_runner.py','alignment_config.py'):
  shutil.copy2(repo/'revision/development'/name,out/'support'/name)
 shutil.copy2(repo/'experiments/scripts/component50.py',out/'component50.py')
 source=repo/'experiment_results/final/records/units'
 req=json.loads((source/'v4/eda_005/1/planning_calls/call_02/request.json').read_text())
 system=req['messages'][0]['content'];(out/'planning_system.txt').write_text(system)
 reuse=[]
 for model in ('v4','v32','qwen36','gpt4o'):
  for task in tasks:
   if task['stratum']!='electrical20':continue
   calls=source/model/task['id']/'1/planning_calls'
   files=sorted(calls.glob('call_*/request.json'))
   if len(files)!=4 or not all(p.with_name('response.json').exists() for p in files):continue
   requests=[json.loads(p.read_text()) for p in files]
   if requests[0].get('seed')!=task['seed'] or any(q['messages'][0]['content']!=system for q in requests[1:]):continue
   dest=out/'results'/model/task['id']/'full/calls'
   for p in files:
    d=dest/p.parent.name;d.mkdir(parents=True,exist_ok=True)
    for name in ('request.json','response.json'):shutil.copy2(p.parent/name,d/name)
   shutil.copy2(calls.parent/'provider.json',dest.parent/'reused_provider.json')
   reuse.append({'model':model,'task':task['id'],'source':str(calls),'calls':4})
 (out/'reuse.json').write_text(json.dumps(reuse,indent=2)+'\n')
 (out/'protocol.json').write_text(json.dumps({'tasks':49,'models':4,'arms':['full','no_elaboration','no_rank','no_exact_match'],
  'exclusion':'test_5 duplicates test_3 requirement but has unrelated golden_components; original dataset preserved',
  'repeat':1,'evaluations':784,'candidates':3,'temperatures':[.1,.2,.30000000000000004],
  'labels':'board29 retains exact library labels; electrical20 uses frozen requirement-derived role sets; report strata separately',
  'quantity':'unique component types/roles, not instance counts or electrical correctness',
  'ranking':'Full selects highest original semantic+lexical score; no_rank uses first candidate, including parse failure',
  'no_exact_match':'disable registry and lib_id lookup; retain query optimization and virtual-device behavior',
  'pool':'not scheduled: no independent category-pool implementation in current planner',
  'reuse':'first repeat only, all returned candidates preserved; existing ResponseLedger enforces exact request replay',
  'authorization':'user approved these task/planning payloads to api.deepseek.com, api.siliconflow.cn, api2.aigcbest.top',
  'endpoint_check':'verify saved provider endpoint_sha256 against current configuration before generation'},indent=2)+'\n')
 print(json.dumps({'tasks':49,'reuse_units':len(reuse),'reuse_calls':4*len(reuse)}))

if __name__=='__main__':main()

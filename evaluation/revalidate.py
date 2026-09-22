"""Recheck saved native evidence, including every agent-requested experiment.

No model, SSH, Docker or candidate code is executed. Works with local execution
folders or the portable bundle's extracted results/ directory.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from backtest_repair.acceptance import validate_submission
from backtest_repair.contracts import load_json,read_bars,digest
from backtest_repair.identity import checker_identity
from backtest_repair.preservation import check_preservation
from backtest_repair.probes import future_perturbation
from backtest_repair.rules import check_contract
from backtest_repair.store import atomic_json
from backtest_repair.validation import financial_check,prefix_check,indicator_preservation,conformance_check


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,default=ROOT/'results/twenty')
    parser.add_argument('--output',type=Path,default=ROOT/'evaluation/revalidation.json')
    args=parser.parse_args();rows=[]
    for source in load_json(ROOT/'sources.json'):
        ident=source['id'];paths=list(args.runs.glob(ident+'/*/episode.json'))
        if len(paths)!=1:raise ValueError('Expected one frozen episode for '+ident)
        folder=paths[0].parent;episode=load_json(paths[0]);baseline=load_json(folder/'baseline.json')
        project=ROOT/'cases'/ident;candidate=folder/'candidate'
        sha=digest(candidate/'strategy.py')
        assert sha==episode['submitted_sha256']
        spec=load_json(project/'task.json');bars=read_bars(project/'fixtures/bars.csv')
        native={}
        for path in (folder/'executions').glob('*/result.json'):
            result=load_json(path)
            native[result['run_id']]=(result,path.parent)
        def run(ident):return native[ident][0]
        full=run(episode['visible_evidence']['baseline']['run_id'])
        full_folder=native[full['run_id']][1]
        assert digest(full_folder/'candidate/strategy.py')==sha
        original=run(baseline['report']['baseline']['run_id'])
        canonical=episode['visible_evidence']['causality']
        causal=prefix_check(full,run(canonical['prefix_run_id']),bars,canonical['cutoff_index']+1)
        required=[]
        # Reconstruct the actual requested experiments from durable action receipts.
        for response_path in sorted((folder/'model_calls').glob('*/response.json')):
            response=load_json(response_path)['response'];text=response['text'].strip()
            if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
            try:actions=json.loads(text)['actions']
            except (ValueError,KeyError):continue
            for index,action in enumerate(actions):
                receipt=folder/'actions'/f'{response_path.parent.name}-{index+1}.json'
                if not receipt.exists():continue
                if action['tool']=='probe':probes=[{'kind':action.get('kind','future'),'fraction':float(action.get('fraction',0.5))}]
                elif action['tool']=='localize':probes=[{'kind':'future','fraction':f} for f in (0.25,0.375)]
                else:continue
                for probe in probes:
                    if probe not in required:required.append(probe)
        additional=[]
        for probe in required:
            count=max(2,min(len(bars)-1,int(len(bars)*probe['fraction'])))
            expected=bars[:count] if probe['kind']=='prefix' else future_perturbation(bars,count-1,seed=0)
            matches=[]
            for result,native_folder in native.values():
                request=load_json(native_folder/'request.json')
                if not request.get('instrument',True) or digest(native_folder/'candidate/strategy.py')!=sha:continue
                if read_bars(native_folder/'candidate/fixtures/bars.csv')==expected:matches.append(result)
            if not matches:raise ValueError('No final-candidate evidence for requested experiment: '+ident+' '+str(probe))
            measured=prefix_check(full,matches[0],bars,count)
            measured['source_sha256']=sha
            additional.append({**probe,'result':measured})
        causal['additional_probes']=additional
        statuses=[causal['status'],*[a['result']['status'] for a in additional]]
        causal['status']='fail' if 'fail' in statuses else 'pass' if all(s=='pass' for s in statuses) else 'inconclusive'
        preservation=check_preservation(project/'strategy.py',candidate/'strategy.py',spec.get('repair_policy'))
        preservation['indicators']=indicator_preservation(spec,original,full)
        if preservation['indicators']['status']!='pass':preservation['status']='fail'
        report={'source_sha256':sha,'baseline':episode['visible_evidence']['baseline'],'financial':financial_check(spec,bars,full),'invariants':check_contract(spec,bars,full),'causality':causal,'preservation':preservation}
        if episode['visible_evidence'].get('conformance'):
            plain=run(episode['visible_evidence']['conformance']['plain_run_id'])
            report['conformance']=conformance_check(full,plain)
            if report['conformance']['status']!='pass':report['invariants']['status']='inconclusive'
        if episode['submission']:
            verdict=validate_submission(episode['submission']['diagnosis'],episode['original_sha256'],sha,sha,report,required)
            assert verdict['accepted']==episode['accepted']
        else:verdict={'accepted':False,'status':episode['status']}
        rows.append({'case':ident,'accepted':verdict['accepted'],'original_episode_status':episode['status'],'additional_experiments':len(additional),'report':report,'acceptance_consistent':True})
    result={'mode':'offline recheck of saved native results and exact experiment fixtures','model_calls':0,'native_calls':0,'checker':checker_identity(),'cases':len(rows),'accepted':sum(r['accepted'] for r in rows),'all_acceptance_consistent':all(r['acceptance_consistent'] for r in rows),'additional_experiments':sum(r['additional_experiments'] for r in rows),'results':rows}
    atomic_json(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k!='results'}))


if __name__=='__main__':main()

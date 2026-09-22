"""Small external-code validation suite. No invented target trades or return oracle."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import math
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from backtest_repair.contracts import load_json, dump_json, read_bars, digest
from backtest_repair.runner import Runner, Budget
from backtest_repair.semantics import ledger, fee
from defect_checks import check_contract
from backtest_repair.identity import execution_identity, reuse_completed
from backtest_repair.preservation import check_preservation

def near(a,b):
    if a is None or b is None: return a is b
    return math.isclose(float(a),float(b),abs_tol=1e-6,rel_tol=1e-8)

def financial_check(spec,bars,result):
    if result['status']!='ok': return {'status':'inconclusive','reason':result.get('error')}
    native=result['native']; fills=native.get('fills',[])
    expected=ledger(spec,bars,fills)
    observed_fills=[e for e in result['events'] if e['kind']=='fill']
    errors=[]
    if spec.get('native_exit_rules'):
        configs=[e.get('exit_rules') for e in result['events'] if e['kind']=='execution_config']
        if len(configs)!=1 or configs[0]!=spec['native_exit_rules']:
            errors.append({'field':'execution_config','expected':spec['native_exit_rules'],'actual':configs})
    for field in ['equity','position']+(['cash'] if spec['accounting_profile']=='cash_equity' else []):
        if native.get(field) is None or not math.isfinite(float(native[field])):
            errors.append({'field':field,'reason':'Required native account observation missing or nonfinite'})
    for i,f in enumerate(fills):
        if not near(f['fee'],fee(spec,f['qty'],f['price'])):
            errors.append({'fill':i,'field':'fee','expected':fee(spec,f['qty'],f['price']),'actual':f['fee']})
    for field in ['cash','equity','position']:
        a,b=expected[-1].get(field),native.get(field)
        if a is not None and b is not None and not near(a,b): errors.append({'field':field,'expected':a,'actual':b})
    if len(observed_fills)!=len(fills): errors.append({'field':'fill_trace_count','native':len(fills),'trace':len(observed_fills)})
    for i,(a,b) in enumerate(zip(observed_fills,fills)):
        if a['session']!=b['session'] or any(not near(a[k],b[k]) for k in ['qty','price','fee']):
            errors.append({'field':'fill_trace_reconciliation','fill':i})
    # Account at every observed bar, including the native daily result for minute CTA data.
    by_session={r['session']:r for r in expected}
    accounts={e['session']:e for e in result['events'] if e['kind']=='account'}
    for e in accounts.values():
        for field in ['cash','equity','position']:
            a,b=by_session[e['session']].get(field),e.get(field)
            if a is not None and b is not None and not near(a,b):
                errors.append({'field':field,'session':e['session'],'expected':a,'actual':b})
    return {'status':'fail' if errors else 'pass' if fills else 'inconclusive','fills':len(fills),'errors':errors[:8],'error_count':len(errors),'meaning':'Reconciles native fills, declared fees and cash/PnL ledger; does not prove strategy intent or market realism.'}

def observations(result,last_session):
    values={}; fills=[]; orders=[]
    terminal_ids={e['order_id'] for e in result.get('events',[]) if e['kind']=='fill' and e.get('order_id') is not None and (e.get('exit_reason')=='force_exit' or e.get('phase')=='finalize')}
    for e in result.get('events',[]):
        if e['session']>last_session: continue
        if e['kind']=='indicator': values[e['session']+'|indicator|'+e['name']]=e['value']
        elif e['kind']=='signal':
            values[e['session']+'|entry']=e.get('signal')
            if 'exit_signal' in e: values[e['session']+'|exit']=e['exit_signal']
        elif e['kind']=='order' and e.get('order_id') not in terminal_ids and e.get('phase')!='finalize':
            orders.append((e['session'],e.get('qty'),e.get('order_type'),e.get('price')))
    for row in result.get('native',{}).get('indicators',[]):
        if row['session']<=last_session:
            for name,value in row['values'].items(): values[row['session']+'|indicator|'+name]=value
    for f in result.get('native',{}).get('fills',[]):
        if f['session']<=last_session and f.get('exit_reason')!='force_exit' and not f.get('terminal',False): fills.append({k:f[k] for k in ['session','qty','price','fee']})
    return values,fills,orders

def prefix_check(full,prefix,bars,count):
    if full['status']!='ok' or prefix['status']!='ok':
        return {'status':'inconclusive','reason':prefix.get('error') or full.get('error'),'full_status':full['status'],'prefix_status':prefix['status']}
    # Compare indicators/signals through the decision boundary. Only explicitly
    # identified forced terminal fills/orders are excluded by observations().
    last=bars[count-1]['date']
    a,af,ao=observations(full,last); b,bf,bo=observations(prefix,last)
    if not any(v is not None for v in a.values()) and not af and not ao:
        return {'status':'inconclusive','reason':'No meaningful indicator, signal, order or fill observations through the cutoff','difference_count':0}
    differences=[]
    for key in sorted(a.keys()|b.keys()):
        if key not in a or key not in b or not near(a.get(key),b.get(key)):
            differences.append({'observation':key,'full':a.get(key),'prefix':b.get(key)})
    if af!=bf: differences.append({'observation':'native_fill_sequence','full_count':len(af),'prefix_count':len(bf),'full_first':af[:3],'prefix_first':bf[:3]})
    if ao!=bo: differences.append({'observation':'order_sequence','full_count':len(ao),'prefix_count':len(bo)})
    return {'status':'fail' if differences else 'pass','compared_through':last,'prefix_bars':count,'observable_values':len(a),'fill_count':len(af),'order_count':len(ao),'difference_count':len(differences),'examples':differences[:5],'full_run_id':full['run_id'],'prefix_run_id':prefix['run_id'],'scope':'Selected indicators, entry/exit signals and native order/fill prefixes; hidden internal state is not fully observed.'}

def conformance_check(full,plain):
    if full['status']!='ok' or plain['status']!='ok': return {'status':'inconclusive','reason':plain.get('error') or full.get('error')}
    a,b=full['native'],plain['native']
    ok=all(near(a.get(k),b.get(k)) for k in ['cash','equity','position']) and a.get('fills')==b.get('fills')
    return {'status':'pass' if ok else 'fail','plain_run_id':plain['run_id'],'meaning':'Observation toggle preserves native final account and every native fill.'}

def short(result):
    native=result.get('native',{})
    return {'status':result['status'],'error':result.get('error'),'run_id':result['run_id'],'runtime_image':result.get('runtime_image'),'equity':native.get('equity'),'position':native.get('position'),'fills':len(native.get('fills',[])),'trades':native.get('trade_count',native.get('closed_trade_count')),'elapsed_seconds':result.get('elapsed_seconds')}

def baseline(ident,runtime,tag='baseline'):
    case=ROOT/'cases'/ident
    output=ROOT/'results'/tag/ident
    identity=execution_identity(case,runtime,load_json(ROOT/'protocol.json'),[ROOT/'external_eval.py',ROOT/'defect_checks.py'])
    cached=reuse_completed(output/'summary.json',identity)
    if cached is not None:
        print(json.dumps({'case':ident,'skipped':'already recorded'}),flush=True)
        return cached
    spec=load_json(case/'task.json'); bars=read_bars(case/'fixtures/bars.csv')
    runner=Runner(runtime,output/'native_runs',Budget(max_runs=3,max_seconds=600),mode='ssh_docker')
    full=runner.run(case)
    dump_json(output/'full.json',full)
    result={'case':ident,'execution_identity':identity,'source_sha256':digest(case/'strategy.py'),'baseline':short(full),'financial':financial_check(spec,bars,full),'invariants':check_contract(spec,bars,full),'preservation':check_preservation(case/'strategy.py',case/'strategy.py',spec.get('repair_policy'))}
    if full['status']=='ok':
        count=int(len(bars)*load_json(ROOT/'protocol.json')['visible_prefix_fractions'][0])
        prefix=runner.run(case,bars=bars[:count])
        dump_json(output/'prefix.json',prefix)
        result['causality']=prefix_check(full,prefix,bars,count)
        if ident=='adx_missing_exit':
            plain=runner.run(case,instrument=False)
            result['observation_conformance']=conformance_check(full,plain)
    dump_json(output/'summary.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

def main(action,runtime,selected=None):
    choices=[r['id'] for r in load_json(ROOT/'sources.json')]
    selected=selected or choices
    if not set(selected)<=set(choices): raise ValueError('Unknown case')
    if action.startswith('baseline'):
        with ThreadPoolExecutor(max_workers=3) as pool:
            result=list(pool.map(lambda ident:baseline(ident,runtime,action),selected))
        dump_json(ROOT/'results'/action/'summary.json',result)
    elif action=='agents':
        from external_agent import episode
        with ThreadPoolExecutor(max_workers=3) as pool:
            result=list(pool.map(lambda ident:episode(ident,runtime),selected))
        dump_json(ROOT/'results/agents/summary.json',result)
    elif action=='holdout':
        from external_agent import holdout
        with ThreadPoolExecutor(max_workers=3) as pool:
            result=list(pool.map(lambda ident:holdout(ident,runtime),selected))
        dump_json(ROOT/'results/holdout/summary.json',result)
    else: raise ValueError(action)

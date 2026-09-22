import copy
from pathlib import Path
import shutil

import pytest

from backtest_repair.acceptance import REQUIRED_CHECKS, validate_submission
from backtest_repair.contracts import capabilities, dump_json, load_json
from backtest_repair.identity import execution_identity, reuse_completed
from backtest_repair.preservation import check_preservation
from backtest_repair.trace import Recorder
from backtest_repair import fixture_api
from external_eval import financial_check, prefix_check

ROOT=Path(__file__).resolve().parents[1]


def evidence():
    return {'baseline':{'status':'ok'},**{name:{'status':'pass'} for name in REQUIRED_CHECKS}}


def test_unchanged_failed_code_cannot_claim_repair():
    report=evidence();report['invariants']['status']='fail'
    with pytest.raises(ValueError,match='actual source change'):
        validate_submission('repaired','old','old','old',report)


@pytest.mark.parametrize('check',REQUIRED_CHECKS)
@pytest.mark.parametrize('diagnosis',['repaired','observed_no_violation'])
def test_every_success_diagnosis_requires_every_check(check,diagnosis):
    report=evidence();report[check]['status']='fail'
    current='new' if diagnosis=='repaired' else 'old'
    with pytest.raises(ValueError,match=check):
        validate_submission(diagnosis,'old',current,current,report)


def test_only_checked_hash_can_be_submitted():
    with pytest.raises(ValueError,match='exact source hash'):
        validate_submission('repaired','old','new','older-check',evidence())
    assert validate_submission('repaired','old','new','new',evidence())['accepted']
    assert not validate_submission('needs_spec','old','old','old',evidence())['accepted']


def trace(rows,leak=False):
    values=[{'session':r['date'],'values':{'price':rows[i+1]['close'] if leak and i+1<len(rows) else None if leak else r['close']}} for i,r in enumerate(rows)]
    return {'status':'ok','run_id':str(len(rows)),'events':[],'native':{'indicators':values,'fills':[]}}


def test_one_bar_lookahead_must_fail_at_prefix_boundary():
    bars=[{'date':f'2024-01-{i+1:02d}','close':100+i} for i in range(10)]
    result=prefix_check(trace(bars,True),trace(bars[:5],True),bars,5)
    assert result['status']=='fail' and result['difference_count']==1
    assert result['compared_through']==bars[4]['date']
    assert prefix_check(trace(bars),trace(bars[:5]),bars,5)['status']=='pass'


def test_explicit_forced_exit_does_not_hide_last_bar_indicators():
    bars=[{'date':f'2024-01-{i+1:02d}','close':100+i} for i in range(10)]
    full,short=trace(bars),trace(bars[:5])
    short['native']['fills']=[{'session':bars[4]['date'],'qty':-1,'price':104,'fee':0,'exit_reason':'force_exit'}]
    short['events']=[{'kind':'order','session':bars[4]['date'],'order_id':'forced','qty':-1},{'kind':'fill','session':bars[4]['date'],'order_id':'forced','exit_reason':'force_exit'}]
    assert prefix_check(full,short,bars,5)['status']=='pass'
    short['native']['indicators'][-1]['values']['price']=999
    assert prefix_check(full,short,bars,5)['status']=='fail'


def financial_fixture():
    rules={'minimal_roi':{'0':.01},'stoploss':-.25,'use_exit_signal':True}
    spec={'accounting_profile':'cash_equity','position':{'initial_cash':1000,'multiplier':1},'costs':{'fee_rate':.01,'minimum_fee':0,'sell_tax':0},'native_exit_rules':rules}
    bars=[{'date':'2024-01-01','close':100},{'date':'2024-01-02','close':100}]
    fill={'session':'2024-01-01','qty':1,'price':100,'fee':1}
    result={'status':'ok','native':{'fills':[fill],'cash':899,'position':1,'equity':999},'events':[{'kind':'fill',**fill},{'kind':'execution_config','exit_rules':copy.deepcopy(rules)}]}
    return spec,bars,result


def test_wrong_or_missing_execution_config_is_rejected():
    spec,bars,result=financial_fixture()
    assert financial_check(spec,bars,result)['status']=='pass'
    result['events'][-1]['exit_rules']['stoploss']=-.9
    assert financial_check(spec,bars,result)['status']=='fail'
    result['events'].pop()
    assert financial_check(spec,bars,result)['status']=='fail'


def test_missing_native_account_is_not_a_pass():
    spec,bars,result=financial_fixture()
    result['native']['equity']=None
    assert financial_check(spec,bars,result)['status']=='fail'


@pytest.mark.parametrize('change',['source','bars','spec','image','policy'])
def test_cache_rejects_different_input_identity(tmp_path,change):
    project=tmp_path/'case'
    shutil.copytree(ROOT/'cases/vnpy_stale_orders',project)
    runtime={'vnpy_cta':{'image':'sha256:first'}}
    original=execution_identity(project,runtime,{'cutoff':.5})
    saved=tmp_path/'result.json';dump_json(saved,{'execution_identity':original})
    assert reuse_completed(saved,original)
    policy={'cutoff':.5}
    if change=='source':
        p=project/'strategy.py';p.write_text(p.read_text(encoding='utf-8').replace('fast_window = 10','fast_window = 11'),encoding='utf-8')
    elif change=='bars':
        p=project/'fixtures/bars.csv';p.write_bytes(p.read_bytes()+b'\n')
    elif change=='spec':
        p=project/'task.json';s=load_json(p);s['position']['initial_cash']+=1;dump_json(p,s)
    elif change=='image':runtime['vnpy_cta']['image']='sha256:second'
    else:policy['cutoff']=.6
    changed=execution_identity(project,runtime,policy)
    with pytest.raises(ValueError,match='identity changed'):
        reuse_completed(saved,changed)


def test_parameters_predicates_and_unrelated_methods_are_protected(tmp_path):
    original=tmp_path/'original.py';candidate=tmp_path/'candidate.py'
    text='class Strategy:\n    stoploss=-0.25\n    def signal(self,x):\n        if x>25:\n            return 0\n    def size(self):\n        return 1\n'
    original.write_text(text)
    policy={'editable_methods':['Strategy.signal']}
    candidate.write_text(text.replace('return 0','return 1'))
    assert check_preservation(original,candidate,policy)['status']=='pass'
    for changed in [text.replace('stoploss=-0.25','stoploss=-0.9'),text.replace('x>25','x>0'),text.replace('return 1','return 2')]:
        candidate.write_text(changed)
        assert check_preservation(original,candidate,policy)['status']=='fail'


def test_intraday_capability_and_release_visibility_use_same_clock(monkeypatch):
    spec=load_json(ROOT/'cases/vnpy_stale_orders/task.json')
    assert capabilities(spec)['frequency']=='1m'
    rows=[{'date':'2024-01-01T00:00:00'},{'date':'2024-01-01T00:01:00'}]
    recorder=Recorder(spec,rows)
    monkeypatch.setattr(fixture_api,'_recorder',recorder)
    monkeypatch.setattr(fixture_api,'_releases',[{'event_time':'2024-01-01T00:00:00+00:00','available_at':'2024-01-01T00:01:30+00:00','value':'5'}])
    assert fixture_api.latest_release(rows[0]['date'])==0
    assert fixture_api.latest_release(rows[1]['date'])==5

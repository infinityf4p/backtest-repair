import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from defect_checks import check_contract

def test_missing_exit_signal_is_not_a_causality_problem():
    conditions={'enter_long':[['adx','>',25],['mom','<',0],['minus_di','>',25],['plus_di','<','minus_di']], 'exit_long':[['adx','>',25],['mom','>',0],['minus_di','>',25],['plus_di','>','minus_di']]}
    bars=[{'date':'2024-01-01T00:00:00'},{'date':'2024-01-01T01:00:00'}]
    features=[{'session':bars[0]['date'],'values':{'adx':30,'mom':-1,'minus_di':30,'plus_di':20}}, {'session':bars[1]['date'],'values':{'adx':30,'mom':1,'minus_di':30,'plus_di':40}}]
    result={'status':'ok','native':{'indicators':features},'events':[{'kind':'signal','session':bars[0]['date'],'signal':1,'exit_signal':0},{'kind':'signal','session':bars[1]['date'],'signal':0,'exit_signal':1}]}
    assert check_contract({'signal_conditions':conditions},bars,result)['status']=='pass'
    result['events'][1]['exit_signal']=0
    failed=check_contract({'signal_conditions':conditions},bars,result)
    assert failed['status']=='fail' and failed['violation_count']==1

def test_an_unfilled_order_gets_one_matching_opportunity():
    spec={'order_validity_bars':1,'max_abs_position':1}
    order={'kind':'order','order_id':'A','bar_index':0,'session':'2024-01-01T00:00:00','qty':-1,'price':100}
    decision0={'kind':'decision','bar_index':0,'session':'2024-01-01T00:00:00'}
    decision1={'kind':'decision','bar_index':1,'session':'2024-01-01T00:01:00'}
    result={'status':'ok','native':{'fills':[{'qty':1}]},'events':[{'kind':'fill','qty':1,'session':'2024-01-01T00:00:00'},order,decision0,decision1]}
    assert check_contract(spec,[],result)['status']=='fail'
    for terminal in ['已撤销', '全部成交', '拒单', 'All Traded', 'Cancelled', 'Rejected', 'ALLTRADED']:
        fixed=copy.deepcopy(result)
        fixed['events'].insert(-1,{'kind':'order_status','order_id':'A','status':terminal})
        assert check_contract(spec,[],fixed)['status']=='pass', terminal

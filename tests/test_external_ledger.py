import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from external_eval import financial_check

def test_last_bar_liquidation_uses_final_account_phase():
    spec={'accounting_profile':'cash_equity','position':{'initial_cash':1000,'multiplier':1},'costs':{'fee_rate':0.01,'minimum_fee':0,'sell_tax':0}}
    bars=[{'date':'2024-01-01','close':100},{'date':'2024-01-02','close':110}]
    fills=[{'session':'2024-01-01','qty':1,'price':100,'fee':1},{'session':'2024-01-02','qty':-1,'price':110,'fee':1.1}]
    result={'status':'ok','native':{'cash':1007.9,'equity':1007.9,'position':0,'fills':fills},'events':[
        *[{'kind':'fill',**f} for f in fills],
        {'kind':'account','session':'2024-01-02','cash':899,'equity':1009,'position':1,'phase':'close'},
        {'kind':'account','session':'2024-01-02','cash':1007.9,'equity':1007.9,'position':0,'phase':'finalize'},
    ]}
    assert financial_check(spec,bars,result)['status']=='pass'
    result['events'][-1]['cash']=999
    assert financial_check(spec,bars,result)['status']=='fail'

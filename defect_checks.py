"""Checks derived from public trading contracts, never from the hidden upstream patch."""
import math

def near(a,b):
    if a is None or b is None:return a is b
    return math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=1e-6)

def check_contract(spec,bars,result):
    if result['status']!='ok':return {'status':'inconclusive','reason':result.get('error')}
    errors=[];details={};exercised=True
    features={r['session']:r['values'] for r in result['native'].get('indicators',[])}
    if spec.get('rolling_columns'):
        for column,rule in spec['rolling_columns'].items():
            window=rule['window'];source=rule['source'];n=0
            for i,row in enumerate(bars):
                expected=sum(b[source] for b in bars[i-window+1:i+1])/window if i>=window-1 else None
                observed=features.get(row['date'],{}).get(column)
                if not near(expected,observed):
                    errors.append({'rule':'trailing_window','session':row['date'],'column':column,'expected':expected,'observed':observed})
                n+=observed is not None
            details[column]={'observations':n,'window':window}
            exercised&=n>window
    if spec.get('signal_conditions'):
        observed={e['session']:e for e in result['events'] if e['kind']=='signal'}
        for name,conditions in spec['signal_conditions'].items():
            field='signal' if name=='enter_long' else 'exit_signal';positives=signals=0
            for row in bars:
                values=features.get(row['date'],{})
                truth=True
                for left,op,right in conditions:
                    a=values.get(left);b=values.get(right) if isinstance(right,str) else right
                    truth=truth and a is not None and b is not None and (a>b if op=='>' else a<b)
                actual=observed.get(row['date'],{}).get(field)
                positives+=int(truth);signals+=int(actual==1)
                if actual is None or bool(actual==1)!=bool(truth):
                    errors.append({'rule':'signal_predicate','signal':name,'session':row['date'],'expected':int(truth),'observed':actual,'indicators':values})
            details[name]={'predicate_true_bars':positives,'emitted_signals':signals}
            exercised&=positives>0
    if 'order_validity_bars' in spec:
        active={};stale_ids=set();decisions=0;position=0;largest=0
        for e in result['events']:
            if e['kind']=='order':active[e['order_id']]=e
            elif e['kind']=='order_status' and str(e.get('status','')).replace(' ','').upper() in ['全部成交','已撤销','拒单','ALLTRADED','CANCELLED','REJECTED']:
                active.pop(e['order_id'],None)
            elif e['kind']=='fill':
                position+=e['qty'];largest=max(largest,abs(position))
                if abs(position)>spec.get('max_abs_position',float('inf'))+1e-9:
                    errors.append({'rule':'max_abs_position','session':e['session'],'position':position,'limit':spec['max_abs_position']})
            elif e['kind'] in ['decision','signal']:
                decisions+=1
                for oid,order in active.items():
                    if e['bar_index']-order['bar_index']>=spec['order_validity_bars']:
                        stale_ids.add(oid)
                        errors.append({'rule':'expired_order_still_active','session':e['session'],'order_id':oid,'created_session':order['session'],'age_bars':e['bar_index']-order['bar_index'],'qty':order['qty'],'price':order.get('price')})
        details['order_lifetime']={'decisions':decisions,'distinct_stale_orders':len(stale_ids),'max_abs_position_observed':largest,'native_fill_count':len(result['native'].get('fills',[]))}
        exercised&=decisions>0 and bool(result['native'].get('fills'))
    return {'status':'fail' if errors else 'pass' if exercised and details else 'inconclusive','violation_count':len(errors),'violation_kinds':{k:sum(e['rule']==k for e in errors) for k in sorted({e['rule'] for e in errors})},'examples':errors[:6],'coverage':details}

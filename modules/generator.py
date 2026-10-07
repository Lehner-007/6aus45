"""Uniform integer-rank sampling and explicit hard filters/weighted selection."""
import random,json,heapq,math
from .database import TOTAL,rank,unrank,utc
from .statistics import analyze
ALGORITHM='rank-sample-1'

def accepts(ns,rules):
    s=set(ns)
    if not set(rules.get('include',[]))<=s or set(rules.get('exclude',[]))&s:return False
    even=sum(n%2==0 for n in ns)
    if 'even' in rules and even!=rules['even']:return False
    if 'sum_min' in rules and sum(ns)<rules['sum_min']:return False
    if 'sum_max' in rules and sum(ns)>rules['sum_max']:return False
    if 'neighbors_max' in rules and sum(b==a+1 for a,b in zip(ns,ns[1:]))>rules['neighbors_max']:return False
    if 'regions' in rules and [sum(lo<=n<=hi for n in ns) for lo,hi in [(1,15),(16,30),(31,45)]]!=rules['regions']:return False
    return True

def check_rules(rules):
    if not isinstance(rules,dict):raise ValueError('rules')
    allowed={'include','exclude','even','sum_min','sum_max','neighbors_max','regions','overlap_max','weight'}
    if set(rules)-allowed:raise ValueError('unknown_rule')
    for key in ('include','exclude'):
        ns=rules.get(key,[])
        if not isinstance(ns,list) or any(type(n)is not int or not 1<=n<=45 for n in ns) or len(ns)!=len(set(ns)):raise ValueError('rule_numbers')
    inc=set(rules.get('include',[]));exc=set(rules.get('exclude',[]))
    if len(inc)>6 or len(exc)>39 or inc&exc:raise ValueError('impossible_rules')
    for key,lo,hi in [('even',0,6),('neighbors_max',0,5),('overlap_max',0,6),('sum_min',21,255),('sum_max',21,255)]:
        if key in rules and (type(rules[key])is not int or not lo<=rules[key]<=hi):raise ValueError('rule_range')
    if rules.get('sum_min',21)>rules.get('sum_max',255):raise ValueError('impossible_sum')
    if 'regions' in rules and (not isinstance(rules['regions'],list) or len(rules['regions'])!=3 or any(type(n)is not int or not 0<=n<=6 for n in rules['regions']) or sum(rules['regions'])!=6):raise ValueError('regions')
    if rules.get('weight') not in (None,'frequent','rare','absent'):raise ValueError('weight')

def generate(db,n=10,game='lotto',seed=None,rules=None,statistics_enabled=False,exclude_drawn=False,exclude_used=False,period=None,context=None):
    if type(n)is not int or n<=0:raise ValueError('positive_count')
    rules=(rules or {}) if statistics_enabled else {};check_rules(rules)
    if game not in ('lotto','joker'):raise ValueError('game')
    if game=='joker' and rules:raise ValueError('lotto_rules_only')
    rng=random.Random(seed);size=TOTAL if game=='lotto' else 1000000
    column='combination_id' if game=='lotto' else 'joker';excluded=set()
    if exclude_drawn:excluded.update(r[0] for r in db.conn.execute(f'SELECT {column} FROM draws WHERE game=? AND {column} IS NOT NULL',(game,)))
    if exclude_used:excluded.update(r[0] for r in db.conn.execute(f'SELECT {column} FROM tips WHERE {column} IS NOT NULL'))
    if game=='joker':excluded={int(v)+1 for v in excluded}
    else:excluded={int(v) for v in excluded}
    available=size-len(excluded)
    if n>available:raise ValueError('count_exceeds_available')
    period=period or {};weight=rules.get('weight');weights={}
    if weight:
        history=db.draw_rows('lotto',**period)
        if not history:raise ValueError('statistics_empty')
        stats=analyze(history)
        for r in stats['frequency']:
            weights[r['number']]={'frequent':r['count']+1,'rare':1/(r['count']+1),'absent':(r['current_gap'] if r['current_gap'] is not None else len(history))+1}[weight]
    settings=dict(seed=seed,algorithm=ALGORITHM,rules=rules,statistics_enabled=statistics_enabled,exclude_drawn=exclude_drawn,exclude_used=exclude_used,period=period,available=available,weights=weights)
    # Exact candidate list is only compact 32-bit identifiers, never millions of GUI records.
    candidates=None
    if rules or excluded:
        from array import array
        candidates=array('I')
        if game=='lotto':
            clauses=[];params=[]
            for key,ns in [('include',rules.get('include',[])),('exclude',rules.get('exclude',[]))]:
                for number in ns:
                    clauses.append('?' + (' IN ' if key=='include' else ' NOT IN ')+'(n1,n2,n3,n4,n5,n6)');params.append(number)
            if 'even' in rules:clauses.append('(n1%2=0)+(n2%2=0)+(n3%2=0)+(n4%2=0)+(n5%2=0)+(n6%2=0)=?');params.append(rules['even'])
            for key,op in [('sum_min','>='),('sum_max','<=')]:
                if key in rules:clauses.append('n1+n2+n3+n4+n5+n6'+op+'?');params.append(rules[key])
            if 'neighbors_max' in rules:clauses.append('(n2=n1+1)+(n3=n2+1)+(n4=n3+1)+(n5=n4+1)+(n6=n5+1)<=?');params.append(rules['neighbors_max'])
            if 'regions' in rules:
                for (lo,hi),value in zip([(1,15),(16,30),(31,45)],rules['regions']):clauses.append('+'.join(f'(n{i} BETWEEN {lo} AND {hi})' for i in range(1,7))+'=?');params.append(value)
            # Rules need the full universe to establish exact availability.
            if db.summary()['combinations']!=TOTAL:raise ValueError('build_inventory_first')
            cursor=db.conn.execute('SELECT id FROM combinations'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY id',params)
            for index,row in enumerate(cursor):
                if context and index%10000==0:context.check_cancel()
                if row[0] not in excluded:candidates.append(row[0])
        else:
            candidates=array('I',(i for i in range(1,size+1) if i not in excluded))
        available=len(candidates);settings['available']=available
        if n>available:raise ValueError('count_exceeds_filtered')
    population=candidates if candidates is not None else range(1,size+1)
    if weight:
        # Exponential race: weighted sampling without replacement, bounded O(N) heap.
        selected=[]
        for i,identifier in enumerate(population):
            if context and i%10000==0:context.check_cancel()
            value=math.prod(weights[x] for x in unrank(identifier));key=math.log(max(rng.random(),1e-300))/value
            if len(selected)<n:heapq.heappush(selected,(key,identifier))
            elif key>selected[0][0]:heapq.heapreplace(selected,(key,identifier))
        ids=[v for _,v in selected]
    else:ids=rng.sample(population,n)
    max_overlap=rules.get('overlap_max')
    if max_overlap==0 and n>7:raise ValueError('impossible_overlap')
    if max_overlap is not None and max_overlap<6:
        chosen=[];pool=list(ids);visited=set(ids);budget=min(size,max(10000,n*100))
        for attempt in range(budget):
            if context and attempt%100==0:context.check_cancel()
            if not pool:
                identifier=rng.choice(population)
                if identifier in visited:continue
                visited.add(identifier)
            else:identifier=pool.pop()
            ns=unrank(identifier)
            if all(len(set(ns)&set(unrank(other)))<=max_overlap for other in chosen):chosen.append(identifier)
            if len(chosen)==n:break
        if len(chosen)!=n:raise ValueError('overlap_search_limit')
        ids=chosen
    with db.conn:series=db.conn.execute('INSERT INTO series(created,game,method,requested,settings,status) VALUES(?,?,?,?,?,?)',(utc(),game,'weighted' if weight else 'uniform',n,json.dumps(settings),'running')).lastrowid
    try:
        for start in range(0,n,1000):
            if context:context.check_cancel()
            with db.conn:
                for i,identifier in enumerate(ids[start:start+1000],start+1):
                    if game=='lotto':db.ensure_combination(unrank(identifier));db.conn.execute('INSERT INTO tips VALUES(?,?,?,NULL)',(series,i,identifier))
                    else:
                        number=f'{identifier-1:06d}';db.conn.execute('INSERT OR IGNORE INTO joker_numbers VALUES(?)',(number,));db.conn.execute('INSERT INTO tips VALUES(?,?,NULL,?)',(series,i,number))
            if context:context.progress(min(start+1000,n),n)
    except Exception:
        with db.conn:db.conn.execute("UPDATE series SET status='partial' WHERE id=?",(series,))
        raise
    with db.conn:db.conn.execute("UPDATE series SET status='complete' WHERE id=?",(series,))
    return {'series':series,'count':n,'available':available}

def series_tips(db,series,offset=0,limit=100):
    return [dict(r) for r in db.conn.execute('SELECT t.*,c.n1,c.n2,c.n3,c.n4,c.n5,c.n6 FROM tips t LEFT JOIN combinations c ON c.id=t.combination_id WHERE series_id=? ORDER BY t.id LIMIT ? OFFSET ?',(series,limit,offset))]

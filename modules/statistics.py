"""Descriptive statistics; no predictions or invented prize amounts."""
from collections import Counter,defaultdict
from itertools import combinations
from statistics import mean
from datetime import date

def numbers(row):return tuple(row['n'+str(i)] for i in range(1,7))
def suffix_hits(a,b):
    count=0
    for x,y in zip(reversed(a),reversed(b)):
        if x!=y:break
        count+=1
    return count

def analyze(rows,game='lotto',previous=None,triples=False):
    if game=='joker':
        digits=[Counter() for _ in range(6)];ends={i:Counter() for i in range(1,7)};seen=defaultdict(list)
        for index,row in enumerate(rows):
            for i,c in enumerate(row['joker']):digits[i][c]+=1
            for i in ends:ends[i][row['joker'][-i:]]+=1
            seen[row['joker']].append((index,row['date']))
        return dict(count=len(rows),positions=[dict(c) for c in digits],endings={i:dict(c) for i,c in ends.items()},repeated={n:v for n,v in seen.items() if len(v)>1},repeat_distances={n:[b[0]-a[0] for a,b in zip(v,v[1:])] for n,v in seen.items() if len(v)>1})
    count=len(rows);main=Counter();extra=Counter();seen=defaultdict(list);pairs=Counter();three=Counter();shape=[];repeats=defaultdict(list)
    last=set(numbers(previous)) if previous else None
    for i,row in enumerate(rows):
        ns=numbers(row);main.update(ns)
        if row['extra'] is not None:extra[row['extra']]+=1
        pairs.update(combinations(ns,2))
        if triples:three.update(combinations(ns,3))
        for n in ns:seen[n].append((i,row['date']))
        repeats[ns].append(row['date'])
        gaps=[b-a for a,b in zip(ns,ns[1:])];runs=[];run=1
        for gap in gaps:
            if gap==1:run+=1
            else:runs.append(run);run=1
        runs.append(run)
        shape.append(dict(date=row['date'],even=sum(n%2==0 for n in ns),odd=sum(n%2==1 for n in ns),regions=[sum(lo<=n<=hi for n in ns) for lo,hi in [(1,15),(16,30),(31,45)]],sum=sum(ns),span=ns[-1]-ns[0],min=ns[0],max=ns[-1],gaps=gaps,neighbors=gaps.count(1),longest_run=max(runs),previous_overlap=len(set(ns)&last) if last is not None else None));last=set(ns)
    frequency=[]
    for n in range(1,46):
        obs=seen[n];distances=[b[0]-a[0] for a,b in zip(obs,obs[1:])]
        frequency.append(dict(number=n,count=main[n],relative=main[n]/count if count else 0,expected=count*6/45,last=obs[-1][1] if obs else None,current_gap=count-1-obs[-1][0] if obs else None,mean_gap=mean(distances) if distances else None,max_gap=max(distances) if distances else None,left_edge_incomplete=True,right_edge_incomplete=True,extra_count=extra[n]))
    ranked=sorted(frequency,key=lambda r:(-r['count'],r['number']))
    ranks={r['count']:i+1 for i,r in reversed(list(enumerate(ranked)))}
    for r in frequency:r['rank']=ranks[r['count']]
    return dict(count=count,frequency=frequency,pairs=[{'numbers':k,'count':v} for k,v in pairs.most_common()],triples=[{'numbers':k,'count':v} for k,v in three.most_common()],shape=shape,repeated=[{'numbers':k,'dates':v} for k,v in repeats.items() if len(v)>1])

def historic_match(tips,rows,game='lotto'):
    result=[]
    for tip in tips:
        counts=Counter();matches=[]
        for row in rows:
            hit=suffix_hits(tip,row['joker']) if game=='joker' else len(set(tip)&set(numbers(row)))
            extra=False if game=='joker' else row['extra'] in tip
            counts[hit]+=1
            if hit or extra:matches.append({'date':row['date'],'hits':hit,'extra':extra})
        result.append({'tip':tip,'counts':{i:counts[i] for i in range(7)},'draws':matches})
    return result

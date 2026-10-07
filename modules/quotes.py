"""Prize evidence adapted from the archived 6aus45 project; never infer payouts."""
import re
from decimal import Decimal

def quote(label, winners, amount, currency, rule):
    winners, amount = winners.strip(), amount.strip()
    count = int(winners.replace('.', '')) if re.fullmatch(r'[0-9.]+', winners) else None
    jackpot = 'JP' in winners.upper() or 'JACKPOT' in winners.upper()
    value = Decimal(re.sub(r'\s+', '', amount).replace('.', '').replace(',', '.')) * 100 if amount else None
    if value is not None and (value < 0 or value != value.to_integral_value()):
        raise ValueError('invalid_quote_amount')
    return dict(rank=label.replace(' ', ''), rule=rule, winners=0 if jackpot else count,
                currency=currency, amount=int(value) if value is not None else None,
                kind='jackpot' if jackpot else 'per_winner' if count else 'unknown',
                status=winners if count is None else '', raw_winners=winners, raw_amount=amount)

def normalize_old(q):
    return dict(rank=q['klasse'],rule=q['regelwerk'],winners=q['gewinner'],currency=q['waehrung'],
                amount=q['betrag_hundertstel'],kind={'je_gewinn':'per_winner','jackpot':'jackpot'}.get(q['betrag_art'],'unknown'),
                status=q['status'])

def validate_quotes(values):
    if not isinstance(values,list) or len(values)>8:raise ValueError('invalid_quotes')
    ranks=set()
    for q in values:
        if not isinstance(q,dict) or not isinstance(q.get('rank'),str) or not q['rank'] or q['rank'] in ranks:raise ValueError('invalid_quote_rank')
        ranks.add(q['rank'])
        if q.get('currency') not in ('EUR','ATS') or q.get('kind') not in ('jackpot','per_winner','unknown'):raise ValueError('invalid_quote_currency')
        if not isinstance(q.get('rule'),str) or not isinstance(q.get('status',''),str):raise ValueError('invalid_quote_rule')
        for key in ('amount','winners'):
            if q.get(key) is not None and (type(q[key]) is not int or q[key]<0):raise ValueError('invalid_quote_value')
    return values

def store_quotes(db,draw_id,source_id,values):
    snapshot=list(db.conn.execute('SELECT combination_id,extra,joker FROM draws WHERE id=?',(draw_id,)).fetchone())
    for q in validate_quotes(values):
        q=dict(q,_draw_result=snapshot)
        # Each original source snapshot remains separate. A conflicting source cannot erase evidence.
        db.conn.execute('INSERT OR IGNORE INTO quotes(draw_id,source_id,rank,rule,winners,currency,amount,kind,status,original) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (draw_id,source_id,q['rank'],q['rule'],q.get('winners'),q['currency'],q.get('amount'),q['kind'],q.get('status',''),__import__('json').dumps(q,ensure_ascii=False)))

def for_draw(db,draw_id):
    rows=db.conn.execute('SELECT q.*,s.url FROM quotes q JOIN sources s ON s.id=q.source_id WHERE draw_id=? ORDER BY q.source_id DESC,q.id',(draw_id,)).fetchall()
    import json
    current=db.conn.execute('SELECT combination_id,extra,joker FROM draws WHERE id=?',(draw_id,)).fetchone()
    rows=[row for row in rows if current and json.loads(row['original']).get('_draw_result')==list(current)]
    chosen={}
    for row in rows:
        q=dict(row);key=(q['rank'],q['currency'])
        if key not in chosen or chosen[key]['amount'] is None and q['amount'] is not None:chosen[key]=q
    order={'6er':0,'5er+ZZ':1,'5er':2,'4er+ZZ':3,'4er':4,'3er+ZZ':5,'3er':6,'ZZ':7}
    result=sorted(chosen.values(),key=lambda q:(int(q['rank']) if q['rank'].isdigit() else order.get(q['rank'],99),q['currency']))
    for q in result:
        variants={(r['winners'],r['amount'],r['kind']) for r in rows if r['rank']==q['rank'] and r['currency']==q['currency'] and r['amount'] is not None}
        q['conflicting']=len(variants)>1
    return result

import csv
import datetime as dt
def parse_joker_csv(raw, filename):
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: text = raw.decode('cp1252')
    year = int(re.search(r'Joker_(\d{4})',filename)[1]); records,issues=[],[]
    for lineno,row in enumerate(csv.reader(text.splitlines(),delimiter=';'),1):
        if not row or not any(row) or row[0]=='Datum': continue
        try:
            match=re.fullmatch(r'\w+\s+(\d+)\.(\d+)\.',row[0].strip())
            if not match: raise ValueError('Unbekanntes Datum')
            digits=[Decimal(x.replace(',','.')) for x in row[1:7]]
            if len(digits)!=6 or any(d!=int(d) or d<0 or d>9 for d in digits): raise ValueError('Ungültige Jokerziffer')
            qs=[quote('1',row[7],row[9],'EUR','6_rang_pdf')]
            qs.extend(quote(str(rank),count,'','EUR','6_rang_pdf') for rank,count in enumerate(row[10:15],2))
            if len(qs)!=6: raise ValueError('Fehlende Gewinnklassen')
            records.append({'spiel':'joker','datum':dt.date(year,int(match[2]),int(match[1])).isoformat(),'nummer':''.join(str(int(d)) for d in digits),'quoten':qs,'zeile':lineno})
        except (ValueError,IndexError,ArithmeticError) as e: issues.append((lineno,f'L003: {e}',row))
    if not records: raise ValueError('L003: Keine Joker-Ziehungen erkannt')
    return records,issues


def joker_csv(path):
    from pathlib import Path
    path=Path(path);records,issues=parse_joker_csv(path.read_bytes(),path.name)
    return [dict(game='joker',date=r['datum'],joker=r['nummer'],line=r['zeile'],quotes=r['quoten']) for r in records],[dict(line=line,reason=message,row=row) for line,message,row in issues]

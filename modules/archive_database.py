"""Read-only draw and prize transfer from archived or current 6aus45 SQLite databases."""
import sqlite3,json
from pathlib import Path
from .quotes import normalize_old

def read_database(path):
    path=Path(path).resolve()
    con=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    try:
        if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('invalid_archive_database')
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        records=[]
        if {'lotto_ziehungen','joker_ziehungen','lotto_tipps','gewinnklassen'}.issubset(tables):
            for game in ('lotto','joker'):
                source_rows=con.execute(f'SELECT e.ziehung_id,s.uri,s.sha256,e.zeile FROM {game}_quellen e JOIN import_quellen s ON s.id=e.quelle_id').fetchall() if game+'_quellen' in tables else []
                provenance={}
                for row in source_rows:provenance.setdefault(row[0],[]).append(dict(url=row[1],sha256=row[2],line=row[3]))
                prizes={}
                for row in con.execute(f'SELECT q.*,k.code,k.regelwerk FROM {game}_quoten q JOIN gewinnklassen k ON k.id=q.klasse_id'):
                    old=dict(klasse=row['code'],regelwerk=row['regelwerk'],gewinner=row['gewinner'],waehrung=row['waehrung'],betrag_hundertstel=row['betrag_hundertstel'],betrag_art=row['betrag_art'],status=row['status'])
                    q=normalize_old(old);q['archived_original']=json.loads(row['original']);q['archived_sources']=provenance.get(row['ziehung_id'],[])
                    prizes.setdefault(row['ziehung_id'],[]).append(q)
                sql='SELECT d.*,t.n1,t.n2,t.n3,t.n4,t.n5,t.n6 FROM lotto_ziehungen d JOIN lotto_tipps t ON t.id=d.tipp_id' if game=='lotto' else 'SELECT * FROM joker_ziehungen'
                for row in con.execute(sql+' ORDER BY datum,kennung,id'):
                    r=dict(game=game,date=row['datum'],line=row['id'],identity='' if row['kennung']=='haupt' else row['kennung'],quotes=prizes.get(row['id'],[]),archived_sources=provenance.get(row['id'],[]),archived_extras=row['extras'])
                    if game=='lotto':r.update(numbers=[row['n'+str(i)] for i in range(1,7)],extra=row['zusatzzahl'])
                    else:r['joker']=row['nummer']
                    records.append(r)
        elif {'draws','combinations','sources'}.issubset(tables):
            from .quotes import for_draw
            class View:pass
            view=View();view.conn=con
            for row in con.execute('SELECT d.*,c.n1,c.n2,c.n3,c.n4,c.n5,c.n6 FROM draws d LEFT JOIN combinations c ON c.id=d.combination_id ORDER BY date,time,identity,id'):
                r=dict(game=row['game'],date=row['date'],time=row['time'],identity=row['identity'],official_id=row['official_id'],draw_type=row['draw_type'],line=row['id'])
                if row['game']=='joker':r['joker']=row['joker']
                else:r.update(numbers=[row['n'+str(i)] for i in range(1,7)],extra=row['extra'])
                if 'quotes' in tables:r['quotes']=[json.loads(q['original']) for q in for_draw(view,row['id'])]
                records.append(r)
        else:raise ValueError('unsupported_archive_database')
        from .importers import validate
        valid=[];invalid=[]
        for r in records:
            try:valid.append(validate(r))
            except (ValueError,TypeError,KeyError) as error:invalid.append(dict(line=r['line'],row=r,reason=str(error)))
        return valid,invalid
    finally:con.close()

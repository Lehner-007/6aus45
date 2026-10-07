"""Verified Win2day CSV epochs / Joker PDF rows plus strict JSON/CSV interchange."""
import csv,json,re,hashlib,subprocess,time
from pathlib import Path
from datetime import date
from urllib.parse import urlparse,urljoin
import requests
from bs4 import BeautifulSoup
from .database import validate_numbers,utc
PARSER='win2day-quotes-2'
from .quotes import quote,validate_quotes,store_quotes
PAGES={'lotto':'https://www.win2day.at/lotterie/lotto/lotto-statistik-zahlen-ergebnisse-download','joker':'https://www.win2day.at/lotterie/joker-statistik'}

def validate(record):
    r=dict(record);date.fromisoformat(r['date'])
    if r['game'] not in ('lotto','joker','lottoplus'):raise ValueError('game')
    if r['game']=='joker':
        if not isinstance(r.get('joker'),str) or not re.fullmatch(r'[0-9]{6}',r['joker']):raise ValueError('joker')
    else:
        r['numbers']=list(validate_numbers(r['numbers']))
        extra=r.get('extra')
        if extra is not None and (type(extra)is not int or not 1<=extra<=45 or extra in r['numbers']):raise ValueError('extra')
        order=r.get('order')
        if order is not None and (len(order)!=6 or sorted(order)!=r['numbers']):raise ValueError('draw_order')
    if 'quotes' in r:validate_quotes(r['quotes'])
    return r

def day(raw,year):
    m=re.fullmatch(r'\s*(\d{1,2})\.(\d{1,2})\.(?:(\d{4}))?\s*',raw)
    if not m:raise ValueError('date')
    return date(int(m[3] or year),int(m[2]),int(m[1])).isoformat()

def lotto_csv(path):
    path=Path(path);match=re.search(r'_(\d{4})\.csv$',path.name);year=int(match[1]) if match else None
    raw=path.read_bytes().decode('utf-8-sig') if path.read_bytes().startswith(b'\xef\xbb\xbf') else path.read_bytes().decode('cp1252')
    records=[];rejected=[];previous=None;currency='EUR'
    for line,row in enumerate(csv.reader(raw.splitlines(),delimiter=';'),1):
        row=[v.strip() for v in row]
        for field in row[:2]:
            m=re.match(r'^(19\d{2}|20\d{2})\s+Lotto',field)
            if m:
                year=int(m[1]);currency='ATS' if 'ATS' in field else 'EUR';previous=None
        try:
            if len(row)>10 and re.match(r'^\d{1,2}\.\d{1,2}\.',row[0]) and row[1]=='aufsteigend':
                r={'game':'lotto','date':day(row[0],year),'numbers':[int(v) for v in row[2:8]],'extra':int(row[9]),'line':line}
            elif len(row)>10 and row[2]=='aufsteigend':
                r={'game':'lotto','date':day(row[1],year),'numbers':[int(v) for v in row[3:9]],'extra':int(row[10]),'line':line}
            elif len(row)>9 and re.match(r'^\d{1,2}\.\d{1,2}\.',row[1]) and row[8].lower().startswith('zz'):
                r={'game':'lotto','date':day(row[1],year),'numbers':[int(v) for v in row[2:8]],'extra':int(row[9]),'line':line}
            elif previous and len(row)>10 and (row[2]=='gezogen' or (row[1]=='' and row[10] and row[0])):
                if row[0] and day(row[0],year)!=previous['date']:raise ValueError('quote_date')
                start=11 if row[2]=='gezogen' else 10
                previous['quotes'].extend(quote(row[i],row[i+1],row[i+3],currency,'8_rang') for i in range(start,start+16,4) if row[i])
                continue
            else:continue
            if row[1]=='aufsteigend' or row[2]=='aufsteigend':
                start=10 if row[1]=='aufsteigend' else 11
                r['quotes']=[quote(row[i],row[i+1],row[i+3],currency,'8_rang') for i in range(start,min(start+16,len(row)-3),4) if row[i]]
            else:
                r['quotes']=[quote(label,row[i],row[i+2],currency,'5_rang') for label,i in zip(['6er','5er+ZZ','5er','4er','3er'],range(10,25,3)) if len(row)>i+2]
            r=validate(r);records.append(r);previous=r
        except (ValueError,TypeError,IndexError) as e:rejected.append({'line':line,'row':row,'reason':str(e)});previous=None
    if not records:raise ValueError('unknown_csv_format')
    return records,rejected

def joker_pdf(path):
    path=Path(path);m=re.search(r'_(\d{4})\.pdf$',path.name)
    if not m:raise ValueError('joker_pdf_year')
    year=int(m[1]);result=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,check=True,timeout=60)
    text=result.stdout.decode('utf-8');records=[];rejected=[]
    pattern=re.compile(r'^\s*(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?\s+(\d{1,2}\.\d{1,2}\.)\s+([0-9])\s+([0-9])\s+([0-9])\s+([0-9])\s+([0-9])\s+([0-9])(?:\s|$)')
    for line,s in enumerate(text.splitlines(),1):
        match=pattern.match(s)
        if match:
            try:
                rest=[v for v in s[match.end():].split() if v!='à']
                if len(rest)!=7:raise ValueError('pdf_quote_columns')
                qs=[quote('1',rest[0],rest[1],'EUR','6_rang_pdf')]
                qs.extend(quote(str(rank),count,'','EUR','6_rang_pdf') for rank,count in enumerate(rest[2:],2))
                records.append(validate({'game':'joker','date':day(match[1],year),'joker':''.join(match.groups()[1:]),'line':line,'quotes':qs}))
            except ValueError as e:rejected.append({'line':line,'row':s,'reason':str(e)})
        elif re.match(r'^\s*(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?\s+\d{1,2}\.\d{1,2}\.',s):rejected.append({'line':line,'row':s,'reason':'pdf_row_format'})
    if not records:raise ValueError('unknown_pdf_format')
    return records,rejected

def read_source(path):
    path=Path(path)
    if path.suffix.lower() in ('.sqlite','.sqlite3','.db'):
        from .archive_database import read_database
        return read_database(path)
    if path.suffix.lower()=='.pdf':return joker_pdf(path)
    if path.suffix.lower()=='.json':
        data=json.loads(path.read_text())
        if isinstance(data,dict) and data.get('game')=='JOKER':
            from .joker_quotes import read_api
            return read_api(path.read_bytes())
        raw=data['draws'] if isinstance(data,dict) else data
        valid=[];invalid=[]
        for i,r in enumerate(raw,1):
            try:valid.append(validate(dict(r,line=i)))
            except (ValueError,KeyError,TypeError) as e:invalid.append({'line':i,'row':r,'reason':str(e)})
        return valid,invalid
    if re.search(r'Joker_\d{4}\.csv$',path.name):
        from .quotes import joker_csv
        return joker_csv(path)
    first=path.read_text(encoding='cp1252').splitlines()[0]
    if first.startswith('game;date;'):
        rows=list(csv.DictReader(path.read_text(encoding='utf-8-sig').splitlines(),delimiter=';'));valid=[];invalid=[]
        for i,r in enumerate(rows,2):
            try:
                if r['game']!='joker':r['numbers']=[int(n) for n in r['numbers'].split(',')];r['extra']=int(r['extra']) if r.get('extra') else None
                valid.append(validate(dict(r,line=i)))
            except (ValueError,KeyError,TypeError) as e:invalid.append({'line':i,'row':r,'reason':str(e)})
        return valid,invalid
    return lotto_csv(path)

def preview(db,records,rejected):
    counts={'new':0,'existing':0,'conflicts':0,'invalid':len(rejected)}
    for r in records:
        old=db.conn.execute('SELECT * FROM draws WHERE game=? AND date=? AND time=? AND identity=?',(r['game'],r['date'],r.get('time',''),r.get('identity',''))).fetchone()
        if not old:counts['new']+=1;continue
        from .database import rank
        equal=(old['joker']==r.get('joker')) if r['game']=='joker' else (old['combination_id']==rank(r['numbers']) and old['extra']==r.get('extra'))
        counts['existing' if equal else 'conflicts']+=1
    return counts

def import_records(db,records,rejected,url,checksum,context=None):
    counts=preview(db,records,rejected)
    with db.conn:
        db.conn.execute('INSERT OR IGNORE INTO sources(url,sha256,retrieved,parser) VALUES(?,?,?,?)',(url,checksum,utc(),PARSER))
        sid=db.conn.execute('SELECT id FROM sources WHERE url=? AND sha256=?',(url,checksum)).fetchone()[0]
        run=db.conn.execute('INSERT INTO import_runs(source_id,started) VALUES(?,?)',(sid,utc())).lastrowid
        for x in rejected:db.conn.execute('INSERT INTO rejected(source_id,line,record,reason) VALUES(?,?,?,?)',(sid,x.get('line'),json.dumps(x.get('row'),ensure_ascii=False),x['reason']))
    for i,r in enumerate(records):
        if context:context.check_cancel()
        r=validate(r)
        with db.conn:
            combo=db.ensure_combination(r['numbers']) if r['game']!='joker' else None
            if r['game']=='joker':db.conn.execute('INSERT OR IGNORE INTO joker_numbers VALUES(?)',(r['joker'],))
            key=(r['game'],r['date'],r.get('time',''),r.get('identity',''))
            old=db.conn.execute('SELECT * FROM draws WHERE game=? AND date=? AND time=? AND identity=?',key).fetchone()
            if old:
                identifier=old['id']
                if (old['combination_id'],old['extra'],old['joker'])!=(combo,r.get('extra'),r.get('joker')):
                    record=json.dumps(r,sort_keys=True)
                    if not db.conn.execute('SELECT 1 FROM conflicts WHERE draw_id=? AND source_id=? AND record=?',(identifier,sid,record)).fetchone():db.conn.execute('INSERT INTO conflicts(draw_id,source_id,record,created) VALUES(?,?,?,?)',(identifier,sid,record,utc()))
                elif r.get('order') and old['draw_order'] in (None,'null'):db.conn.execute('UPDATE draws SET draw_order=? WHERE id=?',(json.dumps(r['order']),identifier))
            else:
                identifier=db.conn.execute('INSERT INTO draws(game,date,time,identity,draw_type,official_id,combination_id,extra,draw_order,joker) VALUES(?,?,?,?,?,?,?,?,?,?)',(*key,r.get('draw_type','unspecified'),r.get('official_id'),combo,r.get('extra'),json.dumps(r.get('order')),r.get('joker'))).lastrowid
            db.conn.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?)',(identifier,sid,r.get('line')))
            if not old or (old['combination_id'],old['extra'],old['joker'])==(combo,r.get('extra'),r.get('joker')):
                store_quotes(db,identifier,sid,r.get('quotes',[]))
        if context and i%50==0:context.progress(i+1,len(records))
    with db.conn:db.conn.execute('UPDATE import_runs SET finished=?,counts=? WHERE id=?',(utc(),json.dumps(counts),run))
    return counts

def import_file(db,path,url=None,context=None):
    path=Path(path);records,rejected=read_source(path)
    return import_records(db,records,rejected,url or path.name,hashlib.sha256(path.read_bytes()).hexdigest(),context)

def fetch(url,path,context=None,allowed_hosts=None):
    allowed_hosts=set(allowed_hosts or ('www.win2day.at','statics.win2day.at','lotterien.win2day.at'))
    path=Path(path);temp=path.with_suffix(path.suffix+'.part')
    def check(u):
        parts=urlparse(u)
        if parts.scheme!='https' or parts.hostname not in allowed_hosts or parts.username or parts.password:raise ValueError('source_url')
    try:
        for attempt in range(3):
            try:
                current=url
                for redirect in range(6):
                    check(current)
                    response=requests.get(current,timeout=(10,30),stream=True,allow_redirects=False)
                    if response.status_code in (301,302,303,307,308):
                        next_url=urljoin(current,response.headers.get('Location',''));response.close()
                        if redirect==5:raise ValueError('source_redirect')
                        current=next_url;continue
                    break
                with response:
                    response.raise_for_status();size=0
                    with temp.open('wb') as out:
                        for block in response.iter_content(65536):
                            if context:context.check_cancel()
                            size+=len(block)
                            if size>30*1024*1024:raise ValueError('source_size')
                            out.write(block)
                temp.replace(path);return
            except requests.RequestException as e:
                if getattr(e.response,'status_code',None) in (401,403,404) or attempt==2:raise
                time.sleep(.5*(attempt+1))
    finally:temp.unlink(missing_ok=True)

def discover_and_update(db,folder,context=None,sources=None):
    from .source_settings import defaults,validate_sources
    from .model import atomic_json
    configured=validate_sources(defaults() if sources is None else sources)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    catalog_path=folder/'catalog.json'
    try:catalog=json.loads(catalog_path.read_text())
    except (OSError,ValueError):catalog=[]
    results=[];errors=[]
    for source in configured:
        if not source['enabled']:continue
        url=source['url'];game=source['game']
        hosts={urlparse(url).hostname}
        if urlparse(url).hostname in ('www.win2day.at','lotterien.win2day.at'):hosts.add('statics.win2day.at')
        try:
            if context:context.check_cancel()
            prefix=hashlib.sha256(url.encode()).hexdigest()[:12]
            if source['format']=='html':
                page=folder/(prefix+'-index.html');fetch(url,page,context,hosts)
                soup=BeautifulSoup(page.read_bytes(),'html.parser');links=[]
                for a in soup.select('a[href]'):
                    u=urljoin(url,a['href']);suffix=Path(urlparse(u).path).suffix.lower()
                    if suffix in (('.csv','.pdf') if game=='auto' else ('.csv',) if game=='lotto' else ('.pdf',)) and urlparse(u).hostname in hosts and u not in links:links.append(u)
                if not links:raise ValueError('no_archive_links')
            else:links=[url]
            for u in links:
                if context:context.check_cancel()
                filename=Path(urlparse(u).path).name
                if source['format']!='html' and not filename.lower().endswith('.'+source['format']):filename='source.'+source['format']
                name=hashlib.sha256(u.encode()).hexdigest()[:12]+'_'+filename
                staged=folder/(name+'.download');fetch(u,staged,context,hosts)
                checksum=hashlib.sha256(staged.read_bytes()).hexdigest()
                existing=next((r for r in catalog if r['sha256']==checksum and r['url']==u and (folder/r['file']).exists()),None)
                if existing:
                    name=existing['file'];target=folder/name;staged.unlink()
                else:
                    name=checksum[:12]+'_'+filename;target=folder/name;staged.replace(target)
                records,rejected=read_source(target)
                if game!='auto' and any(r['game']!=game for r in records):raise ValueError('source_game_mismatch')
                checksum=hashlib.sha256(target.read_bytes()).hexdigest()
                results.append(import_records(db,records,rejected,u,checksum,context))
                entry=dict(game=game,url=u,file=name,sha256=checksum)
                if entry not in catalog:catalog.append(entry)
        except (ValueError,OSError,requests.RequestException,subprocess.SubprocessError) as error:
            import logging
            logging.exception('Draw source failed: %s',source['name'])
            errors.append(dict(name=source['name'],reason=str(error)))
        finally:atomic_json(catalog_path,catalog)
    return dict(results=results,errors=errors)

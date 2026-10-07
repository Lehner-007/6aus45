"""Versioned SQLite storage, combinatorial ranking and resumable full inventory."""
from pathlib import Path
from math import comb
from itertools import islice
import sqlite3,json,shutil,time
from datetime import datetime,timezone
TOTAL=comb(45,6)
SCHEMA_VERSION=2

def utc():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def rank(numbers):
    ns=validate_numbers(numbers);r=0;last=0
    for i,n in enumerate(ns):
        for v in range(last+1,n):r+=comb(45-v,5-i)
        last=n
    return r+1

def unrank(identifier):
    if not 1<=identifier<=TOTAL:raise ValueError('combination_id')
    r=identifier-1;out=[];previous=0
    for i in range(6):
        for v in range(previous+1,46):
            width=comb(45-v,5-i)
            if r<width:out.append(v);previous=v;break
            r-=width
    return tuple(out)

def validate_numbers(numbers):
    if not isinstance(numbers,(list,tuple)) or len(numbers)!=6 or any(type(n) is not int for n in numbers):raise ValueError('six_numbers')
    ns=tuple(sorted(numbers))
    if len(set(ns))!=6 or ns[0]<1 or ns[-1]>45:raise ValueError('range_numbers')
    return ns

def sequence(start=1):
    current=list(unrank(start))
    while True:
        yield tuple(current)
        for i in range(5,-1,-1):
            if current[i]<40+i:
                current[i]+=1
                for j in range(i+1,6):current[j]=current[j-1]+1
                break
        else:return

class Database:
    def __init__(self,path):
        self.path=Path(path).expanduser();self.path.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(self.path,timeout=10)
        self.conn.row_factory=sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON');self.conn.execute('PRAGMA journal_mode=WAL');self.conn.execute('PRAGMA busy_timeout=10000')
        self.migrate()
    def __enter__(self):return self
    def __exit__(self,*args):self.conn.close()
    def migrate(self):
        v=self.conn.execute('PRAGMA user_version').fetchone()[0]
        if v>SCHEMA_VERSION:raise ValueError('newer_schema')
        if v==0:
            if self.path.stat().st_size>4096:self.backup(self.path.with_suffix('.before-migration.sqlite'))
            self.conn.executescript('''
            BEGIN;
            CREATE TABLE combinations(id INTEGER PRIMARY KEY,n1 INTEGER NOT NULL,n2 INTEGER NOT NULL,n3 INTEGER NOT NULL,n4 INTEGER NOT NULL,n5 INTEGER NOT NULL,n6 INTEGER NOT NULL,
              CHECK(n1>=1 AND n1<n2 AND n2<n3 AND n3<n4 AND n4<n5 AND n5<n6 AND n6<=45),UNIQUE(n1,n2,n3,n4,n5,n6));
            CREATE TABLE joker_numbers(number TEXT PRIMARY KEY CHECK(length(number)=6 AND number NOT GLOB '*[^0-9]*')) WITHOUT ROWID;
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE sources(id INTEGER PRIMARY KEY,url TEXT NOT NULL,sha256 TEXT NOT NULL,retrieved TEXT NOT NULL,parser TEXT NOT NULL,UNIQUE(url,sha256));
            CREATE TABLE import_runs(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES sources,started TEXT NOT NULL,finished TEXT,counts TEXT);
            CREATE TABLE draws(id INTEGER PRIMARY KEY,game TEXT NOT NULL CHECK(game IN ('lotto','joker','lottoplus')),date TEXT NOT NULL,time TEXT NOT NULL DEFAULT '',identity TEXT NOT NULL DEFAULT '',draw_type TEXT NOT NULL DEFAULT 'unspecified',official_id TEXT,
              combination_id INTEGER REFERENCES combinations,extra INTEGER CHECK(extra BETWEEN 1 AND 45),draw_order TEXT,joker TEXT REFERENCES joker_numbers,
              UNIQUE(game,date,time,identity));
            CREATE TABLE evidence(draw_id INTEGER REFERENCES draws,source_id INTEGER REFERENCES sources,line INTEGER,PRIMARY KEY(draw_id,source_id)) WITHOUT ROWID;
            CREATE TABLE conflicts(id INTEGER PRIMARY KEY,draw_id INTEGER REFERENCES draws,source_id INTEGER REFERENCES sources,record TEXT NOT NULL,created TEXT NOT NULL,resolved INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE changes(id INTEGER PRIMARY KEY,draw_id INTEGER REFERENCES draws,previous TEXT NOT NULL,replacement TEXT NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE rejected(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES sources,line INTEGER,record TEXT NOT NULL,reason TEXT NOT NULL);
            CREATE TABLE series(id INTEGER PRIMARY KEY,created TEXT NOT NULL,game TEXT NOT NULL,method TEXT NOT NULL,requested INTEGER NOT NULL,settings TEXT NOT NULL,status TEXT NOT NULL);
            CREATE TABLE tips(series_id INTEGER REFERENCES series,id INTEGER,combination_id INTEGER REFERENCES combinations,joker TEXT REFERENCES joker_numbers,PRIMARY KEY(series_id,id),UNIQUE(series_id,combination_id),UNIQUE(series_id,joker)) WITHOUT ROWID;
            PRAGMA user_version=1;COMMIT;''')
        if v<2:
            if v==1:
                self.backup(self.path.with_name(self.path.stem+'.before-v2-'+str(time.time_ns())+'.sqlite'))
            self.conn.executescript('''
            BEGIN;
            CREATE TABLE quotes(id INTEGER PRIMARY KEY,draw_id INTEGER NOT NULL REFERENCES draws,
                source_id INTEGER NOT NULL REFERENCES sources,rank TEXT NOT NULL,rule TEXT NOT NULL,
                winners INTEGER CHECK(winners>=0),currency TEXT NOT NULL CHECK(currency IN ('EUR','ATS')),
                amount INTEGER CHECK(amount>=0),kind TEXT NOT NULL CHECK(kind IN ('jackpot','per_winner','unknown')),
                status TEXT NOT NULL,original TEXT NOT NULL,UNIQUE(draw_id,source_id,rank));
            CREATE INDEX quotes_draw ON quotes(draw_id);
            PRAGMA user_version=2;COMMIT;''')
    def backup(self,target,context=None):
        target=Path(target)
        if target.resolve()==self.path.resolve() or target.exists():raise ValueError('backup_target')
        try:
            with sqlite3.connect(target) as dest:
                self.conn.backup(dest,pages=256,progress=(lambda *_:context.check_cancel()) if context else None)
        except Exception:
            target.unlink(missing_ok=True);raise
    def summary(self):
        return dict(combinations=self.conn.execute('SELECT count(*) FROM combinations').fetchone()[0],joker_numbers=self.conn.execute('SELECT count(*) FROM joker_numbers').fetchone()[0],draws=self.conn.execute('SELECT count(*) FROM draws').fetchone()[0],series=self.conn.execute('SELECT count(*) FROM series').fetchone()[0],conflicts=self.conn.execute('SELECT count(*) FROM conflicts WHERE resolved=0').fetchone()[0],complete=bool(self.conn.execute("SELECT value FROM metadata WHERE key='complete'").fetchone()))
    def ensure_combination(self,ns):
        ns=validate_numbers(ns);identifier=rank(ns)
        self.conn.execute('INSERT OR IGNORE INTO combinations VALUES(?,?,?,?,?,?,?)',(identifier,*ns));return identifier
    def build(self,context=None,batch=10000,limit=None):
        def check():
            if context:context.check_cancel()
        # Saved cursor describes a contiguous, fully committed prefix, independent of imported sparse rows.
        row=self.conn.execute("SELECT value FROM metadata WHERE key='lotto_cursor'").fetchone();cursor=int(row[0]) if row else 0
        goal=TOTAL if limit is None else min(TOTAL,limit)
        iterator=sequence(cursor+1) if cursor<TOTAL else iter(())
        if shutil.disk_usage(self.path.parent).free<64*1024*1024:raise OSError('insufficient_disk')
        initial_bytes=self.path.stat().st_size
        started=time.monotonic()
        while cursor<goal:
            check();values=list(islice(iterator,min(batch,goal-cursor)))
            with self.conn:
                self.conn.executemany('INSERT OR IGNORE INTO combinations VALUES(?,?,?,?,?,?,?)',((cursor+i+1,*ns) for i,ns in enumerate(values)))
                cursor+=len(values);self.conn.execute("INSERT OR REPLACE INTO metadata VALUES('lotto_cursor',?)",(str(cursor),))
            if context:context.progress(cursor,TOTAL+1000000)
            if cursor%100000==0:
                size=self.path.stat().st_size+Path(str(self.path)+'-wal').stat().st_size
                bytes_per=max(64,(size-initial_bytes)/max(1,cursor))
                needed=int(bytes_per*(goal-cursor)*1.25+64*1000000)
                if shutil.disk_usage(self.path.parent).free<needed:raise OSError('insufficient_disk')
                self.conn.execute('PRAGMA wal_checkpoint(PASSIVE)')
        if limit is not None:return self.summary()
        row=self.conn.execute("SELECT value FROM metadata WHERE key='joker_cursor'").fetchone();j=int(row[0]) if row else 0
        while j<1000000:
            check();end=min(j+batch,1000000)
            with self.conn:
                self.conn.executemany('INSERT OR IGNORE INTO joker_numbers VALUES(?)',((f'{n:06d}',) for n in range(j,end)))
                j=end;self.conn.execute("INSERT OR REPLACE INTO metadata VALUES('joker_cursor',?)",(str(j),))
            if context:context.progress(TOTAL+j,TOTAL+1000000)
        check();self.verify_full()
        with self.conn:self.conn.execute("INSERT OR REPLACE INTO metadata VALUES('complete',?)",(utc(),))
        self.conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return {'seconds':time.monotonic()-started,'bytes':self.path.stat().st_size,**self.summary()}
    def verify_full(self):
        summary=self.summary()
        if summary['combinations']!=TOTAL or summary['joker_numbers']!=1000000:raise ValueError('incomplete_inventory')
        for identifier,expected in [(1,(1,2,3,4,5,6)),(TOTAL,(40,41,42,43,44,45))]:
            row=self.conn.execute('SELECT n1,n2,n3,n4,n5,n6 FROM combinations WHERE id=?',(identifier,)).fetchone()
            if tuple(row)!=expected:raise ValueError('inventory_bounds')
        if self.conn.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('integrity')
        if self.conn.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('foreign_keys')
        return summary
    def coverage(self):return [dict(r) for r in self.conn.execute("SELECT game,substr(date,1,4) year,count(*) count,min(date) first,max(date) last FROM draws GROUP BY game,year ORDER BY game,year")]
    def draw_rows(self,game='lotto',start='',end='9999-12-31',last=0):
        rows=self.conn.execute('SELECT d.*,c.n1,c.n2,c.n3,c.n4,c.n5,c.n6 FROM draws d LEFT JOIN combinations c ON c.id=d.combination_id WHERE game=? AND date>=? AND date<=? ORDER BY date,time,id',(game,start,end)).fetchall()
        return [dict(r) for r in (rows[-last:] if last else rows)]
    def page(self,game='lotto',offset=0,limit=100):
        return [dict(r) for r in self.conn.execute('SELECT d.*,c.n1,c.n2,c.n3,c.n4,c.n5,c.n6 FROM draws d LEFT JOIN combinations c ON c.id=d.combination_id WHERE game=? ORDER BY date DESC,time DESC,id DESC LIMIT ? OFFSET ?',(game,limit,offset))]
    def correct(self,conflict_id,reason):
        if not reason.strip():raise ValueError('correction_reason')
        row=self.conn.execute('SELECT * FROM conflicts WHERE id=? AND resolved=0',(conflict_id,)).fetchone()
        if not row:raise ValueError('conflict')
        record=json.loads(row['record']);old=dict(self.conn.execute('SELECT * FROM draws WHERE id=?',(row['draw_id'],)).fetchone())
        with self.conn:
            combo=self.ensure_combination(record['numbers']) if record['game']!='joker' else None
            joker=record.get('joker');extra=record.get('extra')
            if joker:self.conn.execute('INSERT OR IGNORE INTO joker_numbers VALUES(?)',(joker,))
            self.conn.execute('UPDATE draws SET combination_id=?,extra=?,joker=?,draw_order=? WHERE id=?',(combo,extra,joker,json.dumps(record.get('order')),old['id']))
            self.conn.execute('INSERT INTO changes(draw_id,previous,replacement,reason,created) VALUES(?,?,?,?,?)',(old['id'],json.dumps(old),json.dumps(record),reason,utc()))
            self.conn.execute('UPDATE conflicts SET resolved=1 WHERE id=?',(conflict_id,))
            from .quotes import store_quotes
            store_quotes(self,old['id'],row['source_id'],record.get('quotes',[]))

import unittest,tempfile,json,random,time
from pathlib import Path
from modules.database import Database,rank,unrank,TOTAL
from modules.importers import import_records,read_source
from modules.generator import generate,series_tips
from modules.statistics import analyze,historic_match,suffix_hits
from modules.jobs import Cancelled
ROOT=Path(__file__).resolve().parents[1]
class Core(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests');self.root=Path(self.temp.name);self.db=Database(self.root/'test.sqlite')
 def tearDown(self):self.db.conn.close();self.temp.cleanup()
 def test_rank(self):
  self.assertEqual(TOTAL,8145060)
  for i in [1,2,TOTAL,*random.Random(42).sample(range(1,TOTAL),100)]:self.assertEqual(rank(unrank(i)),i)
  self.assertEqual(unrank(1),(1,2,3,4,5,6));self.assertEqual(unrank(TOTAL),(40,41,42,43,44,45))
 def test_resume(self):
  self.db.build(limit=100);self.db.build(limit=200);self.assertEqual(self.db.summary()['combinations'],200)
  self.assertEqual(self.db.conn.execute("SELECT value FROM metadata WHERE key='lotto_cursor'").fetchone()[0],'200')
 def test_schema(self):
  self.assertRaises(Exception,self.db.conn.execute,'INSERT INTO combinations VALUES(1,1,1,2,3,4,5)')
  self.assertRaises(Exception,self.db.conn.execute,"INSERT INTO joker_numbers VALUES('1000000')")
 def test_import_and_conflict(self):
  a={'game':'lotto','date':'2000-01-01','numbers':[1,2,3,4,5,6],'extra':7};b=dict(a,date='2000-01-02')
  import_records(self.db,[a,b],[],'source-a','sha-a');import_records(self.db,[a,b],[],'source-a','sha-a');import_records(self.db,[a],[],'source-b','sha-b')
  self.assertEqual(self.db.summary()['draws'],2);self.assertEqual(self.db.conn.execute('SELECT count(*) FROM evidence').fetchone()[0],3)
  conflict=dict(a,numbers=[1,2,3,4,5,8]);import_records(self.db,[conflict],[],'source-b','sha-b')
  self.assertEqual(self.db.summary()['conflicts'],1);self.db.correct(1,'verified official correction');self.assertEqual(self.db.summary()['conflicts'],0)
 def test_statistics(self):
  records=[dict(game='lotto',date='2000-01-01',numbers=[1,2,3,4,5,6],extra=7),dict(game='lotto',date='2000-01-02',numbers=[1,2,7,8,9,10],extra=3)]
  import_records(self.db,records,[],'test','test');rows=self.db.draw_rows();s=analyze(rows)
  self.assertEqual(s['frequency'][0]['count'],2);self.assertEqual(s['frequency'][2]['extra_count'],1);self.assertEqual(s['shape'][1]['previous_overlap'],2)
  self.assertEqual(s['pairs'][0]['numbers'],(1,2));self.assertEqual(s['pairs'][0]['count'],2)
  self.assertEqual(historic_match([[1,2,3,4,5,6]],rows)[0]['counts'][6],1)
 def test_joker(self):
  import_records(self.db,[dict(game='joker',date='2000-01-01',joker='000001')],[],'test','test');r=self.db.draw_rows('joker')[0]
  self.assertEqual(r['joker'],'000001');self.assertEqual(suffix_hits('120001','990001'),4);self.assertEqual(suffix_hits('120001','120002'),0)
  self.assertEqual(analyze([r],'joker')['positions'][0]['0'],1)
 def test_series(self):
  for n in [10,100,10000]:
   r=generate(self.db,n,seed=42);self.assertEqual(len(series_tips(self.db,r['series'],limit=n)),n)
  self.assertRaises(ValueError,generate,self.db,TOTAL+1)
  self.assertRaises(ValueError,generate,self.db,10,rules={'include':[1,2,3,4,5,6,7]},statistics_enabled=True)
  r=generate(self.db,10000,'joker',seed=42);self.assertEqual(len(series_tips(self.db,r['series'],limit=10000)),10000)
 def test_reproducible(self):
  a=generate(self.db,10,seed=123);b=generate(self.db,10,seed=123)
  self.assertEqual([r['combination_id'] for r in series_tips(self.db,a['series'])],[r['combination_id'] for r in series_tips(self.db,b['series'])])
 def test_cancel(self):
  class Stop:
   def check_cancel(self):raise Cancelled()
   def progress(self,*args):raise Cancelled()
  self.assertRaises(Cancelled,self.db.build,Stop());self.assertEqual(self.db.summary()['combinations'],0)
 def test_backup(self):
  self.db.build(limit=100);target=self.root/'backup.sqlite';self.db.backup(target)
  with Database(target) as copy:self.assertEqual(copy.summary()['combinations'],100)
 def test_official_samples(self):
  r,e=read_source(ROOT/'sources/1986-2010-Lotto.csv');self.assertFalse(e);self.assertEqual(r[0]['date'],'1986-09-07');self.assertEqual(r[0]['numbers'],[1,20,22,24,27,40]);self.assertEqual(r[0]['extra'],12);self.assertNotIn('order',r[0])
  r,e=read_source(ROOT/'sources/NN_W2D_STAT_Lotto_2026.csv');self.assertFalse(e);self.assertEqual(r[0]['numbers'],[1,4,15,16,22,38]);self.assertEqual(r[0]['extra'],11)
  r,e=read_source(ROOT/'sources/lotto-ziehungen-2010-2017.csv');self.assertFalse(e);self.assertEqual(r[0]['numbers'],[4,30,31,32,34,38]);self.assertEqual(r[0]['extra'],33)
  r,e=read_source(ROOT/'sources/NN_W2D_STAT_Joker_2026.pdf');self.assertFalse(e);self.assertEqual(r[0]['joker'],'051256')
if __name__=='__main__':unittest.main()

class Exports(unittest.TestCase):
 def test_stream_and_cancel(self):
  import gi
  gi.require_version('Gtk','4.0')
  from modules.stream_export import write_stream
  from modules.i18n import Strings
  from modules.jobs import Cancelled
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
   target=Path(folder);tr=Strings('de');rows=[{'number':'=1+1'},{'number':'<script>'}];columns=[('number','numbers')]
   for format_ in ['csv','json','html','txt']:
    p=target/('report.'+format_);self.assertEqual(write_stream(p,iter(rows),columns,format_,tr),2)
    text=p.read_text()
    if format_=='html':self.assertIn('&lt;script&gt;',text);self.assertIn('data:image/png;base64',text)
    if format_=='csv':self.assertIn("'=1+1",text)
    if format_=='json':self.assertEqual(len(json.loads(text)['results']),2)
   class Stop:
    def check_cancel(self):raise Cancelled()
   p=target/'cancel.csv';self.assertRaises(Cancelled,write_stream,p,iter(rows),columns,'csv',tr,Stop());self.assertFalse(p.exists());self.assertFalse(list(target.glob('.cancel*')))

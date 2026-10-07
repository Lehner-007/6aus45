"""Regression tests for prizes, configurable sources, and preserved evidence."""
import unittest,tempfile,json,sqlite3
from pathlib import Path
from unittest.mock import patch
from modules.database import Database,SCHEMA_VERSION
from modules.importers import read_source,import_records,discover_and_update,fetch
from modules.quotes import for_draw
from modules.source_settings import defaults,validate_sources
ROOT=Path(__file__).resolve().parents[1]
class Updates(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests');self.root=Path(self.tmp.name);self.db=Database(self.root/'test.sqlite')
 def tearDown(self):self.db.conn.close();self.tmp.cleanup()
 def test_lotto_quotes_epochs(self):
  records,bad=read_source(ROOT/'sources/1986-2010-Lotto.csv');self.assertFalse(bad)
  q=records[0]['quotes'][0];self.assertEqual((q['currency'],q['amount'],q['winners']),('ATS',654215900,1));self.assertNotIn('order',records[0]);self.assertEqual(len(records[0]['quotes']),5)
  records,bad=read_source(ROOT/'sources/NN_W2D_STAT_Lotto_2026.csv');self.assertFalse(bad)
  self.assertEqual(len(records[0]['quotes']),8);self.assertEqual(records[0]['quotes'][-1]['amount'],150)
  q=records[1]['quotes'][0];self.assertEqual(q['kind'],'jackpot');self.assertEqual(q['winners'],0)
  records,bad=read_source(ROOT/'sources/lotto-ziehungen-2010-2017.csv');self.assertFalse(bad);self.assertEqual(len(records[0]['quotes']),8);self.assertNotIn('order',records[0])
 def test_joker_prize_evidence(self):
  records,bad=read_source(ROOT/'sources/NN_W2D_STAT_Joker_2026.pdf');self.assertFalse(bad)
  self.assertEqual(records[0]['joker'],'051256');self.assertEqual(len(records[0]['quotes']),6);self.assertEqual(records[0]['quotes'][0]['amount'],19619870);self.assertIsNone(records[0]['quotes'][1]['amount'])
  records,bad=read_source(ROOT/'sources/joker-quotes-current.json');self.assertFalse(bad);self.assertEqual(len(records[0]['quotes']),6)
  self.assertTrue(all(q['amount'] is not None for q in records[0]['quotes']))
 def test_idempotent_and_conflicting_evidence(self):
  records,_=read_source(ROOT/'sources/NN_W2D_STAT_Lotto_2026.csv');r=records[0]
  for _ in range(2):import_records(self.db,[r],[],'official','same-sha')
  self.assertEqual(self.db.conn.execute('SELECT count(*) FROM quotes').fetchone()[0],8)
  changed=json.loads(json.dumps(r));changed['quotes'][0]['amount']+=100
  import_records(self.db,[changed],[],'alternate','new-sha');rows=for_draw(self.db,1)
  self.assertTrue(rows[0]['conflicting']);self.assertEqual(self.db.conn.execute('SELECT count(*) FROM quotes').fetchone()[0],16)
  changed['numbers']=[1,2,3,4,5,6];changed['extra']=7
  import_records(self.db,[changed],[],'correction','correction-sha');self.db.correct(1,'verified replacement')
  rows=for_draw(self.db,1);self.assertFalse(rows[0]['conflicting']);self.assertEqual(rows[0]['url'],'correction')
 def test_source_validation(self):
  self.assertEqual(len(validate_sources(defaults())),3)
  for url in ('file:///etc/passwd','https://user:pass@example.com/a','https://127.0.0.1/a','http://example.com/a'):
   sources=defaults();sources[0]['url']=url;self.assertRaises(ValueError,validate_sources,sources)
  self.assertRaises(ValueError,validate_sources,[defaults()[0],defaults()[0]])
 def test_custom_source_and_disabled(self):
  r=dict(game='lotto',date='2020-01-01',numbers=[1,2,3,4,5,6],extra=7)
  calls=[]
  def download(url,path,ctx,hosts):calls.append(url);Path(path).write_text(json.dumps([r]));self.assertIn('example.com',hosts)
  source=dict(name='Custom',url='https://example.com/archive.json',enabled=True,game='lotto',format='json')
  with patch('modules.importers.fetch',download):
   result=discover_and_update(self.db,self.root/'sources',sources=[source]);self.assertFalse(result['errors']);self.assertEqual(result['results'][0]['new'],1)
   discover_and_update(self.db,self.root/'sources',sources=[source]);self.assertEqual(len(list((self.root/'sources').glob('*.json'))),2)
   source['enabled']=False;discover_and_update(self.db,self.root/'sources',sources=[source]);self.assertEqual(len(calls),2)
 def test_redirect_checked_before_request(self):
  class Redirect:
   status_code=302;headers={'Location':'https://127.0.0.1/private'}
   def close(self):pass
  with patch('modules.importers.requests.get',return_value=Redirect()) as get:
   self.assertRaises(ValueError,fetch,'https://example.com/start',self.root/'test',allowed_hosts={'example.com'})
   self.assertEqual(get.call_count,1);self.assertFalse((self.root/'test.part').exists())
 def test_upgrade_backup_preserves_tips(self):
  from modules.generator import generate
  generate(self.db,2,seed=3);self.db.conn.execute('DROP TABLE quotes');self.db.conn.execute('PRAGMA user_version=1');self.db.conn.commit();self.db.conn.close()
  self.db=Database(self.root/'test.sqlite');self.assertEqual(self.db.summary()['series'],1)
  backups=list(self.root.glob('test.before-v2-*.sqlite'));self.assertEqual(len(backups),1)
  with sqlite3.connect(backups[0]) as old:self.assertEqual(old.execute('PRAGMA user_version').fetchone()[0],1);self.assertEqual(old.execute('SELECT count(*) FROM tips').fetchone()[0],2)
  self.assertEqual(self.db.conn.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)

 def test_current_database_transfer(self):
  from modules.archive_database import read_database
  records,_=read_source(ROOT/'sources/NN_W2D_STAT_Lotto_2026.csv');import_records(self.db,records[:1],[],'original','sha')
  rows,bad=read_database(self.db.path);self.assertFalse(bad);self.assertEqual(rows[0]['numbers'],records[0]['numbers']);self.assertEqual(len(rows[0]['quotes']),8)
 def test_archived_database_transfer(self):
  from modules.archive_database import read_database
  path=self.root/'old.sqlite3'
  with sqlite3.connect(path) as old:
   old.executescript("""CREATE TABLE lotto_tipps(id,n1,n2,n3,n4,n5,n6);
CREATE TABLE lotto_ziehungen(id,datum,kennung,tipp_id,zusatzzahl,extras);
CREATE TABLE joker_ziehungen(id,datum,kennung,nummer,extras);
CREATE TABLE gewinnklassen(id,code,regelwerk);
CREATE TABLE lotto_quoten(ziehung_id,klasse_id,gewinner,waehrung,betrag_hundertstel,betrag_art,status,original);
CREATE TABLE joker_quoten(ziehung_id,klasse_id,gewinner,waehrung,betrag_hundertstel,betrag_art,status,original);
INSERT INTO lotto_tipps VALUES(999,1,2,3,4,5,6);
INSERT INTO lotto_ziehungen VALUES(1,'1986-09-07','haupt',999,7,'{}');
INSERT INTO joker_ziehungen VALUES(1,'1988-10-02','haupt','000001','{}');
INSERT INTO gewinnklassen VALUES(1,'6er','5_rang');
INSERT INTO lotto_quoten VALUES(1,1,1,'ATS',12300,'je_gewinn','','{}');""")
  rows,bad=read_database(path);self.assertFalse(bad);self.assertEqual(len(rows),2);self.assertEqual(rows[0]['numbers'],[1,2,3,4,5,6]);self.assertEqual(rows[1]['joker'],'000001');self.assertEqual(rows[0]['identity'],'');self.assertNotIn('order',rows[0]);self.assertEqual(rows[0]['quotes'][0]['currency'],'ATS')
  import_records(self.db,rows,bad,'archive','sha');self.assertEqual(self.db.summary()['draws'],2)
 def test_watermark_and_blue_assets(self):
  import hashlib,base64,re
  from modules.model import PROJECT
  self.assertNotEqual(PROJECT['image'],PROJECT['watermark'])
  watermark=(ROOT/PROJECT['watermark']).read_bytes()
  for code in ('de','en'):
   html=(ROOT/'help'/code/'index.html').read_text();embedded=re.search(r'background:url\(data:image/png;base64,([A-Za-z0-9+/=]+)',html)[1];self.assertEqual(base64.b64decode(embedded),watermark)
  self.assertEqual(len(list((ROOT/'assets/balls').glob('ball-blue-*.svg'))),10)

 def test_link_only_source_inference(self):
  from modules.source_settings import source_from_url
  previous=defaults()[0];self.assertEqual(source_from_url(previous['url'],False,previous),dict(previous,enabled=False))
  self.assertEqual(source_from_url('https://example.com/joker_2026.pdf',True)['format'],'pdf')
  self.assertEqual(source_from_url(defaults()[2]['url'],True)['format'],'json')
  source=source_from_url('https://example.com/results.json',True);self.assertEqual(source['game'],'auto');validate_sources([source])
  self.assertRaises(ValueError,source_from_url,'',True)
  def download(url,path,ctx,hosts):Path(path).write_text(json.dumps([dict(game='joker',date='2020-01-01',joker='000123')]))
  with patch('modules.importers.fetch',download):
   result=discover_and_update(self.db,self.root/'sources',sources=[source]);self.assertFalse(result['errors']);self.assertEqual(result['results'][0]['new'],1)
  self.assertEqual(self.db.draw_rows('joker')[0]['joker'],'000123')

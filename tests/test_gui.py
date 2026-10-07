"""In-process GTK integration; isolated configuration, no user's settings mutated."""
import os,tempfile,unittest,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class GUI(unittest.TestCase):
 def test_gui(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp:
   os.environ.pop('PYTHON_TEMPLATE_DEV',None);os.environ['XDG_CONFIG_HOME']=tmp
   from modules.database import Database
   from modules.importers import import_records
   from modules.generator import generate
   from modules.model import save_settings
   dbpath=Path(tmp)/'gui.sqlite'
   with Database(dbpath) as db:
    import_records(db,[dict(game='lotto',date='2020-01-01',numbers=[1,2,3,4,5,6],extra=7,quotes=[dict(rank='6er',rule='8_rang',winners=1,currency='EUR',amount=12300,kind='per_winner',status='')]),dict(game='joker',date='2020-01-01',joker='000123')],[],'test','test')
    generate(db,3,seed=42)
   save_settings(dict(db_path=str(dbpath)))
   from modules.application import Application,LottoWindow
   from gi.repository import GLib,Gtk
   app=Application();app.register(None);w=LottoWindow(app);w.present()
   for _ in range(30):
    while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
   self.assertEqual(w.tabs.get_n_pages(),6);self.assertGreater(len(w.draws.rows()),0);self.assertEqual(len(w.stats.rows()),45)
   for mode in range(len(w.stat_keys)):
    w.stat_view.set_selected(mode);w.refresh_statistics()
   w.stats_game.set_selected(1)
   for mode in range(len(w.stat_keys)):w.stat_view.set_selected(mode);w.refresh_statistics()
   self.assertEqual(w.stat_keys,['stat_frequency','stat_repeated','stat_endings'])
   w.stat_view.set_selected(w.stat_keys.index('stat_endings'));self.assertIn('stat_endings',w.stat_keys)
   w.stats_game.set_selected(0);self.assertNotIn('stat_endings',w.stat_keys);self.assertEqual(w.stat_view.get_selected(),0);self.assertEqual(len(w.stats.rows()),45)
   w.stat_view.set_selected(w.stat_keys.index('stat_shapes'));self.assertEqual(w.stats.rows()[0]['name'],'01.01.2020')
   widths=[column.get_fixed_width() for column,_ in w.stats.headers]
   w.stat_view.set_selected(w.stat_keys.index('stat_compare'));self.assertEqual(widths,[column.get_fixed_width() for column,_ in w.stats.headers]);self.assertTrue(all(not column.get_resizable() and not column.get_expand() for column,_ in w.stats.headers))
   w.stats_game.set_selected(1);self.assertNotIn('stat_compare',w.stat_keys);self.assertEqual(len(w.stats.rows()),60)
   w.stats_game.set_selected(0);w.stat_view.set_selected(0)
   from modules.menus import descendants,compact_menus
   from gi.repository import Gio
   theme=Gtk.Settings.get_default();original=theme.get_property('gtk-application-prefer-dark-theme')
   def pump():
    for _ in range(30):
     while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
   for dark in (False,True):
    theme.set_property('gtk-application-prefer-dark-theme',dark)
    for code in ('de','en'):
     w.apply_language(code);pump()
     single=Gio.Menu();single.append('Test','win.settings');pop=Gtk.PopoverMenu.new_from_model(single);pop.set_parent(w.menu);compact_menus(w.menu)
     for menu in [x for x in descendants(w.menu) if isinstance(x,Gtk.PopoverMenu)]:
      menu.popup();pump()
      for sep in [x for x in descendants(menu) if isinstance(x,Gtk.Separator)]:
       self.assertTrue(sep.get_mapped());self.assertGreaterEqual(sep.get_height(),1)
      scroll=next(x for x in descendants(menu) if isinstance(x,Gtk.ScrolledWindow));page=scroll.get_child().get_child().get_visible_child();natural=page.measure(Gtk.Orientation.VERTICAL,-1).natural
      self.assertLessEqual(scroll.get_height()-natural,2)
      menu.popdown();pump()
     pop.unparent()
   theme.set_property('gtk-application-prefer-dark-theme',original)
   w.apply_language('en');self.assertEqual(w.tr('draws'),'Draws');w.apply_language('de')
   # New settings keep cancel/save semantics and permit an additional source.
   old_sources=[r.copy() for r in w.opts['draw_sources']]
   dialog=w.show_settings();self.assertEqual(len(dialog.draw_source_rows),3)
   dialog.draw_source_rows[0]['url'].set_text('https://example.com/cancelled.json');w.close_dialog(dialog);self.assertEqual(w.opts['draw_sources'],old_sources)
   dialog=w.show_settings();r=dialog.add_draw_source(dict(name='Test archive',url='https://example.com/test.json',enabled=False,game='joker',format='json'))
   dialog.template_controls['save'].emit('clicked');self.assertEqual(len(w.opts['draw_sources']),4)
   from modules.model import settings
   self.assertEqual(settings()['draw_sources'][-1]['name'],'Test archive')
   dialog=w.show_settings();self.assertEqual(dialog.add_source_button.get_label(),'+')
   for row in dialog.draw_source_rows:
    self.assertIsInstance(row['box'].get_first_child(),Gtk.CheckButton);self.assertEqual(row['remove'].get_label(),'−');self.assertNotIn('name',row);self.assertNotIn('game',row);self.assertNotIn('format',row)
   dialog.add_source_button.emit('clicked');self.assertEqual(len(dialog.draw_source_rows),5)
   dialog.draw_source_rows[-1]['url'].set_text('https://example.com/joker.json')
   dialog.draw_source_rows[-1]['enabled'].set_active(False)
   dialog.draw_source_rows[3]['remove'].emit('clicked');self.assertEqual(len(dialog.draw_source_rows),4)
   dialog.template_controls['save'].emit('clicked');self.assertEqual(w.opts['draw_sources'][-1]['game'],'joker');self.assertFalse(w.opts['draw_sources'][-1]['enabled'])
   # Joker keeps leading zeroes; every number is a blue picture, including zero.
   w.game.set_selected(1);w.refresh_draws();w.draws.selection.set_selected(0);pump()
   pics=[];child=w.ballbox.get_first_child()
   while child:pics.append(child);child=child.get_next_sibling()
   self.assertEqual(len(pics),6);self.assertEqual([p.get_tooltip_text() for p in pics],list('000123'))
   self.assertTrue(all(isinstance(p,Gtk.Picture) for p in pics));self.assertEqual([p.get_file().get_basename() for p in pics],['ball-blue-'+v+'.svg' for v in '000123']);self.assertTrue(all(p.get_paintable().get_intrinsic_width()>0 for p in pics))
   w.game.set_selected(0);w.refresh_draws();w.draws.selection.set_selected(0);self.assertIsNotNone(w.quote_box.get_first_child());w.quote_expander.set_expanded(True);pump()
   # Six main balls and a separate extra-ball column, with a bounded watermark.
   testrow=dict(numbers='1 2 3 4 5 6',extra=7)
   main=Gtk.Box();extra=Gtk.Box();w.populate_balls(main,testrow,include_extra=False);w.populate_extra_ball(extra,testrow)
   def children(box):
    result=[];child=box.get_first_child()
    while child:result.append(child);child=child.get_next_sibling()
    return result
   self.assertEqual(w.draws.headers[1][0].get_fixed_width(),230);self.assertFalse(w.draws.headers[1][0].get_expand());self.assertEqual(w.draws.headers[2][0].get_fixed_width(),110)
   self.assertEqual(len(children(main)),6);self.assertEqual(len(children(extra)),1);self.assertEqual(children(extra)[0].get_file().get_basename(),'ball-green-07.svg')
   watermark=next(p for p in descendants(w) if isinstance(p,Gtk.Picture) and abs(p.get_opacity()-.05)<.01)
   self.assertLessEqual(watermark.get_paintable().get_intrinsic_width(),300);self.assertLessEqual(watermark.get_paintable().get_intrinsic_height(),300)
   # Hide empty columns, restore populated ones, and retain numeric zero.
   self.assertEqual(w.draws.headers[0][0].get_fixed_width(),125);self.assertFalse(w.draws.headers[0][0].get_expand())
   self.assertFalse(w.draws.headers[3][0].get_visible())
   w.game.set_selected(1);w.refresh_draws();self.assertFalse(w.draws.headers[2][0].get_visible())
   w.game.set_selected(0);w.refresh_draws();self.assertTrue(w.draws.headers[2][0].get_visible())
   rows=w.draws.rows();rows[0]['identity']='Test-ID';w.draws.set_rows(rows);self.assertTrue(w.draws.headers[3][0].get_visible())
   w.refresh_draws();self.assertFalse(w.draws.headers[3][0].get_visible())
   from modules.results import ResultList
   sample=ResultList(w,[('value','stat_value'),('empty','stat_details')]);sample.set_rows([dict(id=1,status='ok',value=0,empty='   '),dict(id=2,status='ok',value=1,empty='content')])
   self.assertTrue(sample.headers[0][0].get_visible());self.assertTrue(sample.headers[1][0].get_visible())
   sample.search.set_text('0');sample.refilter();self.assertTrue(sample.headers[0][0].get_visible());self.assertFalse(sample.headers[1][0].get_visible())
   sample.search.set_text('');sample.refilter();self.assertTrue(sample.headers[1][0].get_visible())
   # Tip generation callback switches to results and selects its first pictured tip.
   w.count.set_value(3);w.tip_game.set_selected(1);w.seed.set_text('123');w.make_tips()
   import time
   deadline=time.monotonic()+10
   while w.busy and time.monotonic()<deadline:pump();time.sleep(.01)
   self.assertFalse(w.busy);self.assertEqual(w.tabs.get_current_page(),4);self.assertEqual(len(w.mine.rows()),3);self.assertIsNotNone(w.tipballs.get_first_child());self.assertIsNotNone(w.generation_balls.get_first_child())
   dialog=w.show_about();self.assertEqual(dialog.get_program_name(),'6aus45');w.close_dialog(dialog)
   w.close();app.quit()
if __name__=='__main__':unittest.main()

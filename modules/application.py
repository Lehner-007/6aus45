"""GTK application using the shared dialogs, menus, jobs, exports and window state."""
import json,logging,sqlite3,shutil
from pathlib import Path
from datetime import datetime
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gio,GLib,Gdk,GdkPixbuf
from .gui import MainWindow as BaseWindow,vertical
from .model import ROOT,PROJECT,config_dir,save_settings
from .results import ResultList
from .menus import compact_menus
from .database import Database,TOTAL,SCHEMA_VERSION
from .source_settings import validate_sources,source_from_url
from .quotes import for_draw
from .importers import import_file,read_source,preview,discover_and_update
from .generator import generate,series_tips
from .statistics import analyze,numbers,historic_match
from .file_dialogs import choose

class Application(Gtk.Application):
    def __init__(self):super().__init__(application_id='de.lehner.sechsaus45',flags=Gio.ApplicationFlags.NON_UNIQUE)
    def do_activate(self):
        win=self.get_active_window() or LottoWindow(self);win.present()

class LottoWindow(BaseWindow):
    def __init__(self,app):
        self.initialized=False
        super().__init__(app)
        self.opts.setdefault('db_path',str(ROOT/'data/6aus45.sqlite'))
        self.offset=0;self.current_series=0;self.preview_path=None
        area=self.menu.get_next_sibling();self.layout.remove(area)
        overlay=Gtk.Overlay(vexpand=True);box=vertical();overlay.set_child(box)
        watermark=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT/PROJECT.get('watermark',PROJECT['image'])),300,300,True)
        picture=Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(watermark));picture.set_size_request(300,300);picture.set_halign(Gtk.Align.CENTER);picture.set_valign(Gtk.Align.CENTER);picture.set_opacity(.05);picture.set_can_target(False);overlay.add_overlay(picture)
        self.layout.insert_child_after(overlay,self.menu)
        self.notice=self.label('fair_notice',xalign=0,wrap=True);box.append(self.notice)
        self.tabs=Gtk.Notebook(vexpand=True,scrollable=True);box.append(self.tabs);self.tabs.connect('switch-page',self.tab_changed)
        self.overview=self.label('loading',xalign=0,wrap=True,selectable=True)
        over=vertical();over.append(self.overview);self.add_tab(over,'overview')
        self.draw_box=vertical();self.game=Gtk.DropDown.new_from_strings(['Lotto','Joker']);self.game.connect('notify::selected',self.refresh_draws);self.draw_box.append(self.game)
        self.draws=ResultList(self,[('date','date'),('numbers','numbers'),('extra','extra'),('identity','draw_identity')]);self.draw_box.append(self.draws);self.ballbox=Gtk.Box(spacing=8);self.draw_box.append(self.ballbox);self.draws.selection.connect('selection-changed',lambda *_:self.render_balls(self.draws));self.quote_expander=Gtk.Expander(label=self.tr('quotes_title'),expanded=True);self.quote_box=vertical();self.quote_expander.set_child(self.quote_box);self.draw_box.append(self.quote_expander);self.add_tab(self.draw_box,'draws')
        stats=vertical();self.filters=Gtk.Grid(column_spacing=12,row_spacing=8)
        stats.append(self.filters);self.start=Gtk.Entry(placeholder_text='dd.mm.yyyy');self.end=Gtk.Entry(placeholder_text='dd.mm.yyyy');self.last=Gtk.SpinButton.new_with_range(0,1000000,1)
        self.stats_game=Gtk.DropDown.new_from_strings(['Lotto','Joker'])
        for i,(key,w) in enumerate([('game',self.stats_game),('start_date',self.start),('end_date',self.end),('last_n',self.last)]):self.filters.attach(self.label(key,xalign=0),0,i,1,1);self.filters.attach(w,1,i,1,1)
        self.stats_label=self.label('no_data',xalign=0,wrap=True);stats.append(self.stats_label)
        self.all_stat_keys=['stat_frequency','stat_pairs','stat_triples','stat_shapes','stat_repeated','stat_endings','stat_compare'];self.stat_keys=[k for k in self.all_stat_keys if k!='stat_endings'];self.stat_view=Gtk.DropDown.new_from_strings([self.tr(k) for k in self.stat_keys]);stats.append(self.stat_view)
        self.stats_game.connect('notify::selected',self.statistics_game_changed);self.stat_view.connect('notify::selected',self.statistics_view_changed)
        self.stats=ResultList(self,[('name','stat_item'),('value','stat_value'),('details','stat_details')]);stats.append(self.stats);self.chart=Gtk.DrawingArea(content_width=500,content_height=150);self.chart.set_draw_func(self.draw_chart);stats.append(self.chart);self.add_tab(stats,'statistics')
        gen=vertical();self.gen_grid=Gtk.Grid(column_spacing=12,row_spacing=8);gen.append(self.gen_grid)
        self.tip_game=Gtk.DropDown.new_from_strings(['Lotto','Joker']);self.count=Gtk.SpinButton.new_with_range(1,TOTAL,1);self.count.set_value(10);self.seed=Gtk.Entry();self.rule_text=Gtk.TextView(monospace=True);self.rule_text.get_buffer().set_text('{}')
        for i,(key,w) in enumerate([('game',self.tip_game),('tip_count',self.count),('seed',self.seed)]):self.gen_grid.attach(self.label(key,xalign=0),0,i,1,1);self.gen_grid.attach(w,1,i,1,1)
        self.use_stats=Gtk.CheckButton();self.bindings.append((self.use_stats,'set_label','use_statistics'));gen.append(self.use_stats)
        self.exclude_drawn=Gtk.CheckButton();self.bindings.append((self.exclude_drawn,'set_label','exclude_drawn'));gen.append(self.exclude_drawn)
        self.exclude_used=Gtk.CheckButton();self.bindings.append((self.exclude_used,'set_label','exclude_used'));gen.append(self.exclude_used)
        gen.append(self.label('rules_help',xalign=0,wrap=True));scroll=Gtk.ScrolledWindow(min_content_height=120,vexpand=True);scroll.set_child(self.rule_text);gen.append(scroll);self.generation_balls=Gtk.Box(spacing=8);gen.append(self.generation_balls);self.add_tab(gen,'tip_generation')
        mine=vertical();self.series_select=Gtk.SpinButton.new_with_range(0,100000000,1);self.series_select.connect('value-changed',self.select_series);mine.append(self.label('series_id',xalign=0));mine.append(self.series_select)
        self.mine=ResultList(self,[('id','tip_id'),('numbers','numbers'),('extra','extra')]);mine.append(self.mine);self.tipballs=Gtk.Box(spacing=8);mine.append(self.tipballs);self.mine.selection.connect('selection-changed',lambda *_:self.render_balls(self.mine));self.add_tab(mine,'my_tips')
        sources=vertical();sources.append(self.label('import_help',xalign=0,wrap=True));self.sources=ResultList(self,[('game','game'),('year','year'),('count','draw_count'),('first','start_date'),('last','end_date')]);sources.append(self.sources);self.add_tab(sources,'import')
        for name,callback in [('build',self.build),('refresh',self.refresh),('generate',self.make_tips),('import',self.local_import),('confirm_import',self.confirm_import),('update_draws',self.update_draws),('backup',self.backup),('restore',self.restore),('db_path',self.choose_database),('previous',self.previous),('next',self.next),('match',self.match),('conflicts',self.conflicts)]:
            action=Gio.SimpleAction.new(name,None);action.connect('activate',callback);self.add_action(action)
        app.set_accels_for_action('win.refresh',['F5'])
        self.results=self.draws;self.initialized=True;self.apply_language(self.tr.code);self.refresh()
    def add_tab(self,widget,key):self.tabs.append_page(widget,self.label(key))
    def dbpath(self):return Path(self.opts['db_path']).expanduser()
    def apply_language(self,code):
        super().apply_language(code)
        if not self.initialized:return
        self.make_menu()
        self.update_statistics_options()
        for table in [self.draws,self.stats,self.mine,self.sources]:table.translate()
        self.quote_expander.set_label(self.tr('quotes_title'));self.refresh_draws();self.safe(self.refresh_statistics)
    def make_menu(self):
        top=Gio.Menu()
        for title,groups in [('file',[[('db_build','build'),('database_path','db_path')],[('database_backup','backup'),('database_restore','restore'),('results_export','export_results')],[('settings','settings')],[('quit','quit')]]),('data_menu',[[('import_file','import'),('confirm_import','confirm_import'),('update_draws','update_draws')],[('conflicts','conflicts')]]),('analysis_menu',[[('refresh','refresh'),('generate_tips','generate'),('match_tips','match')],[('previous_page','previous'),('next_page','next')]]),('help',[[('help','help'),('log','log'),('info','tool_info'),('about','about')]])]:
            menu=Gio.Menu()
            for group in groups:
                section=Gio.Menu()
                for key,action in group:section.append(self.tr(key),'win.'+action)
                menu.append_section(None,section)
            top.append_submenu(self.tr(title),menu)
        self.menu.set_menu_model(top);compact_menus(self.menu)
    def update_actions(self):
        super().update_actions()
        if self.initialized:
            for name in ['build','refresh','generate','import','update_draws','backup','restore','db_path','previous','next','match','conflicts']:
                self.lookup_action(name).set_enabled(not self.busy and not self.closing)
            self.lookup_action('confirm_import').set_enabled(not self.busy and self.preview_path is not None)
    def tab_changed(self,_tabs,_page,index):
        if not self.initialized:return
        self.results={0:self.sources,1:self.draws,2:self.stats,3:self.mine,4:self.mine,5:self.sources}.get(index,self.draws);self.offset=0
    def safe(self,fn):
        try:return fn()
        except Exception as e:self.logger.exception('Operation [%s]',type(e).__name__);self.notify('operation_failed',reason=str(e));return None
    def refresh(self,*_):
        def run():
            with Database(self.dbpath()) as db:
                s=db.summary();coverage=db.coverage()
                self.overview.set_label(self.tr('overview_values',lotto=s['combinations'],joker=s['joker_numbers'],draws=s['draws'],series=s['series'],conflicts=s['conflicts'],path=str(self.dbpath()))+'\n\n'+self.tr('history_gap'))
                rows=[]
                for i,r in enumerate(coverage):rows.append(dict(id=i,status='ok',**{**r,'first':self.date(r['first']),'last':self.date(r['last'])}))
                self.sources.set_rows(rows)
                if s['series'] and not self.current_series:self.series_select.set_value(s['series'])
            self.refresh_draws();self.refresh_statistics();self.refresh_mine()
        self.safe(run)
    def date(self,value):return datetime.strptime(value,'%Y-%m-%d').strftime('%d.%m.%Y') if value else ''
    def refresh_draws(self,*_):
        if not self.initialized:return
        def run():
            with Database(self.dbpath()) as db:rows=db.page('lotto' if self.game.get_selected()==0 else 'joker',self.offset)
            self.draws.set_rows([dict(id=r['id'],status='ok',date=self.date(r['date']),numbers=r['joker'] or ' '.join(str(r['n'+str(i)]) for i in range(1,7)),extra=r['extra'] or '',identity=r['official_id'] or '') for r in rows])
            if rows:self.draws.selection.set_selected(0)
            else:self.show_quotes(None)
        self.safe(run)
    def period(self):
        def value(entry):return datetime.strptime(entry.get_text().strip(),'%d.%m.%Y').strftime('%Y-%m-%d') if entry.get_text().strip() else ''
        start=value(self.start);end=value(self.end) or '9999-12-31'
        if start>end:raise ValueError(self.tr('invalid_period'))
        return dict(start=start,end=end,last=self.last.get_value_as_int())
    def update_statistics_options(self):
        index=self.stat_view.get_selected()
        selected=self.stat_keys[index] if index<len(self.stat_keys) else 'stat_frequency'
        self.stat_keys=(['stat_frequency','stat_repeated','stat_endings'] if self.stats_game.get_selected()==1
                        else [key for key in self.all_stat_keys if key!='stat_endings'])
        self._updating_stat_options=True
        try:
            self.stat_view.set_model(Gtk.StringList.new([self.tr(key) for key in self.stat_keys]))
            self.stat_view.set_selected(self.stat_keys.index(selected) if selected in self.stat_keys else 0)
        finally:self._updating_stat_options=False

    def statistics_game_changed(self,*_):
        if not self.initialized:return
        self.update_statistics_options();self.safe(self.refresh_statistics)

    def statistics_view_changed(self,*_):
        if self.initialized and not getattr(self,'_updating_stat_options',False):self.safe(self.refresh_statistics)

    def refresh_statistics(self):
        period=self.period();game='lotto' if self.stats_game.get_selected()==0 else 'joker'
        with Database(self.dbpath()) as db:
            all_rows=db.draw_rows(game);rows=db.draw_rows(game,**period)
        first_index=next((i for i,r in enumerate(all_rows) if rows and r['id']==rows[0]['id']),0);previous=all_rows[first_index-1] if first_index else None;s=analyze(rows,game,previous);self.stats_label.set_label(self.tr('sample_count',count=s['count']))
        out=[];selected=self.stat_view.get_selected()
        if selected>=len(self.stat_keys):return
        view=self.all_stat_keys.index(self.stat_keys[selected]);self.chart_values=[]
        if game=='lotto':
            self.chart_values=[r['count'] for r in s['frequency']]
            if view==0:
                for r in s['frequency']:out.append(dict(id=r['number'],status='ok',name=str(r['number']),value=r['count'],details=self.tr('frequency_details',relative=f"{r['relative']:.3f}",expected=f"{r['expected']:.2f}",extra=r['extra_count'],gap=r['current_gap'] if r['current_gap'] is not None else '—')+'; '+self.tr('gap_details',last=self.date(r['last']),mean=f"{r['mean_gap']:.2f}" if r['mean_gap'] is not None else '—',max=r['max_gap'] or '—')))
            elif view in (1,2):
                if view==2:s=analyze(rows,game,previous,triples=True)
                for i,r in enumerate(s['pairs' if view==1 else 'triples']):out.append(dict(id=i,status='ok',name=' '.join(map(str,r['numbers'])),value=r['count'],details=self.tr('sample_count',count=len(rows))))
            elif view==3:
                for i,r in enumerate(s['shape']):out.append(dict(id=i,status='ok',name=self.date(r['date']),value=r['sum'],details=self.tr('shape_details',even=r['even'],odd=r['odd'],regions='/'.join(map(str,r['regions'])),span=r['span'],gaps='/'.join(map(str,r['gaps'])),neighbors=r['neighbors'],run=r['longest_run'],overlap=r['previous_overlap'] if r['previous_overlap'] is not None else '—')))
            elif view==4:
                for i,r in enumerate(s['repeated']):out.append(dict(id=i,status='ok',name=' '.join(map(str,r['numbers'])),value=len(r['dates']),details=', '.join(self.date(v) for v in r['dates'])))
            elif view==6:
                preceding=all_rows[max(0,first_index-len(rows)):first_index];other=analyze(preceding)
                for r,old in zip(s['frequency'],other['frequency']):out.append(dict(id=r['number'],status='ok',name=str(r['number']),value=r['count']-old['count'],details=self.tr('compare_details',before=old['count'],current=r['count'],difference=r['count']-old['count'])))
                self.stats_label.set_label(self.tr('sample_count',count=len(rows))+' / '+self.tr('sample_count',count=len(preceding)))
            self.latest_stats=s
        elif view==4:
            for i,(number,values) in enumerate(s['repeated'].items()):out.append(dict(id=i,status='ok',name=number,value=len(values),details=', '.join(self.date(v[1]) for v in values)))
        elif view==5:
            for length,counts in s['endings'].items():
                for suffix,count in sorted(counts.items(),key=lambda r:(-r[1],r[0])):out.append(dict(id=f'{length}-{suffix}',status='ok',name=suffix,value=count,details=str(length)))
        else:
            for i,digits in enumerate(s['positions']):
                for digit in '0123456789':out.append(dict(id=f'{i}-{digit}',status='ok',name=self.tr('joker_position',position=i+1,digit=digit),value=digits.get(digit,0),details=''))
            self.chart_values=[r['value'] for r in out]
        self.stats.set_rows(out);self.chart.queue_draw()
    def draw_chart(self,widget,cr,width,height):
        values=getattr(self,'chart_values',[])
        if not values:return
        largest=max(values) or 1;step=width/len(values);cr.set_source_rgb(.25,.55,.28)
        for i,v in enumerate(values):cr.rectangle(i*step+1,height-v/largest*(height-20),max(1,step-2),v/largest*(height-20))
        cr.fill()
    def select_series(self,*_):
        if not self.initialized:return
        self.current_series=self.series_select.get_value_as_int();self.offset=0;self.refresh_mine()
    def refresh_mine(self):
        def run():
            with Database(self.dbpath()) as db:rows=series_tips(db,self.current_series,self.offset)
            self.mine.set_rows([dict(id=r['id'],status='ok',numbers=r['joker'] or ' '.join(str(r['n'+str(i)]) for i in range(1,7)),extra='') for r in rows])
        self.safe(run)
    def previous(self,*_):self.offset=max(0,self.offset-100);self.refresh_draws();self.refresh_mine()
    def next(self,*_):self.offset+=100;self.refresh_draws();self.refresh_mine()
    def task(self,key,fn,done=None):
        path=self.dbpath()
        def work(ctx):
            with Database(path) as db:return fn(db,ctx)
        self.start_job(work,done or (lambda _r:self.refresh()),cancellable=True,title_key=key)
    def build(self,*_):self.task('db_build',lambda db,c:db.build(c))
    def make_tips(self,*_):
        def run():
            buffer=self.rule_text.get_buffer();rules=json.loads(buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False));n=self.count.get_value_as_int();seed=self.seed.get_text() or None;game='lotto' if self.tip_game.get_selected()==0 else 'joker';active=self.use_stats.get_active();exd=self.exclude_drawn.get_active();exu=self.exclude_used.get_active();period=self.period()
            def done(r):
                self.current_series=r['series'];self.offset=0;self.series_select.set_value(r['series']);self.refresh()
                if self.mine.sorted.get_n_items():
                    self.mine.selection.set_selected(0)
                    self.populate_balls(self.generation_balls,self.mine.selection.get_selected_item().data,48)
                self.tabs.set_current_page(4)
            self.task('generate_tips',lambda db,c:generate(db,n,game,seed,rules,active,exd,exu,period,c),done)
        self.safe(run)
    def local_import(self,*_):
        def selected(path):
            def work(db,c):
                records,invalid=read_source(path);return preview(db,records,invalid)
            def done(result):self.preview_path=path;self.notify('import_preview',**result);self.update_actions()
            self.task('import_file',work,done)
        choose(self,'import_file',selected,filters=[('CSV/JSON/PDF/SQLite',['*.csv','*.json','*.pdf','*.sqlite','*.sqlite3','*.db'])])
    def confirm_import(self,*_):
        path=self.preview_path
        if path:self.task('import_file',lambda db,c:import_file(db,path,context=c),lambda _r:self.import_done())
    def import_done(self):self.preview_path=None;self.refresh();self.update_actions()
    def update_draws(self,*_):
        sources=[r.copy() for r in self.opts['draw_sources']]
        def done(result):
            self.refresh()
            if result['errors']:self.notify('source_update_errors',count=len(result['errors']),names=', '.join(r['name'] for r in result['errors']))
        self.task('update_draws',lambda db,c:discover_and_update(db,ROOT/'sources',c,sources=sources),done)
    def choose_database(self,*_):
        def selected(path):
            if path.suffix.lower() not in ('.sqlite','.db'):raise ValueError('database_extension')
            with Database(path):pass
            self.opts['db_path']=str(path);save_settings(self.opts);self.refresh()
        choose(self,'database_path',selected,action=Gtk.FileChooserAction.SAVE,filename='6aus45.sqlite',protected_save=False)
    def backup(self,*_):
        choose(self,'database_backup',lambda path:self.task('database_backup',lambda db,c:db.backup(path,c)),action=Gtk.FileChooserAction.SAVE,filename='6aus45-backup.sqlite')
    def restore(self,*_):
        def selected(path):
            def work(db,c):
                if path.resolve()==db.path.resolve():raise ValueError('same_database')
                with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as source:
                    if source.execute('PRAGMA user_version').fetchone()[0] not in (1,SCHEMA_VERSION) or source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('invalid_backup')
                    if source.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('invalid_backup')
                    for name in ['draws','combinations','joker_numbers','series','metadata']:source.execute(f'SELECT 1 FROM {name} LIMIT 1')
                    db.backup(db.path.with_name('before-restore-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite'))
                    c.check_cancel();source.backup(db.conn,pages=256,progress=lambda *_:c.check_cancel())
                return True
            self.task('database_restore',work)
        choose(self,'database_restore',selected,filters=[('SQLite',['*.sqlite','*.db'])])
    def match(self,*_):
        period=self.safe(self.period)
        if period is None:return
        def work(db,c):
            series=db.conn.execute('SELECT game FROM series WHERE id=?',(self.current_series,)).fetchone()
            if not series:raise ValueError('series')
            game=series[0];tips=[];offset=0
            while True:
                c.check_cancel();rows=series_tips(db,self.current_series,offset,1000)
                if not rows:break
                tips.extend(r['joker'] if game=='joker' else numbers(r) for r in rows);offset+=len(rows)
            return historic_match(tips,db.draw_rows(game,**period),game)
        def done(data):
            self.stats.set_rows([dict(id=i,status='ok',name=' '.join(map(str,r['tip'])) if not isinstance(r['tip'],str) else r['tip'],value=sum(n for h,n in r['counts'].items() if h>0),details=json.dumps(r['counts'])) for i,r in enumerate(data)]);self.tabs.set_current_page(2)
        self.task('match_tips',work,done)
    def conflicts(self,*_):
        with Database(self.dbpath()) as db:rows=[dict(r) for r in db.conn.execute('SELECT * FROM conflicts WHERE resolved=0')]
        if not rows:self.notify('conflicts_report',count=0,details='');return
        win=self.track(Gtk.Window(title=self.tr('conflicts'),transient_for=self,modal=True,default_width=650));box=vertical();win.set_child(box)
        choice=Gtk.DropDown.new_from_strings([f"#{r['id']}: "+r['record'] for r in rows]);box.append(choice);box.append(self.label('correction_reason',xalign=0));reason=Gtk.Entry();box.append(reason)
        def apply(*_):
            text=reason.get_text().strip()
            if not text:return
            identifier=rows[choice.get_selected()]['id'];self.close_dialog(win);self.task('apply_correction',lambda db,c:db.correct(identifier,text))
        box.append(self.button('apply_correction',apply));box.append(self.button('cancel',lambda *_:self.close_dialog(win)));win.present()

    def populate_balls(self,box,row,size=30,include_extra=True):
        while box.get_first_child():box.remove(box.get_first_child())
        text=str(row.get('numbers',''));values=text.split()
        import re
        joker=bool(re.fullmatch(r'[0-9]{6}',text))
        if joker:values=list(text)
        if len(values)!=6:return
        for value in values:
            name=f'ball-blue-{value}.svg' if joker else f'ball-white-{int(value):02d}.svg'
            pic=Gtk.Picture.new_for_filename(str(ROOT/'assets/balls'/name));pic.set_size_request(size,size+4);pic.set_tooltip_text(value);pic.set_alternative_text(value);box.append(pic)
        extra=row.get('extra')
        if include_extra and extra:
            pic=Gtk.Picture.new_for_filename(str(ROOT/'assets/balls'/f'ball-green-{int(extra):02d}.svg'));pic.set_size_request(size,size+4);pic.set_tooltip_text(self.tr('extra')+': '+str(extra));box.append(pic)
        box.set_tooltip_text(text)

    def populate_extra_ball(self,box,row,size=30):
        while box.get_first_child():box.remove(box.get_first_child())
        extra=row.get('extra')
        if not extra:return
        pic=Gtk.Picture.new_for_filename(str(ROOT/'assets/balls'/f'ball-green-{int(extra):02d}.svg'))
        pic.set_size_request(size,size+4);pic.set_alternative_text(str(extra));pic.set_tooltip_text(self.tr('extra')+': '+str(extra));box.append(pic)

    def render_balls(self,table):
        box=self.ballbox if table is self.draws else self.tipballs
        row=table.selection.get_selected_item()
        self.populate_balls(box,row.data if row else {},48)
        if table is self.draws:self.show_quotes(row.data['id'] if row else None)

    def show_quotes(self,draw_id):
        if not hasattr(self,'quote_box'):return
        box=self.quote_box
        while box.get_first_child():box.remove(box.get_first_child())
        with Database(self.dbpath()) as db:quotes=for_draw(db,draw_id) if draw_id is not None else []
        if not quotes:box.append(Gtk.Label(label=self.tr('quotes_missing'),xalign=0,wrap=True));return
        grid=Gtk.Grid(column_spacing=16,row_spacing=6)
        for col,key in enumerate(('quote_rank','quote_winners','quote_amount','quote_type')):grid.attach(Gtk.Label(label=self.tr(key),xalign=0),col,0,1,1)
        for index,q in enumerate(quotes,1):
            amount='—' if q['amount'] is None else f"{q['amount']//100:,}".replace(',','.')+f",{q['amount']%100:02d} "+q['currency']
            status=self.tr('quote_'+q['kind'])+(' · '+self.tr('quote_conflict') if q['conflicting'] else '')
            values=(q['rank'],str(q['winners']) if q['winners'] is not None else '—',amount,status)
            for col,value in enumerate(values):
                label=Gtk.Label(label=value,xalign=0,selectable=True,wrap=True);label.set_tooltip_text(q['url']);grid.attach(label,col,index,1,1)
        scroll=Gtk.ScrolledWindow(max_content_height=210,propagate_natural_height=True);scroll.set_child(grid);box.append(scroll)
        box.append(Gtk.Label(label=self.tr('quotes_evidence')+'\n'+'\n'.join(dict.fromkeys(q['url'] for q in quotes)),xalign=0,wrap=True,selectable=True))

    def show_settings(self,*args):
        window=super().show_settings(*args)
        if hasattr(window,'draw_source_rows'):return window
        container=window.get_child().get_first_child().get_child()
        if isinstance(container,Gtk.Viewport):container=container.get_child()
        group=vertical();group.append(self.label('draw_sources_title',xalign=0));hint=self.label('draw_sources_help',xalign=0,wrap=True);group.append(hint);rows=[]
        def add(source=None):
            box=Gtk.Box(spacing=8);check=Gtk.CheckButton(active=source['enabled'] if source else True);check.set_tooltip_text(self.tr('source_enabled'))
            url=Gtk.Entry(text=source['url'] if source else '',placeholder_text='https://…',hexpand=True,width_chars=20)
            record=dict(box=box,enabled=check,url=url,source=source);rows.append(record)
            def remove(*_):rows.remove(record);group.remove(box)
            minus=Gtk.Button(label='−');minus.set_tooltip_text(self.tr('source_remove'));minus.connect('clicked',remove);record['remove']=minus
            for widget in (check,url,minus):box.append(widget)
            group.insert_child_after(box,rows[-2]['box'] if len(rows)>1 else hint)
            return record
        for source in self.opts['draw_sources']:add(source)
        plus=Gtk.Button(label='+',halign=Gtk.Align.START);plus.set_tooltip_text(self.tr('source_add'));plus.connect('clicked',lambda *_:add());group.append(plus)
        group.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL));container.insert_child_after(group,None)
        def collect():
            values=[source_from_url(r['url'].get_text(),r['enabled'].get_active(),r['source']) for r in rows]
            return dict(draw_sources=validate_sources(values))
        window.collect_project_settings=collect;window.draw_source_rows=rows;window.add_draw_source=add;window.add_source_button=plus
        return window

    def export_results(self,*_):
        from .stream_export import write_stream
        from .export import FORMATS
        win=self.track(Gtk.Window(title=self.tr('results_export'),transient_for=self,modal=True,default_width=460));box=vertical();win.set_child(box)
        fmt=Gtk.DropDown.new_from_strings(['CSV','JSON','HTML','TXT']);scope=Gtk.DropDown.new_from_strings([self.tr('export_all'),self.tr('export_visible')]);box.append(self.label('export_format',xalign=0));box.append(fmt);box.append(self.label('export_scope',xalign=0));box.append(scope)
        table=self.results;game='lotto' if self.game.get_selected()==0 else 'joker';series=self.current_series
        def save(*_):
            format_=['csv','json','html','txt'][fmt.get_selected()];visible=scope.get_selected()==1;snapshot=table.rows(visible=True)
            def selected(path):
                def work(db,c):
                    def rows():
                        if visible or table not in (self.draws,self.mine):yield from snapshot;return
                        offset=0
                        while True:
                            c.check_cancel();part=db.page(game,offset,1000) if table is self.draws else series_tips(db,series,offset,1000)
                            if not part:return
                            for r in part:yield dict(id=r['id'],date=self.date(r['date']) if 'date' in r else '',numbers=r['joker'] or ' '.join(str(r['n'+str(i)]) for i in range(1,7)),extra=r.get('extra') or '',identity=r.get('official_id') or '')
                            offset+=len(part)
                    return write_stream(path,rows(),table.columns,format_,self.tr,c)
                self.close_dialog(win);self.task('results_export',work,lambda _r:self.set_status('results_exported',path=str(path)))
            choose(self,'results_export',selected,parent=win,action=Gtk.FileChooserAction.SAVE,filename='6aus45.'+format_)
        foot=Gtk.Box(spacing=8,halign=Gtk.Align.END);foot.append(self.button('cancel',lambda *_:self.close_dialog(win)));foot.append(self.button('choose_save',save));box.append(foot);win.present()

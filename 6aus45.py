#!/usr/bin/env python3
"""GUI and offline command-line utilities for the 6aus45 database."""
import argparse,json,os
from pathlib import Path
from modules.model import PROJECT,VERSION,ROOT

def main():
    p=argparse.ArgumentParser(description='6aus45 – lokale Lotto/Joker-Verwaltung')
    p.add_argument('--version',action='version',version='6aus45 '+VERSION);p.add_argument('--author',action='store_true')
    p.add_argument('--db',type=Path,default=ROOT/'data/6aus45.sqlite');p.add_argument('--build',action='store_true');p.add_argument('--verify',action='store_true');p.add_argument('--import-file',type=Path);p.add_argument('--update',action='store_true');p.add_argument('--generate',type=int);p.add_argument('--game',choices=['lotto','joker'],default='lotto');p.add_argument('--seed');p.add_argument('--statistics',action='store_true');p.add_argument('--rules',default='{}');p.add_argument('--exclude-drawn',action='store_true');p.add_argument('--exclude-used',action='store_true');p.add_argument('--backup',type=Path);p.add_argument('--coverage',action='store_true')
    args=p.parse_args()
    if args.author:print(', '.join(PROJECT['authors']) or 'Autorenangabe noch nicht hinterlegt');return 0
    if any([args.build,args.verify,args.import_file,args.update,args.generate,args.backup,args.coverage]):
        from modules.database import Database
        from modules.importers import import_file,discover_and_update
        from modules.generator import generate
        class Context:
            def check_cancel(self):pass
            def progress(self,n,total):
                if n%250000==0:print(f'{n}/{total}',flush=True)
        try:
            with Database(args.db) as db:
                if args.build:result=db.build(Context())
                elif args.verify:result=db.verify_full()
                elif args.import_file:result=import_file(db,args.import_file)
                elif args.update:
                    from modules.model import settings
                    result=discover_and_update(db,ROOT/'sources',Context(),sources=settings()['draw_sources'])
                elif args.generate:result=generate(db,args.generate,args.game,args.seed,json.loads(args.rules),args.statistics,args.exclude_drawn,args.exclude_used,context=Context())
                elif args.backup:db.backup(args.backup);result={'backup':str(args.backup)}
                else:result=db.coverage()
            print(json.dumps(result,default=lambda x:bool(x),ensure_ascii=False,indent=2));return 0
        except KeyboardInterrupt:print('Abgebrochen. Bereits gespeicherte Daten bleiben erhalten.');return 130
        except Exception as e:print(f'Fehler: {e}');return 1
    from modules.application import Application
    return Application().run([])
if __name__=='__main__':raise SystemExit(main())

"""Atomic streaming exports so full tip series never need to enter the GUI."""
import csv,json,html,base64,tempfile,os
from pathlib import Path
from datetime import datetime
from .file_dialogs import check_export_target
from .model import ROOT,PROJECT,VERSION

def write_stream(path,rows,columns,format_,tr,context=None):
    path=check_export_target(path)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as stream:
            if format_ in ('csv','txt'):
                stream.write('\ufeff' if format_=='csv' else '')
                writer=csv.writer(stream,delimiter=';' if format_=='csv' else '\t');writer.writerow([tr(k) for _,k in columns])
            elif format_=='json':stream.write('{"program":"6aus45","version":'+json.dumps(VERSION)+',"results":[')
            else:
                encoded=base64.b64encode((ROOT/PROJECT.get('watermark',PROJECT['image'])).read_bytes()).decode()
                stream.write('<!doctype html><html lang="'+tr.code+'"><meta charset="utf-8"><title>6aus45</title><style>body{font-family:system-ui}body::before{content:"";position:fixed;inset:0;opacity:.05;pointer-events:none;background:url(data:image/png;base64,'+encoded+') center/250px no-repeat}table{border-collapse:collapse}td,th{padding:.5em;border:1px solid #bbb}tr:nth-child(even){background:#eee}</style><h1>6aus45</h1><p>'+datetime.now().strftime('%d.%m.%Y %H:%M:%S')+'</p><table><tr>'+''.join('<th>'+html.escape(tr(k))+'</th>' for _,k in columns)+'</tr>')
            count=0
            for row in rows:
                if context and count%1000==0:context.check_cancel()
                if format_=='json':stream.write((',' if count else '')+json.dumps(row,ensure_ascii=False))
                elif format_ in ('csv','txt'):
                    values=[str(row.get(k,'')) for k,_ in columns];writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for v in values])
                else:stream.write('<tr>'+''.join('<td>'+html.escape(str(row.get(k,'')))+'</td>' for k,_ in columns)+'</tr>')
                count+=1
            if format_=='json':stream.write(']}\n')
            elif format_=='html':stream.write('</table></html>')
            stream.flush();os.fsync(stream.fileno())
        if context:context.check_cancel()
        os.replace(name,path);return count
    finally:Path(name).unlink(missing_ok=True)

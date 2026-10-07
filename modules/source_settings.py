"""Editable draw archives, separate from fixed software/language update sources."""
from urllib.parse import urlsplit,urlunsplit
from copy import deepcopy
import ipaddress
DEFAULT_SOURCES=[
 dict(name='win2day · Lotto',url='https://www.win2day.at/lotterie/lotto/lotto-statistik-zahlen-ergebnisse-download',enabled=True,game='lotto',format='html'),
 dict(name='win2day · Joker',url='https://www.win2day.at/lotterie/joker-statistik',enabled=True,game='joker',format='html'),
 dict(name='win2day · Joker-Quoten',url='https://lotterien.win2day.at/jam/drawgame/v1/public/drawResultInfo/joker?limit=5000&offset=0',enabled=True,game='joker',format='json')]
FORMATS=('html','csv','pdf','json')
def validate_sources(value):
    if not isinstance(value,list) or len(value)>100:raise ValueError('invalid_sources')
    result=[];seen=set()
    for source in value:
        if not isinstance(source,dict) or type(source.get('enabled')) is not bool or not isinstance(source.get('name'),str) or not source['name'].strip():raise ValueError('source_name_required')
        u=source.get('url')
        if not isinstance(u,str) or any(c.isspace() or ord(c)<32 for c in u):raise ValueError('source_https_required')
        try:
            parts=urlsplit(u);parts.port
            if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:raise ValueError('source_https_required')
        except ValueError:raise ValueError('source_https_required') from None
        if parts.hostname in ('localhost','localhost.localdomain') or parts.hostname.endswith('.localhost'):raise ValueError('source_public_required')
        try:address=ipaddress.ip_address(parts.hostname)
        except ValueError:address=None
        if address and not address.is_global:raise ValueError('source_public_required')
        u=urlunsplit(parts._replace(fragment=''))
        if u in seen:raise ValueError('duplicate_source')
        if source.get('game') not in ('auto','lotto','joker') or source.get('format') not in FORMATS:raise ValueError('source_format_required')
        seen.add(u);result.append(dict(name=source['name'].strip(),url=u,enabled=source['enabled'],game=source['game'],format=source['format']))
    return result

def defaults():return deepcopy(DEFAULT_SOURCES)


def source_from_url(url,enabled,previous=None):
    """Keep existing adapter metadata; infer new links without technical form fields."""
    url=url.strip()
    if not url:raise ValueError('source_https_required')
    if previous and previous['url']==url:return dict(previous,enabled=enabled)
    try:parts=urlsplit(url)
    except ValueError:raise ValueError('source_https_required') from None
    path=parts.path.lower()
    format_=next((f for f in ('csv','pdf','json') if path.endswith('.'+f)),'html')
    if parts.hostname=='lotterien.win2day.at' and '/drawresultinfo/joker' in path:format_='json'
    game='joker' if 'joker' in path else 'lotto' if 'lotto' in path else 'auto'
    return dict(name=url,url=url,enabled=enabled,game=game,format=format_)

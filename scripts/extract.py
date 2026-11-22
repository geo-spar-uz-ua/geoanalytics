# Витягує з файлів OpenStreetMap (кількох областей) точки, будинки, вулиці, воду й населені пункти.
# Об'єкти, що є в обох файлах (на межі областей), беруться один раз.
import osmium, collections

POI_KEYS=['shop','amenity','tourism','railway','highway','public_transport']
AMEN={'marketplace','hospital','clinic','school','kindergarten','university','college','bank','atm','cafe','fast_food','restaurant','pub','bar','pharmacy','townhall','theatre','cinema','post_office','fuel','bus_station','parking','bicycle_rental'}
TOUR={'hotel','guest_house','hostel','attraction','museum'}
PLACES={'city','town','village','hamlet'}
def poi_cat(t):
    if 'shop' in t: return ('shop',t['shop'])
    a=t.get('amenity')
    if a in AMEN: return ('amenity',a)
    if t.get('tourism') in TOUR: return ('tourism',t['tourism'])
    if t.get('railway') in ('station','halt'): return ('railway',t['railway'])
    if t.get('highway')=='bus_stop': return ('highway','bus_stop')
    return None
def tg(t,keys): return {k:t[k] for k in keys if k in t}
KEEP=['name','name:uk','brand','operator','addr:street','addr:housenumber','addr:city','opening_hours','building','building:levels']

class H(osmium.SimpleHandler):
    def __init__(s):
        super().__init__(); s.pois=[]; s.bld=[]; s.roads=[]; s.water=[]; s.rail=[]; s.places=[]; s.seen=set()
    def node(s,n):
        if not n.location.valid(): return
        t=n.tags; c=poi_cat(t); pl=t.get('place')
        if not c and pl not in PLACES: return
        key=('n',n.id)
        if key in s.seen: return
        s.seen.add(key); lon,lat=n.location.lon,n.location.lat
        if c: s.pois.append(dict(t='node',id=n.id,lon=lon,lat=lat,k=c[0],v=c[1],ts=n.timestamp.isoformat() if n.timestamp else '',**tg(t,KEEP)))
        if pl in PLACES and t.get('name'):
            s.places.append(dict(name=t.get('name:uk') or t['name'],place=pl,lon=lon,lat=lat,pop=t.get('population','')))
    def way(s,w):
        key=('w',w.id)
        if key in s.seen: return
        t=w.tags
        if not ('highway' in t or 'building' in t or 'waterway' in t or t.get('natural')=='water' or t.get('railway')=='rail' or poi_cat(t)): return
        try: pts=[(nd.lon,nd.lat) for nd in w.nodes if nd.location.valid()]
        except Exception: return
        if len(pts)<2: return
        s.seen.add(key)
        cx=sum(p[0] for p in pts)/len(pts); cy=sum(p[1] for p in pts)/len(pts)
        if 'highway' in t and t['highway'] not in ('bus_stop','platform'):
            s.roads.append(dict(id=w.id,h=t['highway'],name=t.get('name',''),foot=t.get('foot',''),access=t.get('access',''),area=t.get('area',''),
                                nodes=[nd.ref for nd in w.nodes],pts=pts))
            if t.get('area')!='yes': return
        if 'building' in t:
            s.bld.append(dict(id=w.id,lon=cx,lat=cy,b=t['building'],lv=t.get('building:levels',''),n=len(pts),pts=[(round(x,6),round(y,6)) for x,y in pts]))
        c=poi_cat(t)
        if c and c!=('highway','bus_stop'):
            s.pois.append(dict(t='way',id=w.id,lon=cx,lat=cy,k=c[0],v=c[1],ts=w.timestamp.isoformat() if w.timestamp else '',**tg(t,KEEP)))
        if t.get('waterway') in ('river','canal') or t.get('natural')=='water':
            s.water.append(dict(kind='line' if 'waterway' in t else 'poly',pts=pts,name=t.get('name','')))
        if t.get('railway')=='rail': s.rail.append(pts)

def extract(files):
    """Читає один чи кілька .osm.pbf і повертає всі шари разом з датами файлів."""
    h=H(); stamps=[]
    for f in files:
        h.apply_file(f,locations=True,idx='flex_mem')
        hdr=osmium.io.Reader(f).header()
        stamps.append(hdr.get('osmosis_replication_timestamp') or hdr.get('timestamp') or '')
    return dict(meta={'osm_timestamp':min([x for x in stamps if x] or [''])},pois=h.pois,bld=h.bld,roads=h.roads,water=h.water,rail=h.rail,places=h.places)

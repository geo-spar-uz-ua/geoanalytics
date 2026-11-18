# Витягує з файлу OpenStreetMap точки, будинки, вулиці й воду для межі карти.
import osmium, json, sys, collections
# Використання: python extract.py <файл області .osm.pbf> <вихідний json> W S E N
PBF=sys.argv[1]; OUT=sys.argv[2]
W,S,E_,N=[float(x) for x in sys.argv[3:7]]  # межі карти міста
def inb(lon,lat): return W<=lon<=E_ and S<=lat<=N
POI_KEYS=['shop','amenity','tourism','railway','highway','public_transport']
AMEN={'marketplace','hospital','clinic','school','kindergarten','university','college','bank','atm','cafe','fast_food','restaurant','pub','bar','pharmacy','townhall','theatre','cinema','post_office','fuel','bus_station','parking','bicycle_rental'}
TOUR={'hotel','guest_house','hostel','attraction','museum'}
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
        super().__init__(); s.pois=[]; s.bld=[]; s.roads=[]; s.water=[]; s.rail=[]; s.addr=[]
    def node(s,n):
        if not n.location.valid(): return
        lon,lat=n.location.lon,n.location.lat
        if not inb(lon,lat): return
        t=n.tags
        c=poi_cat(t)
        if c: s.pois.append(dict(t='node',id=n.id,lon=lon,lat=lat,k=c[0],v=c[1],ts=n.timestamp.isoformat() if n.timestamp else '',**tg(t,KEEP)))
        if 'addr:housenumber' in t and 'addr:street' in t:
            s.addr.append((t['addr:street'],t['addr:housenumber'],lon,lat,'node',n.id))
    def way(s,w):
        t=w.tags
        try: pts=[(nd.lon,nd.lat) for nd in w.nodes if nd.location.valid()]
        except Exception: return
        if len(pts)<2: return
        if not any(inb(x,y) for x,y in pts): return
        cx=sum(p[0] for p in pts)/len(pts); cy=sum(p[1] for p in pts)/len(pts)
        if 'highway' in t and t['highway'] not in ('bus_stop','platform'):
            s.roads.append(dict(id=w.id,h=t['highway'],name=t.get('name',''),foot=t.get('foot',''),access=t.get('access',''),area=t.get('area',''),
                                nodes=[nd.ref for nd in w.nodes],pts=pts)); 
            if t.get('area')!='yes': return
        if 'building' in t:
            s.bld.append(dict(id=w.id,lon=cx,lat=cy,b=t['building'],lv=t.get('building:levels',''),n=len(pts),pts=[(round(x,6),round(y,6)) for x,y in pts]))
            if 'addr:housenumber' in t and 'addr:street' in t:
                s.addr.append((t['addr:street'],t['addr:housenumber'],cx,cy,'way',w.id))
        c=poi_cat(t)
        if c and c!=('highway','bus_stop'):
            s.pois.append(dict(t='way',id=w.id,lon=cx,lat=cy,k=c[0],v=c[1],ts=w.timestamp.isoformat() if w.timestamp else '',**tg(t,KEEP)))
        if t.get('waterway') in ('river','canal') or t.get('natural')=='water':
            s.water.append(dict(kind='line' if 'waterway' in t else 'poly',pts=pts,name=t.get('name','')))
        if t.get('railway')=='rail': s.rail.append(pts)
h=H(); h.apply_file(PBF,locations=True)
hdr=osmium.io.Reader(PBF).header()
meta={'osm_timestamp':hdr.get('osmosis_replication_timestamp') or hdr.get('timestamp') or ''}
json.dump(dict(meta=meta,pois=h.pois,bld=h.bld,roads=h.roads,water=h.water,rail=h.rail,addr=h.addr),open(OUT,'w'),ensure_ascii=False)
print(meta, {k:len(getattr(h,k)) for k in ['pois','bld','roads','water','rail','addr']})

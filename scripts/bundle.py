# Збирає пакет відкритих шарів (тільки OpenStreetMap, без даних компанії) для сторінки карти.
# Використання: python bundle.py <json з extract.py> <вихідний bundle.json> <назва міста> W S E N
import json, math, collections, statistics
import numpy as np, h3
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree
import sys
SRC, OUT, CITY = sys.argv[1], sys.argv[2], sys.argv[3]
BBOX=[float(x) for x in sys.argv[4:8]]
d=json.load(open(SRC))
OX,OY=BBOX[0],BBOX[1]
LAT0=(BBOX[1]+BBOX[3])/2; LON0=(BBOX[0]+BBOX[2])/2; KX=111320*math.cos(math.radians(LAT0)); KY=110540
def xy(lon,lat): return ((lon-LON0)*KX,(lat-LAT0)*KY)
def q(lon,lat): return [round((lon-OX)*1e5), round((lat-OY)*1e5)]

# ---- walking graph (largest component), coords quantized to 1e-5 deg
BAD={'motorway','motorway_link','construction','proposed','raceway','bus_guideway','corridor','elevator'}
coord={}; adj=collections.defaultdict(set)
for r in d['roads']:
    if r['h'] in BAD or r['foot']=='no' or r['access'] in ('private','no'): continue
    ns,pts=r['nodes'],r['pts']
    if len(ns)!=len(pts): continue
    for i,(n,p) in enumerate(zip(ns,pts)):
        coord[n]=p
        if i and ns[i-1]!=n: adj[n].add(ns[i-1]); adj[ns[i-1]].add(n)
seen={}; comp=0
for n in coord:
    if n in seen: continue
    st=[n]; seen[n]=comp
    while st:
        u=st.pop()
        for v in adj[u]:
            if v not in seen: seen[v]=comp; st.append(v)
    comp+=1
big=collections.Counter(seen.values()).most_common(1)[0][0]
keep=[n for n in coord if seen[n]==big]
# contract degree-2 nodes into polyline-free edges with exact length
deg={n:len(adj[n]) for n in keep}
def L(a,b):
    ax,ay=xy(*coord[a]); bx,by=xy(*coord[b]); return math.hypot(ax-bx,ay-by)
junction=set(n for n in keep if deg[n]!=2)
idx={}; nodes=[]
def nid(n):
    if n not in idx: idx[n]=len(nodes)//2; nodes.extend(q(*coord[n]))
    return idx[n]
edges=[]; done=set()
for s in junction:
    for nb in adj[s]:
        if (s,nb) in done: continue
        length=L(s,nb); prev,cur=s,nb; done.add((s,nb))
        while cur not in junction:
            nxt=[x for x in adj[cur] if x!=prev][0]
            length+=L(cur,nxt); prev,cur=cur,nxt
        done.add((cur,prev))
        if s!=cur or length>0: edges.extend([nid(s),nid(cur),round(length)])
# isolated loops without junctions are dropped (tiny)
print('graph: nodes',len(nodes)//2,'edges',len(edges)//3)
NX=np.array(nodes[0::2],float); NY=np.array(nodes[1::2],float)
NXm=(NX/1e5+OX-LON0)*KX; NYm=(NY/1e5+OY-LAT0)*KY
def snap(lon,lat):
    x,y=xy(lon,lat); dd=(NXm-x)**2+(NYm-y)**2; i=int(dd.argmin()); return i, round(float(dd[i])**.5)

# ---- buildings, footprints, demand weight
APT={'apartments','residential','dormitory'}; HOUSE={'house','detached','semidetached_house','terrace','bungalow'}
bpoly=[]; bmeta=[]
for b in d['bld']:
    kind='apt' if b['b'] in APT else 'house' if b['b'] in HOUSE else 'yes' if b['b']=='yes' else 'oth'
    b['kind']=kind
    if len(b['pts'])>=4:
        try:
            pg=Polygon([xy(*p) for p in b['pts']])
            if pg.is_valid and pg.area>4: bpoly.append(pg); bmeta.append(b)
        except Exception: pass
_lv=[float(b['lv']) for b in d['bld'] if b['b'] in APT and b['lv'].replace('.','',1).isdigit()]
medapt=statistics.median(_lv) if _lv else 5.0  # без даних про поверхи в місті: 5, як в Ужгороді
def levels(b):
    try: return max(1.0,float(b['lv']))
    except Exception: return medapt if b['kind']=='apt' else 1.0
hexes=collections.defaultdict(lambda:[0,0,0,0,0.0])
for b in d['bld']:
    h=hexes[h3.latlng_to_cell(b['lat'],b['lon'],10)]; h[0]+=1
    if b['kind']=='apt': h[1]+=1
    elif b['kind']=='house': h[2]+=1
    elif b['kind']=='yes': h[3]+=1
for pg,b in zip(bpoly,bmeta):
    if b['kind'] in ('apt','house','yes') and pg.area>=30:
        hexes[h3.latlng_to_cell(b['lat'],b['lon'],10)][4]+=pg.area*levels(b)
hexout=[]
for c,(n,a,ho,ye,r) in hexes.items():
    lat,lon=h3.cell_to_latlng(c); i,off=snap(lon,lat)
    hexout.append([ [v for la,lo in h3.cell_to_boundary(c) for v in q(lo,la)], n,a,ho,ye,round(r), i, off ])

# ---- footprint lookup for area estimates
tree=STRtree(bpoly); byid={b['id']:k for k,b in enumerate(bmeta)}
def footprint(lon,lat,wid=None):
    if wid in byid: return bpoly[byid[wid]].area
    x,y=xy(lon,lat); pt=Point(x,y); best=None
    for k in tree.query(pt.buffer(15)):
        g=bpoly[int(k)]; dd=g.distance(pt)
        if dd<=15 and (best is None or dd<best[0]): best=(dd,g.area)
    return best[1] if best else None
# K: медіанне відношення торгової площі до контуру будівлі у власних магазинах мережі,
# пораховано 18.11.2026 (самі площі й адреси магазинів у цьому репозиторії не зберігаються).
K=0.369
CAP={'supermarket':2500,'convenience':300}

# ---- POIs
FOODSPEC={'greengrocer','butcher','bakery','alcohol','beverages','deli','pastry','confectionery','seafood','dairy','frozen_food','farm','kiosk'}
NONFOOD={'department_store','chemist','variety_store','doityourself','hardware','houseware','clothes','shoes','electronics','furniture','cosmetics'}
MAGNET={'marketplace','hospital','clinic','university','college','school','kindergarten','townhall','theatre','cinema','bus_station'}
SERVICE={'bank','atm','cafe','fast_food','restaurant','pub','bar','pharmacy','post_office','fuel'}
def cat(p):
    k,v=p['k'],p['v']
    if k=='shop':
        if v in CAP: return 'grocery'
        if v in FOODSPEC: return 'foodspec'
        if v=='mall': return 'magnet'
        if v in NONFOOD: return 'nonfood'
        return None
    if k=='amenity':
        return 'magnet' if v in MAGNET else 'service' if v in SERVICE else 'parking' if v=='parking' else None
    if k in ('tourism','railway'): return 'magnet'
    if k=='highway': return 'stop'
pois=[]; est=[]
for p in d['pois']:
    c=cat(p)
    if not c: continue
    i,off=snap(p['lon'],p['lat'])
    rec=dict(c=c,v=p['v'],n=p.get('name') or '',b=p.get('brand') or '',p=q(p['lon'],p['lat']),id=p['t']+'/'+str(p['id']),ts=p.get('ts','')[:10],g=i,o=off)
    if c=='grocery':
        fp=footprint(p['lon'],p['lat'],p['id'] if p['t']=='way' else None)
        rec['ea']=round(min(fp*K,CAP[p['v']])) if fp else None
    pois.append(rec)
def _med(v):
    xs=[r['ea'] for r in pois if r['c']=='grocery' and r['v']==v and r['ea']]
    return statistics.median(xs) if xs else {'supermarket':385,'convenience':101}[v]  # без даних у місті: медіани Ужгорода
med={v:_med(v) for v in CAP}
for r in pois:
    if r['c']=='grocery':
        if r['ea']: r['es']='контур будівлі × K'
        else: r['ea']=round(med[r['v']]); r['es']='медіана типу, будівлі в OSM немає'
print(collections.Counter(r['c'] for r in pois), 'grocery', sum(r['c']=='grocery' for r in pois))

# ---- basemap
MAJOR={'trunk','primary','secondary','tertiary','trunk_link','primary_link','secondary_link','tertiary_link'}
MINOR={'residential','unclassified','living_street','road'}
roads={'a':[],'b':[],'c':[],'p':[]}
for r in d['roads']:
    h=r['h']; k='a' if h in MAJOR else 'b' if h in MINOR else 'p' if h=='pedestrian' else 'c' if h in ('service','footway','path','steps','cycleway','track') else None
    if not k or r['area']=='yes': continue
    ln=LineString([xy(*p) for p in r['pts']]).simplify(3)
    roads[k].append([v for x,y in ln.coords for v in q(x/KX+LON0,y/KY+LAT0)])
water=[]
for w in d['water']:
    if len(w['pts'])<2: continue
    ln=LineString([xy(*p) for p in w['pts']]).simplify(4)
    water.append([w['kind'][0],[v for x,y in ln.coords for v in q(x/KX+LON0,y/KY+LAT0)]])
rail=[[v for p in r for v in q(*p)] for r in d['rail']]
labels=[]; seenl=set()
for r in d['roads']:
    if r['h'] in MAJOR and r['name'] and r['name'] not in seenl and len(r['pts'])>=4:
        seenl.add(r['name']); m=r['pts'][len(r['pts'])//2]; labels.append([r['name']]+q(*m))
B=dict(meta=dict(city=CITY,kxq=round(KX/1e5,5),kyq=round(KY/1e5,5),osm=d['meta']['osm_timestamp'],src=sys.argv[8] if len(sys.argv)>8 else '',
                 license='ODbL 1.0',built=__import__('datetime').date.today().isoformat(),origin=[OX,OY],bbox=BBOX,K=round(K,3),medapt=medapt,cap=CAP,nb=len(d['bld'])),
       g=dict(n=nodes,e=edges), hex=hexout, pois=pois, roads=roads, water=water, rail=rail, labels=labels)
s=json.dumps(B,ensure_ascii=False,separators=(',',':'))
open(OUT,'w').write(s)
print('bundle KB',len(s.encode())//1024, {k:len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode())//1024 for k,v in B.items()})

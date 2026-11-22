# Будує шари карти для обох областей цілком: оглядовий шар region.json і квадрати з деталями.
# Використання: python scripts/build_all.py <pbf Закарпатської> <pbf Івано-Франківської>
# Квадрат: 0,10° довготи × 0,075° широти (≈7,4 × 8,3 км) плюс запас 0,04° / 0,03° (≈3 км) з кожного боку,
# щоб зони пішки й модель Хаффа біля краю квадрата рахувались повністю.
import json, math, os, sys, shutil, collections, datetime
import h3
from shapely.geometry import LineString
sys.path.insert(0,os.path.dirname(__file__))
from extract import extract
from bundle import make_bundle

SRC=['https://download.openstreetmap.fr/extracts/europe/ukraine/zakarpattia_oblast-latest.osm.pbf',
     'https://download.openstreetmap.fr/extracts/europe/ukraine/ivano-frankivsk_oblast-latest.osm.pbf']
OX,OY=22.0,47.6           # спільна точка відліку координат (південний захід обох областей)
TW,TH=0.10,0.075          # розмір квадрата, градусів
BX,BY=0.04,0.03           # запас навколо квадрата, градусів
OUT='docs/data'

def q(lon,lat): return [round((lon-OX)*1e5), round((lat-OY)*1e5)]
def rng(lo,hi,o,t,b): return range(math.floor((lo-o-b)/t), math.floor((hi-o+b)/t)+1)
def tiles_of(pts):
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return [(i,j) for i in rng(min(xs),max(xs),OX,TW,BX) for j in rng(min(ys),max(ys),OY,TH,BY)]
def core_of(lon,lat): return (math.floor((lon-OX)/TW), math.floor((lat-OY)/TH))

d=extract(sys.argv[1:3])
print('extract', {k:len(v) for k,v in d.items() if isinstance(v,list)}, d['meta'], flush=True)

# ---- розкладання по квадратах (з запасом)
bk=collections.defaultdict(lambda:collections.defaultdict(list))
for r in d['roads']:
    for t in tiles_of(r['pts']): bk[t]['roads'].append(r)
for b in d['bld']:
    for t in tiles_of([(b['lon'],b['lat'])]): bk[t]['bld'].append(b)
for p in d['pois']:
    for t in tiles_of([(p['lon'],p['lat'])]): bk[t]['pois'].append(p)
for w in d['water']:
    for t in tiles_of(w['pts']): bk[t]['water'].append(w)
for r in d['rail']:
    for t in tiles_of(r): bk[t]['rail'].append(r)
# квадрати, у ядрі яких є хоч один будинок або продуктовий магазин
want=set(core_of(b['lon'],b['lat']) for b in d['bld'])|set(core_of(p['lon'],p['lat']) for p in d['pois'] if p['k']=='shop')
print('tiles wanted',len(want),flush=True)

if os.path.isdir(OUT+'/t'): shutil.rmtree(OUT+'/t')
os.makedirs(OUT+'/t',exist_ok=True)
tiles=[]
for n,(i,j) in enumerate(sorted(want)):
    core=[round(OX+i*TW,4),round(OY+j*TH,4),round(OX+(i+1)*TW,4),round(OY+(j+1)*TH,4)]
    bbox=[round(core[0]-BX,4),round(core[1]-BY,4),round(core[2]+BX,4),round(core[3]+BY,4)]
    sub=bk.get((i,j),{})
    dt=dict(meta=d['meta'],roads=sub.get('roads',[]),bld=sub.get('bld',[]),pois=sub.get('pois',[]),water=sub.get('water',[]),rail=sub.get('rail',[]))
    if not dt['roads']: continue
    B=make_bundle(dt,bbox,[OX,OY],'%d_%d'%(i,j),' '.join(SRC),core)
    if B is None: continue
    s=json.dumps(B,ensure_ascii=False,separators=(',',':'))
    open('%s/t/%d_%d.json'%(OUT,i,j),'w').write(s)
    tiles.append([i,j,len(s.encode())//1024])
    if n%25==0: print(n,len(want),(i,j),len(s.encode())//1024,'KB',flush=True)

# ---- оглядовий шар обох областей
LAT0=48.6; KX0=111320*math.cos(math.radians(LAT0)); KY=110540
groc=[q(p['lon'],p['lat'])+[p.get('name') or '',p.get('brand') or '',p['v'],p['t']+'/'+str(p['id'])] for p in d['pois'] if p['k']=='shop' and p['v'] in ('supermarket','convenience')]
places=[[p['name'],p['place']]+q(p['lon'],p['lat'])+[p['pop']] for p in d['places'] if p['place']!='hamlet']
MAJ={'motorway':'a','trunk':'a','primary':'a','secondary':'b'}
roads={'a':[],'b':[]}
for r in d['roads']:
    k=MAJ.get(r['h'])
    if not k: continue
    ln=LineString([((x-OX)*KX0,(y-LAT0)*KY) for x,y in r['pts']]).simplify(25)
    roads[k].append([v for x,y in ln.coords for v in q(x/KX0+OX,y/KY+LAT0)])
APT={'apartments','residential','dormitory'}; HOUSE={'house','detached','semidetached_house','terrace','bungalow'}
dens=collections.defaultdict(lambda:[0,0])
for b in d['bld']:
    c=dens[h3.latlng_to_cell(b['lat'],b['lon'],8)]; c[0]+=1
    if b['b'] in APT or b['b'] in HOUSE or b['b']=='yes':
        p=b['pts']; kx=111320*math.cos(math.radians(b['lat']))
        a=abs(sum((p[k][0]-p[k-1][0])*kx*(p[k][1]+p[k-1][1])*KY/2 for k in range(1,len(p))))
        try: lv=max(1.0,float(b['lv']))
        except Exception: lv=5.0 if b['b'] in APT else 1.0
        if a>=30: c[1]+=a*lv
densout=[]
for cell,(n,r) in dens.items():
    la,lo=h3.cell_to_latlng(cell); densout.append(q(lo,la)+[n,round(r)])
R=dict(meta=dict(origin=[OX,OY],tw=TW,th=TH,bx=BX,by=BY,kxq=round(KX0/1e5,5),kyq=round(KY/1e5,5),osm=d['meta']['osm_timestamp'],src=SRC,license='ODbL 1.0',
                 built=datetime.date.today().isoformat(),hexres=8),
       tiles=tiles,groc=groc,places=places,roads=roads,dens=densout)
s=json.dumps(R,ensure_ascii=False,separators=(',',':'))
open(OUT+'/region.json','w').write(s)
print('region KB',len(s.encode())//1024,'tiles',len(tiles),'tiles MB',sum(t[2] for t in tiles)//1024)

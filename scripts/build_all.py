# Будує пакети шарів для всіх міст зі scripts/cities.json і список міст docs/data/cities.json.
# Використання: python scripts/build_all.py <pbf Закарпатської> <pbf Івано-Франківської>
import json, subprocess, sys, os
PBF={'zak':sys.argv[1],'if':sys.argv[2]}
SRC={'zak':'https://download.openstreetmap.fr/extracts/europe/ukraine/zakarpattia_oblast-latest.osm.pbf',
     'if':'https://download.openstreetmap.fr/extracts/europe/ukraine/ivano-frankivsk_oblast-latest.osm.pbf'}
os.makedirs('docs/data',exist_ok=True)
out=[]
for c in json.load(open('scripts/cities.json')):
    bb=[str(x) for x in c['bbox']]; tmp='city_'+c['slug']+'.json'; dst='docs/data/bundle_'+c['slug']+'.json'
    subprocess.run([sys.executable,'scripts/extract.py',PBF[c['region']],tmp]+bb,check=True)
    subprocess.run([sys.executable,'scripts/bundle.py',tmp,dst,c['name']]+bb+[SRC[c['region']]],check=True)
    m=json.load(open(dst))['meta']
    out.append(dict(slug=c['slug'],name=c['name'],bbox=c['bbox'],file='data/bundle_'+c['slug']+'.json',osm=m['osm'],kb=os.path.getsize(dst)//1024))
    os.remove(tmp)
json.dump(out,open('docs/data/cities.json','w'),ensure_ascii=False)
print(json.dumps(out,ensure_ascii=False,indent=1))

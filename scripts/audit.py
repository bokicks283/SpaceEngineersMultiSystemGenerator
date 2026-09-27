"""Read-only local Steam/SE inventory. No Workshop or save writes."""
import os, re, json, collections, xml.etree.ElementTree as ET
from pathlib import Path
import winreg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports'
ALLOW = dict(zip('3576683005 2644430625 2195637331 3618043241 3695766186 3362332228 3309805284 3684013414 3489648084 3515518898 3486181518'.split(),
                 ['Cauldron System','Teal - Water Mod','Teralis - City Planet','Jormun','Planet Zenitaia','Orlunda (Sideways)','Komorebi','Planet Nivis','Planet Relicta','Moon Sulfate','Planet Acribus']))
DENY = '2873186053 2266665708 2636128625 2296726670 2459246911 3617008256 3617040986 3618093811 3617496051 3561998389 2603627657 2789619117'.split()

def vdf(path):
    tokens = iter(re.findall(r'"((?:\\.|[^"\\])*)"|([{}])', path.read_text(encoding='utf-8-sig')))
    def obj():
        result = {}
        for s,b in tokens:
            if b == '}': return result
            key = s.replace('\\\\','\\')
            s,b = next(tokens)
            result[key] = obj() if b == '{' else s.replace('\\\\','\\')
        return result
    return obj()

def dump(name, data):
    (OUT/name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

def scan(path):
    result = dict(voxels=[], planets=[], proxies=[], errors=[], dependencies=[], metadata=None)
    meta = path/'metadata.mod'
    if meta.exists():
        result['metadata'] = meta.read_text(encoding='utf-8-sig')
        result['dependencies'] = re.findall(r'<(?:WorkshopId|PublishedFileId)>(\d+)</', result['metadata'])
    for file in sorted((path/'Data').rglob('*.sbc')):
        try: tree = ET.parse(file)
        except Exception as e:
            result['errors'].append({'file':str(file),'error':str(e)})
            continue
        for el in tree.getroot().iter():
            idnode = el.find('Id')
            if idnode is None: continue
            subtype = idnode.findtext('SubtypeId') or idnode.get('Subtype') or ''
            kind = idnode.findtext('TypeId') or idnode.get('Type') or ''
            xtype = el.get('{http://www.w3.org/2001/XMLSchema-instance}type','')
            item = {'subtype':subtype,'file':str(file),'type':kind, 'enabled':el.get('Enabled','true')}
            if kind in ('VoxelMaterialDefinition','MyObjectBuilder_VoxelMaterialDefinition') or xtype == 'MyObjectBuilder_Dx11VoxelMaterialDefinition' or el.tag == 'VoxelMaterial':
                result['voxels'].append(item)
            if 'PlanetGenerator' in kind or 'PlanetGeneratorDefinition' in xtype or el.tag == 'PlanetGeneratorDefinition':
                item.update(atmosphere=el.findtext('HasAtmosphere'), gravity=el.findtext('SurfaceGravity'), oxygen=el.findtext('Atmosphere/OxygenDensity'))
                result['planets'].append(item)
            if subtype.startswith('PlanetProxyType_'):
                item['description'] = el.findtext('Description')
                result['proxies'].append(item)
    return result

def main():
    OUT.mkdir(exist_ok=True)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
        steam = Path(winreg.QueryValueEx(k,'SteamPath')[0])
    libs = [Path(x['path']) for x in vdf(steam/'steamapps/libraryfolders.vdf')['libraryfolders'].values() if isinstance(x,dict)]
    se = Path(os.environ['APPDATA'])/'SpaceEngineers'
    titles = dict(ALLOW)
    for log in sorted(se.glob('SpaceEngineers*.log')):
        text = log.read_text(encoding='utf-8-sig',errors='replace')
        titles.update(re.findall(r"Up to date mod: Id = (\d+), title = '(.*)'",text))
    worlds=[]
    for file in (se/'Saves').rglob('Sandbox.sbc'):
        if 'Backup' in file.parts: continue
        tree=ET.parse(file)
        mods=[]
        for el in tree.findall('./Mods/ModItem'):
            item={c.tag:c.text for c in el}
            mods.append(item)
            if item.get('FriendlyName'): titles[item.get('PublishedFileId','0')]=item['FriendlyName']
        worlds.append({'file':str(file),'name':tree.findtext('SessionName'),'mods':mods})
    installed=[]; games=[]
    active={m.get('PublishedFileId') for w in worlds for m in w['mods']}
    manifests={}
    for lib in libs:
        manifest=lib/'steamapps/appmanifest_244850.acf'
        if manifest.exists():
            state=vdf(manifest)['AppState']
            game=lib/'steamapps/common'/state['installdir']
            games.append({'path':str(game),'manifest':state,'definitions':scan(game/'Content')})
        wm=lib/'steamapps/workshop/appworkshop_244850.acf'
        if wm.exists(): manifests[str(wm)]=vdf(wm)
        content=lib/'steamapps/workshop/content/244850'
        if not content.exists(): continue
        for mod in sorted(content.iterdir()):
            if not mod.is_dir(): continue
            data=scan(mod)
            installed.append(dict(id=mod.name,title=titles.get(mod.name),path=str(mod),
                desired_planet=mod.name in ALLOW, denylisted=mod.name in DENY,
                active_in_existing_world=mod.name in active, **data))
    dump('inventory.json',dict(libraries=list(map(str,libs)),games=games,workshop_manifests=manifests,mods=installed,worlds=worlds))
    baseline={d['subtype'] for g in games for d in g['definitions']['voxels']}
    scenarios={}
    for name, ids in [('existing',active),('desired_with_existing_gameplay',(active-set(DENY))|set(ALLOW))]:
        defs=collections.defaultdict(list)
        for g in games:
            for d in g['definitions']['voxels']: defs[d['subtype']].append(dict(mod='vanilla',**d))
        permod=[]
        for m in installed:
            if m['id'] not in ids: continue
            names={d['subtype'] for d in m['voxels']}
            if names: permod.append({'id':m['id'],'title':m['title'],'definitions':len(names),'nonvanilla':sorted(names-baseline)})
            for d in m['voxels']: defs[d['subtype']].append(dict(mod=m['id'],**d))
        scenarios[name]={'vanilla':len(baseline),'effective_unique_subtypes':len(defs),'headroom_to_128':128-len(defs),
            'per_mod':permod,'duplicates':{k:v for k,v in defs.items() if len(v)>1},'definitions':dict(defs)}
    dump('voxel-audit.json',scenarios)
    dump('planet-proxy-inventory.json',[{k:m[k] for k in ['id','title','planets','proxies','denylisted','desired_planet','active_in_existing_world']} for m in installed if m['planets'] or m['proxies']])
    print(json.dumps({'libraries':list(map(str,libs)),'installed':len(installed),'worlds':len(worlds),'voxel_scenarios':{k:{a:v[a] for a in ['vanilla','effective_unique_subtypes','headroom_to_128']} for k,v in scenarios.items()},'denylisted_installed':[m['id'] for m in installed if m['denylisted']]},indent=2))

if __name__=='__main__': main()

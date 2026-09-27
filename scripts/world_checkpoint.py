"""Prepare a disposable world and commit an RSG->RSS checkpoint handoff after game exit."""
import argparse, base64, datetime, json, os, re, shutil, subprocess, xml.etree.ElementTree as ET, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SAVE_ROOT=Path(os.environ['APPDATA'])/'SpaceEngineers'/'Saves'
RSG_KEY='RSG_DisposableBootstrap_v1'
RSS_KEY='RealSolarSystemsSettings_Config_xml'
XSI='http://www.w3.org/2001/XMLSchema-instance'; XSD='http://www.w3.org/2001/XMLSchema'
ET.register_namespace('xsi',XSI);ET.register_namespace('xsd',XSD)

def ensure_closed():
    result=subprocess.check_output(['powershell.exe','-NoProfile','-Command',
        '(Get-Process -Name SpaceEngineers -ErrorAction SilentlyContinue | Measure-Object).Count'],text=True).strip()
    if result!='0': raise RuntimeError('Space Engineers is running; exit the game before save changes.')

def active_mods():
    return json.loads((ROOT/'reports/pack-plan.json').read_text(encoding='utf-8'))['selected_workshop']

def config(world):
    return [world/'Sandbox.sbc',world/'Sandbox_config.sbc']

def checkpoint_variables(tree):
    dictionary=tree.find('./ScriptManagerData/variables/dictionary')
    if dictionary is None: raise RuntimeError('Checkpoint has no ScriptManagerData variable dictionary')
    return dictionary

def put_variable(tree,key,value):
    dictionary=checkpoint_variables(tree)
    matches=[el for el in dictionary.findall('item') if el.findtext('Key')==key]
    if len(matches)>1: raise RuntimeError('Duplicate checkpoint variable: '+key)
    item=matches[0] if matches else ET.SubElement(dictionary,'item')
    if not matches: ET.SubElement(item,'Key').text=key
    node=item.find('Value')
    if node is None: node=ET.SubElement(item,'Value')
    node.set(f'{{{XSI}}}type','xsd:string');node.text=value

def get_variable(tree,key):
    for item in checkpoint_variables(tree).findall('item'):
        if item.findtext('Key')==key:return item.findtext('Value')
    return None

def write_atomic(tree,path):
    # ElementTree cannot see namespace prefixes embedded in xsi:type values.
    # Keep the xsd prefix declared for the game's XML serializer.
    tree.getroot().set('xmlns:xsd',XSD)
    temp=path.with_suffix(path.suffix+'.rsg-tmp')
    tree.write(temp,encoding='utf-8',xml_declaration=True)
    ET.parse(temp)
    raw=temp.read_text(encoding='utf-8')
    if 'xsd:string' in raw and f'xmlns:xsd="{XSD}"' not in raw:
        raise RuntimeError('Checkpoint lost its xsd namespace declaration')
    os.replace(temp,path)

def archive(world,label):
    target=ROOT/'backups'/f'{label}-{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}.zip'
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for file in world.rglob('*'):
            if file.is_file():z.write(file,file.relative_to(world))
    return target

def check_sources():
    selected=active_mods()
    for m in selected:
        if not Path(m['path']).is_dir():raise RuntimeError(f"Missing Workshop directory: {m['id']}")
    for name in ['RandomSectorGenerator','CampaignScienceCompatibility']:
        if not (Path(os.environ['APPDATA'])/'SpaceEngineers'/'Mods'/name).is_dir():
            raise RuntimeError('Install local mod before preparing world: '+name)
    voxel=json.loads((ROOT/'reports/selected-voxel-audit.json').read_text(encoding='utf-8'))
    if voxel['total']>voxel['budget']:raise RuntimeError('Voxel audit exceeds budget')
    return selected

def prepare(source,name):
    ensure_closed();selected=check_sources()
    source=source.resolve();root=SAVE_ROOT.resolve()
    if root not in source.parents or 'Backup' in source.parts:raise RuntimeError('Source must be a direct Space Engineers save')
    if any(not p.is_file() for p in config(source)):raise RuntimeError('Source world is incomplete')
    sector=list(source.glob('SANDBOX_*.sbs'))
    if len(sector)!=1:raise RuntimeError('Expected one sector file')
    objects=ET.parse(sector[0]).findall('.//SectorObjects/*')
    if any('Planet' in (o.get(f'{{{XSI}}}type') or '') for o in objects):raise RuntimeError('Source is not an empty planet-free world')
    dest=source.parent/name
    if dest.exists():raise RuntimeError('Destination already exists: '+str(dest))
    backup=archive(source,'World-before-disposable-clone')
    shutil.copytree(source,dest,ignore=shutil.ignore_patterns('Backup','Storage'))
    # Both config files must agree; the checkpoint owns persisted world variables.
    for file in config(dest):
        tree=ET.parse(file);world=tree.getroot()
        world.find('SessionName').text=name
        mods=world.find('Mods')
        if mods is None:raise RuntimeError('World is missing mod list')
        mods.clear()
        for item in selected:
            node=ET.SubElement(mods,'ModItem')
            if item['title']:node.set('FriendlyName',item['title'])
            ET.SubElement(node,'Name').text=item['id']+'.sbm'
            ET.SubElement(node,'PublishedFileId').text=item['id']
            ET.SubElement(node,'PublishedServiceName').text='Steam'
        for name_local in ['CampaignScienceCompatibility','RandomSectorGenerator']:
            node=ET.SubElement(mods,'ModItem')
            ET.SubElement(node,'Name').text=name_local
        if file.name=='Sandbox.sbc':
            checkpoint_variables(tree).clear()
            put_variable(tree,RSG_KEY,'blocked-proxies')
        write_atomic(tree,file)
    print(json.dumps({'world':str(dest),'source_backup':str(backup),'workshop_mods':len(selected),
                      'armed':False,'reason':'Proxy assets pending'},indent=2))

def state_file(world):
    matches=list((world/'Storage').rglob('RandomSectorGenerator.State.xml'))
    if len(matches)!=1:raise RuntimeError(f'Expected one RSG state file, found {len(matches)}')
    return matches[0]

def arm(world):
    ensure_closed(); world=world.resolve()
    if SAVE_ROOT.resolve() not in world.parents or not world.name.startswith('RSG Disposable'):
        raise RuntimeError('Only a prepared disposable world may be armed')
    if (world/'Storage').exists() and list((world/'Storage').rglob('RandomSectorGenerator.State.xml')):
        raise RuntimeError('This world already has an RSG bootstrap state')
    coverage=json.loads((ROOT/'reports/coverage.json').read_text(encoding='utf-8'))
    missing=[]
    for row in coverage:
        if not row['selected']:continue
        candidates=[p for p in row['proxy_candidates'] if p['mod'] in {m['id'] for m in active_mods()}]
        if len(candidates)!=1:missing.append(row['planet'])
        else:
            candidate=candidates[0]
            textures=re.findall(r'^\s*PlanetTexture_(?:cm|ng|add):\s*(\S+)',candidate.get('description') or '',re.MULTILINE)
            if not textures:missing.append(row['planet']+' (no texture paths)')
            for relative in textures:
                # RSS resolves these paths from the providing mod root.
                source=next((m['path'] for m in active_mods() if m['id']==candidate['mod']))
                texture=Path(source)/Path(relative.replace('\\','/'))
                if not texture.is_file():missing.append(row['planet']+' (missing '+relative+')')
    if missing:raise RuntimeError('Missing or duplicate selected RSS proxies: '+', '.join(missing))
    file=world/'Sandbox.sbc';tree=ET.parse(file)
    if get_variable(tree,RSG_KEY)!='blocked-proxies':raise RuntimeError('World is not in disarmed prepared state')
    selected=[m['id'] for m in active_mods()]
    actual=[e.findtext('PublishedFileId') for e in tree.findall('./Mods/ModItem') if e.find('PublishedFileId') is not None]
    if actual!=selected:raise RuntimeError('World mod list differs from current audited pack')
    sector=list(world.glob('SANDBOX_*.sbs'))
    if len(sector)!=1 or any('Planet' in (e.get(f'{{{XSI}}}type') or '') for e in ET.parse(sector[0]).findall('.//SectorObjects/*')):
        raise RuntimeError('World has existing planets')
    backup=archive(world,'World-before-RSG-arm')
    put_variable(tree,RSG_KEY,'armed');write_atomic(tree,file)
    print(json.dumps({'world':str(world),'backup':str(backup),'armed':True},indent=2))

def commit(world):
    ensure_closed();world=world.resolve()
    if SAVE_ROOT.resolve() not in world.parents or not world.name.startswith('RSG Disposable'):
        raise RuntimeError('World is not a prepared disposable save')
    state=ET.parse(state_file(world)).getroot()
    get=lambda k: state.findtext(k)
    if get('PendingApply')!='true' or get('Applied')=='true' or get('InProgress')=='true' or get('Failed')=='true':
        raise RuntimeError('RSG state is not safely pending')
    payload=get('RssConfigBase64')
    if not payload or len(base64.b64decode(payload,validate=True))<100:raise RuntimeError('Invalid RSS payload')
    if get('GeneratedBlackHole')!='true' or int(get('StellarSystemCount','0'))<3:
        raise RuntimeError('Generated sector lacks required hierarchy')
    ids=[e.text for e in state.findall('./GeneratedEntityIds/long')]
    if not ids or get('StartPlanetEntityId') not in ids:raise RuntimeError('Incomplete generated entity record')
    sectors=list(world.glob('SANDBOX_*.sbs'))
    if len(sectors)!=1:raise RuntimeError('Expected one saved sector file')
    saved_ids={e.text for e in ET.parse(sectors[0]).iter('EntityId')}
    if not set(ids).issubset(saved_ids):raise RuntimeError('Saved sector is missing generated entities')
    checkpoint=world/'Sandbox.sbc';tree=ET.parse(checkpoint)
    if get_variable(tree,RSG_KEY)!='armed':raise RuntimeError('This is not an armed disposable world')
    before=get_variable(tree,RSS_KEY)
    if before==payload:
        print('Handoff already committed: '+str(world));return
    backup=archive(world,'World-before-RSS-handoff')
    put_variable(tree,RSS_KEY,payload)
    write_atomic(tree,checkpoint)
    if get_variable(ET.parse(checkpoint),RSS_KEY)!=payload:raise RuntimeError('RSS handoff readback mismatch')
    print(json.dumps({'world':str(world),'backup':str(backup),'rss_handoff':'committed'},indent=2))

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('source',type=Path);a.add_argument('--name',default='RSG Disposable Audit 2026-09-27')
    b=sub.add_parser('commit');b.add_argument('world',type=Path)
    c=sub.add_parser('arm');c.add_argument('world',type=Path)
    args=p.parse_args()
    if args.command=='prepare':prepare(args.source,args.name)
    elif args.command=='arm':arm(args.world)
    else:commit(args.world)

if __name__=='__main__':main()

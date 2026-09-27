"""Prepare a disposable world and commit an RSG->RSS checkpoint handoff after game exit."""
import argparse, base64, datetime, json, os, re, shutil, subprocess, xml.etree.ElementTree as ET, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SAVE_ROOT=Path(os.environ['APPDATA'])/'SpaceEngineers'/'Saves'
RSG_KEY='RSG_DisposableBootstrap_v1'
RSS_KEY='RealSolarSystemsSettings_Config_xml'
PRE_ACTIVATION_SETTINGS={
    'EnableEconomy':'false',
    'CargoShipsEnabled':'false',
    'EnableEncounters':'false',
    'EnablePlanetaryEncounters':'false',
    'GlobalEncounterCap':'0',
}
XSI='http://www.w3.org/2001/XMLSchema-instance'; XSD='http://www.w3.org/2001/XMLSchema'
ET.register_namespace('xsi',XSI);ET.register_namespace('xsd',XSD)

def ensure_closed():
    result=subprocess.check_output(['powershell.exe','-NoProfile','-Command',
        '(Get-Process -Name SpaceEngineers -ErrorAction SilentlyContinue | Measure-Object).Count'],text=True).strip()
    if result!='0': raise RuntimeError('Space Engineers is running; exit the game before save changes.')

def plan():
    return json.loads((ROOT/'reports/pack-plan.json').read_text(encoding='utf-8'))

def active_mods():
    return plan()['selected_workshop']

def local_mods():
    return plan().get('local', ['RandomSectorGenerator','CampaignScienceCompatibility'])

def config(world):
    return [world/'Sandbox.sbc',world/'Sandbox_config.sbc']


def set_pre_activation_settings(tree):
    settings=tree.getroot().find('Settings')
    if settings is None:raise RuntimeError('World has no session settings')
    for key,value in PRE_ACTIVATION_SETTINGS.items():
        node=settings.find(key)
        if node is None:node=ET.SubElement(settings,key)
        node.text=value


def check_no_economy_history(checkpoint):
    stations=checkpoint.findall('./Factions/Factions/MyObjectBuilder_Faction/Stations/MyObjectBuilder_Station')
    if stations:raise RuntimeError(f'World already has {len(stations)} NPC economy station records')
    for component in checkpoint.findall('./SessionComponents/MyObjectBuilder_SessionComponent'):
        if component.get(f'{{{XSI}}}type')=='MyObjectBuilder_SessionComponentEconomy' and component.findtext('GenerateFactionsOnStart')=='false':
            raise RuntimeError('World has an already-initialized Economy component')


def check_pre_activation(world):
    for file in config(world):
        settings=ET.parse(file).getroot().find('Settings')
        if settings is None:raise RuntimeError('World has no settings: '+str(file))
        for key,value in PRE_ACTIVATION_SETTINGS.items():
            if settings.findtext(key)!=value:
                raise RuntimeError(f'Pre-activation setting {key} must be {value} in {file}')
    checkpoint=ET.parse(world/'Sandbox.sbc').getroot()
    check_no_economy_history(checkpoint)

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

def remove_variable(tree,key):
    dictionary=checkpoint_variables(tree)
    for item in list(dictionary.findall('item')):
        if item.findtext('Key')==key:
            dictionary.remove(item)

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
    for name in local_mods():
        if not (Path(os.environ['APPDATA'])/'SpaceEngineers'/'Mods'/name).is_dir():
            raise RuntimeError('Install local mod before preparing world: '+name)
    voxel=json.loads((ROOT/'reports/selected-voxel-audit.json').read_text(encoding='utf-8'))
    if voxel['total']>voxel['budget']:raise RuntimeError('Voxel audit exceeds budget')
    return selected


def sync(world):
    """Refresh an existing disposable empty world to the current audited pack."""
    ensure_closed();selected=check_sources();world=world.resolve()
    if SAVE_ROOT.resolve() not in world.parents or not world.name.startswith('RSG Disposable'):
        raise RuntimeError('Only a prepared disposable world may be synchronized')
    if any(not p.is_file() for p in config(world)):
        raise RuntimeError('Disposable world is incomplete')
    if (world/'Storage').exists() and list((world/'Storage').rglob('RandomSectorGenerator.State.xml')):
        raise RuntimeError('Disposable world already has RSG state; restore/rebuild it instead of syncing')
    sector=list(world.glob('SANDBOX_*.sbs'))
    if len(sector)!=1:
        raise RuntimeError('Expected one sector file')
    objects=ET.parse(sector[0]).findall('.//SectorObjects/*')
    if any('Planet' in (o.get(f'{{{XSI}}}type') or '') for o in objects):
        raise RuntimeError('Disposable world already contains planet/star entities')
    # A prior Economy initialization cannot be undone by toggling settings.
    check_no_economy_history(ET.parse(world/'Sandbox.sbc').getroot())
    backup=archive(world,'World-before-disposable-sync')
    for file in config(world):
        tree=ET.parse(file);root=tree.getroot()
        mods=root.find('Mods')
        if mods is None:
            raise RuntimeError('World is missing mod list')
        mods.clear()
        for item in selected:
            node=ET.SubElement(mods,'ModItem')
            if item['title']:
                node.set('FriendlyName',item['title'])
            ET.SubElement(node,'Name').text=item['id']+'.sbm'
            ET.SubElement(node,'PublishedFileId').text=item['id']
            ET.SubElement(node,'PublishedServiceName').text='Steam'
        for name_local in local_mods():
            node=ET.SubElement(mods,'ModItem')
            ET.SubElement(node,'Name').text=name_local
        set_pre_activation_settings(tree)
        if file.name=='Sandbox.sbc':
            remove_variable(tree,RSG_KEY)
            remove_variable(tree,RSS_KEY)
            put_variable(tree,RSG_KEY,'blocked-proxies')
        write_atomic(tree,file)
    check_pre_activation(world)
    print(json.dumps({'world':str(world),'backup':str(backup),'workshop_mods':len(selected),
                      'synced':True,'armed':False,'reason':'Awaiting explicit arm'},indent=2))

def prepare(source,name,dest_parent=None,stock=False):
    ensure_closed();selected=check_sources()
    source=source.resolve();root=SAVE_ROOT.resolve()
    if stock:
        inventory=json.loads((ROOT/'reports/inventory.json').read_text(encoding='utf-8'))
        expected=(Path(inventory['games'][0]['path'])/'Content/CustomWorlds/Empty World').resolve()
        if source!=expected:raise RuntimeError('Stock source must be the installed Empty World template')
        if dest_parent is None or root not in dest_parent.resolve().parents:
            raise RuntimeError('Destination must be under the Space Engineers Saves directory')
    elif root not in source.parents or 'Backup' in source.parts:
        raise RuntimeError('Source must be a direct Space Engineers save')
    if any(not p.is_file() for p in config(source)):raise RuntimeError('Source world is incomplete')
    sector=list(source.glob('SANDBOX_*.sbs'))
    if len(sector)!=1:raise RuntimeError('Expected one sector file')
    objects=ET.parse(sector[0]).findall('.//SectorObjects/*')
    if any('Planet' in (o.get(f'{{{XSI}}}type') or '') for o in objects):raise RuntimeError('Source is not an empty planet-free world')
    source_checkpoint=ET.parse(source/'Sandbox.sbc').getroot()
    check_no_economy_history(source_checkpoint)
    dest=(dest_parent or source.parent)/name
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
        for name_local in local_mods():
            node=ET.SubElement(mods,'ModItem')
            ET.SubElement(node,'Name').text=name_local
        set_pre_activation_settings(tree)
        if file.name=='Sandbox.sbc':
            # Preserve unrelated script variables from the RSS template. Only remove
            # stale bootstrap/system payloads that could contaminate the disposable copy.
            remove_variable(tree,RSG_KEY)
            remove_variable(tree,RSS_KEY)
            put_variable(tree,RSG_KEY,'blocked-proxies')
        write_atomic(tree,file)
    check_pre_activation(dest)
    print(json.dumps({'world':str(dest),'source_backup':str(backup),'workshop_mods':len(selected),
                      'armed':False,'reason':'Awaiting explicit arm'},indent=2))

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
    check_pre_activation(world)
    coverage=json.loads((ROOT/'reports/coverage.json').read_text(encoding='utf-8'))
    missing=[]
    for row in coverage:
        if not row['selected']:continue
        enabled={m['id'] for m in active_mods()} | {'local:'+name for name in local_mods()}
        candidates=[p for p in row['proxy_candidates'] if p['mod'] in enabled]
        if len(candidates)!=1:missing.append(row['planet'])
        else:
            candidate=candidates[0]
            textures=re.findall(r'^\s*PlanetTexture_(?:cm|ng|add):\s*(\S+)',candidate.get('description') or '',re.MULTILINE)
            if not textures:missing.append(row['planet']+' (no texture paths)')
            for relative in textures:
                # Validate the exact source that the prepared world will load.
                if candidate['mod'].startswith('local:'):
                    local_name=candidate['mod'].split(':',1)[1]
                    source=Path(os.environ['APPDATA'])/'SpaceEngineers'/'Mods'/local_name
                else:
                    source=Path(next((m['path'] for m in active_mods() if m['id']==candidate['mod'])))
                texture=source/Path(relative.replace('\\','/'))
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
    check_pre_activation(world)
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
    # Permanently disarm generation before the adoption reload. The pending state
    # is still the primary guard, but this prevents an accidental second bootstrap
    # if world-storage state is ever lost or removed.
    put_variable(tree,RSG_KEY,'handoff-committed')
    write_atomic(tree,checkpoint)
    check=ET.parse(checkpoint)
    if get_variable(check,RSS_KEY)!=payload:raise RuntimeError('RSS handoff readback mismatch')
    if get_variable(check,RSG_KEY)!='handoff-committed':raise RuntimeError('RSG disarm readback mismatch')
    print(json.dumps({'world':str(world),'backup':str(backup),'rss_handoff':'committed','armed':False},indent=2))

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('source',type=Path);a.add_argument('--name',default='RSG Disposable Audit 2026-09-27')
    b=sub.add_parser('commit');b.add_argument('world',type=Path)
    c=sub.add_parser('arm');c.add_argument('world',type=Path)
    d=sub.add_parser('sync');d.add_argument('world',type=Path)
    e=sub.add_parser('prepare-stock');e.add_argument('reference_world',type=Path)
    e.add_argument('--name',default='RSG Disposable Clean 2026-09-27')
    args=p.parse_args()
    if args.command=='prepare':prepare(args.source,args.name)
    elif args.command=='arm':arm(args.world)
    elif args.command=='sync':sync(args.world)
    elif args.command=='prepare-stock':
        reference=args.reference_world.resolve()
        if SAVE_ROOT.resolve() not in reference.parents or not reference.name.startswith('RSG Disposable'):
            raise RuntimeError('Reference must be an existing disposable save')
        inventory=json.loads((ROOT/'reports/inventory.json').read_text(encoding='utf-8'))
        template=Path(inventory['games'][0]['path'])/'Content/CustomWorlds/Empty World'
        prepare(template,args.name,dest_parent=reference.parent,stock=True)
    else:commit(args.world)

if __name__=='__main__':main()

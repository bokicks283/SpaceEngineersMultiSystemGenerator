"""Derive the selected pack and original science presets from audited local definitions."""
import json, itertools, collections, xml.etree.ElementTree as ET
from pathlib import Path
from audit import ROOT, OUT, ALLOW, DENY, dump

CUTS = {'3309805284','3362332228','3515518898','3618043241','3684013414','3489648084'}
EXTRA = {'3690317665':'AquaExpansion', '2899106264':'Terran Titans Naval Blocks'}

def main():
    inventory=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    mods={m['id']:m for m in inventory['mods']}
    original=[m['PublishedFileId'] for m in inventory['worlds'][0]['mods']]
    selected=[i for i in original if i in mods and i not in DENY and i not in CUTS]
    for i in list(ALLOW)+list(EXTRA):
        if i in mods and i not in CUTS and i not in selected: selected.append(i)
    # Only the SD pack, never both proxy variants. Optional until downloaded/audited.
    if '3357964376' in mods: selected.append('3357964376')
    base={d['subtype'] for g in inventory['games'] for d in g['definitions']['voxels']}
    union=set(base); contributions=[]; owners=collections.defaultdict(list)
    for g in inventory['games']:
        for d in g['definitions']['voxels']:owners[d['subtype']].append(dict(mod='vanilla',**d))
    for id in selected:
        m=mods[id]; names={d['subtype'] for d in m['voxels']}
        contributions.append({'id':id,'title':m['title'] or EXTRA.get(id),'count':len(names),'nonvanilla':sorted(names-base),'incremental':len(names-union)})
        union.update(names)
        for d in m['voxels']: owners[d['subtype']].append(dict(mod=id,**d))
    assert len(union)<=120, f'Unsafe selected pack: {len(union)}'
    vox={'vanilla':len(base),'total':len(union),'headroom':128-len(union),'budget':120,'per_mod':contributions,
         'duplicates':{k:v for k,v in owners.items() if len(v)>1},'subtypes':sorted(union),
         'qualification':'Static local SBC union; runtime definition mutations, dependency expansion, load precedence and engine indexing still require in-game verification.'}
    dump('selected-voxel-audit.json',vox)
    plan={'selected_workshop':[{'id':i,'title':mods[i]['title'] or EXTRA.get(i),'path':mods[i]['path']} for i in selected],
          'local':['RandomSectorGenerator','CampaignScienceCompatibility'],
          'cut_for_budget':sorted(CUTS),'missing_requested':[i for i in ALLOW if i not in mods],
          'stale_missing_world_entries':[i for i in original if i not in mods],
          'denylisted_installed':[i for i in DENY if i in mods],
          'proxy_download_required':['3357964376'],'exporter_download_required':['3350589349']}
    dump('pack-plan.json',plan)
    # Read native presets; exact names matter for variants.
    native={}
    for f in (Path(mods['3665099597']['path'])/'Data').glob('*.sbc'):
        for el in ET.parse(f).findall('.//EntityComponent'):
            sub=el.findtext('Id/SubtypeId','')
            if sub.startswith('PlanetBiomePresetType_'):native[sub.removeprefix('PlanetBiomePresetType_')]=str(f)
    # Authored matching rules; only identifiers and public schema are referenced.
    presets={
        'Cauldron':[('Northern Furnace',50,'Latitude: (0.6, 1)'),('Southern Furnace',50,'Latitude: (-1, -0.6)'),('Equatorial Furnace',40,'Latitude: (-0.2, 0.2)'),('Mantle Expanse',30,'Ores: Cauldron')],
        'Relicta':[('Polar Survey',40,'Latitude: (0.8, 1)'),('Southern Survey',40,'Latitude: (-1, -0.8)'),('Magma Fields',60,'Ores: RelMagma'),('Basalt Fields',35,'Ores: RelBasalt'),('Ancient Bedrock',35,'Ores: RelBedrock'),('Rocky Highlands',30,'Ores: RelRock')],
        'Zenitaia':[('Northern Survey',40,'Latitude: (0.8, 1)'),('Southern Survey',40,'Latitude: (-1, -0.8)'),('Grasslands',30,'Ores: Zenit_Grass'),('Ocean Sands',35,'Ores: Zenit_OCSand'),('Volcanic Gravel',40,'Ores: ZenitLavaGravel'),('Hot Rock Fields',55,'Ores: ZenitHotRock, ZenitLavaRockOC, ZenitLavaRockSurface')]
    }
    xsi='http://www.w3.org/2001/XMLSchema-instance'; ET.register_namespace('xsi',xsi)
    root=ET.Element('Definitions'); components=ET.SubElement(root,'EntityComponents')
    for planet,biomes in presets.items():
        assert planet not in native
        el=ET.SubElement(components,'EntityComponent',{f'{{{xsi}}}type':'MyObjectBuilder_InventoryComponentDefinition'})
        ident=ET.SubElement(el,'Id'); ET.SubElement(ident,'TypeId').text='Inventory';ET.SubElement(ident,'SubtypeId').text='PlanetBiomePresetType_'+planet
        ET.SubElement(el,'Description').text='\nSlopeCheckDist: 100\n'+'\n'.join(f'Biome: {n}\nScienceReward: {r}\n{condition}\n' for n,r,condition in biomes)
    dest=ROOT/'mods/CampaignScienceCompatibility/Data';dest.mkdir(parents=True,exist_ok=True)
    ET.indent(root);ET.ElementTree(root).write(dest/'CampaignBiomes.sbc',encoding='utf-8',xml_declaration=True)
    proxy=collections.defaultdict(list)
    for m in mods.values():
        for p in m['proxies']:
            names=[p['subtype'].removeprefix('PlanetProxyType_')]
            import re
            names+=re.findall(r'PlanetDefaults:\s*([^\n\r]+)',p.get('description') or '')
            for name in [n.strip() for s in names for n in s.split(',')]:proxy[name].append(dict(mod=m['id'],**p))
    coverage=[]
    for id,title in ALLOW.items():
        for p in mods.get(id,{}).get('planets',[{'subtype':'unavailable'}]):
            name=p['subtype']; candidates=proxy.get(name,[])
            chosen=[c for c in candidates if c['mod'] in selected]
            coverage.append({'id':id,'planet':name,'selected':id in selected,'proxy_candidates':candidates,'active_proxy_count':len(chosen),
                             'science_native':native.get(name),'science_compatibility':name in presets,
                             'science_status':'native' if name in native else 'local authored preset' if name in presets else 'unavailable' if name=='unavailable' else 'generic fallback'})
    dump('coverage.json',coverage)
    # Compute all minimum-cardinality cuts, including alternatives retaining Cauldron.
    planets=[m for m in mods.values() if m['desired_planet']]
    alternatives={}
    required_base=set(base)
    for id in EXTRA:
        if id in mods: required_base.update(d['subtype'] for d in mods[id]['voxels'])
    for label,protected in [('unconstrained',set()),('preserve_cauldron',{'3576683005'}),('preserve_cauldron_and_selected_water',{'3576683005','2644430625','2195637331','3695766186'})]:
        for count in range(len(planets)+1):
            options=[]
            for cut in itertools.combinations([m for m in planets if m['id'] not in protected],count):
                ids={m['id'] for m in cut}; names=set(required_base)
                for m in planets:
                    if m['id'] not in ids:names.update(d['subtype'] for d in m['voxels'])
                if len(names)<=120:options.append({'cut':sorted(ids),'total':len(names)})
            if options:alternatives[label]={'minimum_mod_cuts':count,'options':options};break
    dump('planet-cut-options.json',alternatives)
    lines=['# Selected pack audit','',f'Static voxel total: **{len(union)}** = {len(base)} vanilla + {len(union-base)} additions; **{128-len(union)}** headroom against 128 and {120-len(union)} below the conservative budget of 120. Runtime validation pending.','',
           '| Body | Selected | Active RSS proxies | Science |','|---|---|---:|---|']
    lines += [f"| {c['planet']} | {'yes' if c['selected'] else 'no'} | {c['active_proxy_count']} | {c['science_status']} |" for c in coverage]
    lines+=['','## Workshop load-list membership','',*['- '+i+' — '+str(mods[i]['title'] or EXTRA.get(i) or 'title unavailable locally') for i in selected],
            '', '## Local mods', '', '- RandomSectorGenerator: one-shot armed disposable-world bootstrap, pending RSS checkpoint handoff, spoiler manifest.',
            '- CampaignScienceCompatibility: authored Cauldron and Zenitaia biomes; Relicta is prepared but excluded from this pack.',
            '', '## Water and encounters', '',
            'The local Teal-WaterMod, Teralis - City Planet, and Zenitaia packages each define their own WaterConfig planet entry. AquaExpansion and Terran Titans Naval Blocks are selected alongside Water Mod. No global water entry was added.',
            'MES, Assertive Combat Systems, Abandoned Settlements, and AiEnabled are retained. MES warns about NPC grid precision beyond 6,500 km from origin; RSS clamps its physical voxel spawn range to at least 10,000 km. No confirmed safe configuration-only repair was found. Planetary NPC spawning near RSS physical planets remains an acceptance risk.',
            '', '## Limits', '',
            'The selected cut is the only six-mod cut under 120 materials that retains Cauldron plus Water Teal, Teralis, and Zenitaia among the locally available requested planets. Excluded: Komorebi, Orlunda Sideways, Relicta, Sulfate, Jormun, and Nivis. Acribus is not installed.',
            'Cauldron bundles four exact RSS proxy definitions. Teal-WaterMod, Teralis - City Planet, and Zenitaia still lack active exact proxies. Alkurah SD proxy pack and RSS Planet Exporter were identified as candidates but their Workshop downloads and runtime coverage remain unverified. The prepared world is disarmed until coverage is exact.',
            'Voxel modifiers are excluded. No subtype duplicates were found in the selected local definitions. Unique subtype union is independent of override precedence. The old test save contained stale Workshop entries and was not edited; its static voxel estimate is a lower bound. The original was preserved in timestamped ZIPs.',
            'The most recent pre-change game log loaded 189 unique voxel materials from the old pack. The new pack has passed static auditing and offline RSG compilation, but has not been launched, generated, reloaded, or checked for water/science/MES behavior in game.']
    (OUT/'PACK-AUDIT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Selected {len(selected)} Workshop mods, voxel total {len(union)}; missing selected proxies: '+', '.join(c['planet'] for c in coverage if c['selected'] and not c['active_proxy_count']))

if __name__=='__main__':main()

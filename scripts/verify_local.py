"""Cross-check the audited pack, source contracts, and installed CustomWorld."""
import json, re, xml.etree.ElementTree as ET
from pathlib import Path
from audit import ROOT, OUT
from random_sector_custom_world import validate as validate_custom_world
from world_checkpoint import RSG_KEY, RSS_KEY, get_variable, put_variable, apply_handoff_variables

def main():
    inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    plan=json.loads((OUT/'pack-plan.json').read_text(encoding='utf-8'))
    vox=json.loads((OUT/'selected-voxel-audit.json').read_text(encoding='utf-8'))
    coverage=json.loads((OUT/'coverage.json').read_text(encoding='utf-8'))
    collection=json.loads((OUT/'steam-collection.json').read_text(encoding='utf-8'))
    policy=json.loads((ROOT/'phase-a-pack-policy.json').read_text(encoding='utf-8'))
    ids=[m['id'] for m in plan['selected_workshop']]
    assert plan['collection_id']==policy['collection_id']==collection['collection_id']
    assert len(ids)==len(set(ids))
    assert not set(ids)&set(policy['compatibility_exclusions'])
    assert not set(ids)&{item['id'] for item in plan['phase_a_planet_exclusions']}
    assert {item['id'] for item in collection['items'] if item['active']}<=set(ids)
    allowed={item['id'] for item in collection['items']}
    allowed.update(item['id'] for item in plan['dependency_additions'])
    allowed.update(item['id'] for item in plan['support_additions'])
    assert set(ids)<=allowed, 'Workshop mods leaked from outside collection/dependency/support policy'
    assert {'1359618037','571920453','2609118808','3351055036'}<=set(ids)
    assert not {'570767699','570766507'}&set(ids)
    assert vox['total'] <= vox['budget'] and vox['headroom'] == 128 - vox['total']
    assert vox['headroom'] >= 8
    assert all(c['science_status'] in ('native','local authored preset') for c in coverage if c['selected'])
    source=(ROOT/'mods/RandomSectorGenerator/Data/Scripts/RandomSectorGenerator/RandomSectorGeneratorSession.cs').read_text(encoding='utf-8')
    pool=json.loads((ROOT/'campaign-planets.json').read_text(encoding='utf-8'))
    generated=(ROOT/'mods/RandomSectorGenerator/Data/Scripts/RandomSectorGenerator/CampaignPlanetPool.cs').read_text(encoding='utf-8')
    csharp=set()
    for group,key in [('RequiredCustom','required_custom'),('Vanilla','vanilla'),
                      ('OptionalCustom','optional_custom')]:
        block=re.search(r'\b'+group+r'\s*=\s*new string\[\]\s*\{([^}]+)\}',generated)
        assert block,group
        found=set(re.findall(r'"([^"]+)"',block.group(1)))
        assert found==set(pool[key]),(group,found^set(pool[key]))
        csharp.update(found)
    selected={c['planet'] for c in coverage if c['selected']}
    assert len(selected)==18
    assert all(c['active_proxy_count']==1 for c in coverage if c['selected'])
    assert selected<=csharp,(selected-csharp)
    assert csharp.isdisjoint({c['planet'] for c in coverage if not c['selected']})
    assert 'DefaultBlackHole' in source and 'RSG_DisposableBootstrap_v1' in source
    science=ET.parse(ROOT/'mods/CampaignScienceCompatibility/Data/CampaignBiomes.sbc')
    authored={e.text.removeprefix('PlanetBiomePresetType_') for e in science.findall('.//SubtypeId')}
    assert {'Cauldron','Jormun','Relicta','Zenitaia','Kerbin - Water Mod Ready','Aulden'}<=authored
    assert 'Seren' not in authored
    for el in science.findall('.//EntityComponent'):
        desc=el.findtext('Description','')
        assert 'Biome:' in desc and 'ScienceReward:' in desc
    game_root=Path(inv['games'][0]['path'])
    world=game_root/'Content/CustomWorlds/Random Sector'
    validate_custom_world(world)
    trees=[ET.parse(world/name) for name in ['Sandbox.sbc','Sandbox_config.sbc']]
    for t in trees:
        actual=[e.findtext('PublishedFileId') for e in t.findall('./Mods/ModItem') if e.find('PublishedFileId') is not None]
        assert actual == ids, 'Random Sector CustomWorld mod list is not synced to the selected campaign pack'
    raw=(world/'Sandbox.sbc').read_text(encoding='utf-8')
    assert 'xmlns:xsd="http://www.w3.org/2001/XMLSchema"' in raw and 'xsi:type="xsd:string"' in raw
    assert get_variable(trees[0],RSG_KEY)=='random-sector-template-v1'
    # Regression guard: an already-matching RSS payload must not leave RSG armed.
    probe=ET.ElementTree(ET.fromstring('<MyObjectBuilder_Checkpoint><ScriptManagerData><variables><dictionary /></variables></ScriptManagerData></MyObjectBuilder_Checkpoint>'))
    put_variable(probe,RSS_KEY,'matching-payload');put_variable(probe,RSG_KEY,'armed')
    apply_handoff_variables(probe,'matching-payload')
    assert get_variable(probe,RSS_KEY)=='matching-payload'
    assert get_variable(probe,RSG_KEY)=='handoff-committed'
    # Compare the serialized field tags used in our wire types with the installed RSS types.
    rss=Path(inv['games'][0]['path'])
    upstream=(Path(inv['mods'][next(i for i,m in enumerate(inv['mods']) if m['id']=='3351055036')]['path'])/'Data/Scripts/RealSolarSystems/RealSolarSystemsConfig.cs').read_text(encoding='utf-8')
    wire=(ROOT/'mods/RandomSectorGenerator/Data/Scripts/RandomSectorGenerator/RssWireModels.cs').read_text(encoding='utf-8')
    for field,tag in [('OverrideFromConfig',1),('VoxelPlanetSpawnRangeMin',4),('VoxelPlanetSpawnRangeMax',5),('SolarSystems',6)]:
        assert re.search(rf'\[ProtoMember\({tag}\)\]\s+public .*\b{field}\b',upstream)
        assert re.search(rf'\[ProtoMember\({tag}\)\]\s+public .*\b{field}\b',wire)
    real_orbits=Path(next(m['path'] for m in inv['mods'] if m['id']=='2609118808'))
    orbit_source=(real_orbits/'Data/Scripts/RealisticGravity/OrbitSettingsConfig.cs').read_text(encoding='utf-8-sig')
    assert re.search(r'GlobalMaxSpeedMultiplier_LargeGrid\s*=\s*-1F',orbit_source)
    assert re.search(r'GlobalMaxSpeedMultiplier_SmallGrid\s*=\s*-1F',orbit_source)
    print(json.dumps({'checks':'passed','workshop_mods':len(ids),'voxel_total':vox['total'],
                      'selected_bodies':sorted(selected),'world':str(world),
                      'collection_items':len(collection['items'])},indent=2))

if __name__=='__main__':main()

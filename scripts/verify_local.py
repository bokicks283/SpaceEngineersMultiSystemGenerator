"""Cross-check the audited pack, source contracts, and prepared world before runtime tests."""
import json, os, re, xml.etree.ElementTree as ET, zipfile
from pathlib import Path
from audit import ROOT, OUT, ALLOW, DENY
from prepare_pack import CUTS
from world_checkpoint import RSG_KEY, get_variable

def main():
    inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    plan=json.loads((OUT/'pack-plan.json').read_text(encoding='utf-8'))
    vox=json.loads((OUT/'selected-voxel-audit.json').read_text(encoding='utf-8'))
    coverage=json.loads((OUT/'coverage.json').read_text(encoding='utf-8'))
    ids=[m['id'] for m in plan['selected_workshop']]
    assert len(ids)==len(set(ids)) and not set(ids)&set(DENY)
    assert not set(ids)&CUTS and vox['total']==118 and vox['headroom']==10
    assert all(c['science_status'] in ('native','local authored preset') for c in coverage if c['selected'])
    source=(ROOT/'mods/RandomSectorGenerator/Data/Scripts/RandomSectorGenerator/RandomSectorGeneratorSession.cs').read_text(encoding='utf-8')
    csharp=set(re.findall(r'"([A-Za-z][A-Za-z -]+)"',source.split('AllowedPlanets =',1)[1].split('};',1)[0]))
    selected={c['planet'] for c in coverage if c['selected']}
    assert selected<=csharp,(selected-csharp)
    assert csharp.isdisjoint({c['planet'] for c in coverage if not c['selected']})
    assert 'DefaultBlackHole' in source and 'RSG_DisposableBootstrap_v1' in source
    science=ET.parse(ROOT/'mods/CampaignScienceCompatibility/Data/CampaignBiomes.sbc')
    authored={e.text.removeprefix('PlanetBiomePresetType_') for e in science.findall('.//SubtypeId')}
    assert {'Cauldron','Zenitaia'}<=authored
    for el in science.findall('.//EntityComponent'):
        desc=el.findtext('Description','')
        assert 'Biome:' in desc and 'ScienceReward:' in desc
    world=Path(os.environ['APPDATA'])/'SpaceEngineers/Saves/76561198045624840/RSG Disposable Audit 2026-09-27'
    trees=[ET.parse(world/name) for name in ['Sandbox.sbc','Sandbox_config.sbc']]
    for t in trees:
        actual=[e.findtext('PublishedFileId') for e in t.findall('./Mods/ModItem') if e.find('PublishedFileId') is not None]
        assert actual==ids
    assert get_variable(trees[0],RSG_KEY)=='blocked-proxies'
    raw=(world/'Sandbox.sbc').read_text(encoding='utf-8')
    assert 'xmlns:xsd="http://www.w3.org/2001/XMLSchema"' in raw and 'xsi:type="xsd:string"' in raw
    assert not (world/'Storage').exists()
    originals=list((ROOT/'backups').glob('World-before-disposable-clone-*.zip'))
    assert originals
    source_world=Path(inv['worlds'][0]['file'])
    with zipfile.ZipFile(sorted(originals)[-1]) as archive:
        assert archive.read('Sandbox.sbc')==source_world.read_bytes()
    # Compare the serialized field tags used in our wire types with the installed RSS types.
    rss=Path(inv['games'][0]['path'])
    upstream=(Path(inv['mods'][next(i for i,m in enumerate(inv['mods']) if m['id']=='3351055036')]['path'])/'Data/Scripts/RealSolarSystems/RealSolarSystemsConfig.cs').read_text(encoding='utf-8')
    wire=(ROOT/'mods/RandomSectorGenerator/Data/Scripts/RandomSectorGenerator/RssWireModels.cs').read_text(encoding='utf-8')
    for field,tag in [('OverrideFromConfig',1),('VoxelPlanetSpawnRangeMin',4),('VoxelPlanetSpawnRangeMax',5),('SolarSystems',6)]:
        assert re.search(rf'\[ProtoMember\({tag}\)\]\s+public .*\b{field}\b',upstream)
        assert re.search(rf'\[ProtoMember\({tag}\)\]\s+public .*\b{field}\b',wire)
    print(json.dumps({'checks':'passed','workshop_mods':len(ids),'voxel_total':vox['total'],
                      'selected_bodies':sorted(selected),'world':str(world),'original_backup_matches':True},indent=2))

if __name__=='__main__':main()

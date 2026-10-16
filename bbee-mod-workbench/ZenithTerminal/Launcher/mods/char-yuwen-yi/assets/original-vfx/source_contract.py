"""Reduce the frozen raw Cascade graph to reviewable links and parameters.

No shader, Blueprint, game or external program is executed. This reads the
already exported package bytes, rather than searching the source installation.
"""
import hashlib
import io
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
from collect import VfxPackage

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[5]
SOURCE=ROOT/'references/wandering-sword/20261016T005054Z-5a4768831a59'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def value(prop):return prop.get('value',prop.get('boolean'))

def main():
    data=json.loads((SOURCE/'vfx-reference.json').read_text('utf-8'));particles={};materials={}
    for name,item in data['packages'].items():
        if '/Materials/' in name or '/Material/' in name or '/Main_material/' in name:
            prefix=SOURCE/'raw/Wandering_Sword/Content'/name.removeprefix('/Game/')
            pkg=VfxPackage(prefix.with_suffix('.uasset').read_bytes(),prefix.with_suffix('.uexp').read_bytes())
            rows=[]
            for exp in item['exports']:
                if exp['class'] not in {'Material','MaterialInstanceConstant'}:continue
                parameters={};props={p['name']:p for p in exp['properties']}
                for field in ('ScalarParameterValues','VectorParameterValues','TextureParameterValues'):
                    for element in props.get(field,{}).get('elements',[]):
                        e={p['name']:p for p in element};pinfo=e['ParameterInfo']
                        parsed=[pkg.describe(t) for t in pkg.tags(io.BytesIO(bytes.fromhex(pinfo['raw_hex'])))];pmap={p['name']:value(p) for p in parsed}
                        if 'Name' not in pmap:raise ValueError('Material parameter name absent')
                        parameters[pmap['Name']]={'value':value(e['ParameterValue']),'field':field,'parameter_info':pmap,'property_sha256':pinfo['raw_sha256']}
                rows.append({'class':exp['class'],'name':exp['name'],'parent':value(props.get('Parent',{})),
                             'blend_mode':value(props.get('BlendMode',{})),'parameters':parameters,'imports':item['art_dependency_packages'],
                             'shader_tail_simulated':False,'shader_tail_sha256':exp['tail_sha256']})
            materials[name]=rows
        if any(e['class']=='ParticleSystem' for e in item['exports']):
            byid={e['index']:e for e in item['exports']};emitters=[]
            for exp in item['exports']:
                if exp['class']!='ParticleSpriteEmitter':continue
                p={x['name']:x for x in exp['properties']};lods=value(p.get('LODLevels',{})) or []
                for l in lods[:1]:
                    lod=byid[l['index']];lp={x['name']:x for x in lod['properties']};r=byid[value(lp['RequiredModule'])['index']];rp={x['name']:x for x in r['properties']}
                    mods=[byid[m['index']] for m in (value(lp.get('Modules',{})) or [])]
                    lifetime=[]
                    for m in mods:
                        if m['class']=='ParticleModuleLifetime':
                            for prop in m['properties']:
                                if prop['name']=='Lifetime':lifetime.append({f['name']:value(f) for f in prop['fields'] if f['name'] in {'MinValue','MaxValue','Distribution'}})
                    emitters.append({'emitter':exp['name'],'lod':lod['name'],'enabled':value(lp.get('bEnabled',{})),
                                     'material':value(rp.get('Material',{})), 'duration':value(rp.get('EmitterDuration',{})),
                                     'delay':value(rp.get('EmitterDelay',{})), 'loops':value(rp.get('EmitterLoops',{})),
                                     'subimages':[value(rp.get('SubImages_Horizontal',{})) or 1,value(rp.get('SubImages_Vertical',{})) or 1],
                                     'subuv_interpolation':value(rp.get('InterpolationMethod',{})),
                                     'screen_alignment':value(rp.get('ScreenAlignment',{})), 'lifetimes':lifetime,
                                     'module_classes':[m['class'] for m in mods],
                                     'omitted_fields':'Absent tagged fields use UE class defaults, not guessed here.'})
            particles[name]=emitters
    result={'schema':1,'source_manifest':str(SOURCE/'manifest.json'),'source_manifest_sha256':digest(SOURCE/'manifest.json'),
            'source_dataset_sha256':digest(SOURCE/'vfx-reference.json'),'source_code_sha256':digest(Path(__file__)),
            'particles':particles,'materials':materials,
            'scope':'Original first-LOD emitter links, explicit parameters and material overrides only. Cooked shader graphs/native mesh tails are not emulated.'}
    path=HERE/'source-contract.json'
    if path.exists():raise ValueError('Do not replace a frozen source contract')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'particles':len(particles),'materials':len(materials),'sha256':digest(path)},ensure_ascii=False))

if __name__=='__main__':main()

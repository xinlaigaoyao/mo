"""Hash-bound original Wandering Sword texture migration and 2D reconstruction.

The source Cascade/material contract is evidence, not executable UE simulation.
Sprite projections, RG mask recolouring, finite timing and alpha composition are
explicit BBEE adaptations. No geometric placeholder or body sprite is used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
import numpy as np
from PIL import Image, ImageChops, ImageDraw

HERE=Path(__file__).resolve().parent
WORKBENCH=HERE.parents[3]
ASSETS=HERE/'assets/original-vfx'
REFERENCE=WORKBENCH/'references/wandering-sword/20261016T005054Z-5a4768831a59/manifest.json'
SOURCE_CONTRACT=ASSETS/'source-contract.json'
MANIFEST=ASSETS/'adapted/manifest.json'
PAK_SHA='5e049dc376c36dacadf6edb6fab133942679b54b1809d7f483728deec35beaff'
SWORD='/Game/JH/ParticleSystem/Effects/AdvancedMagicFX09/'
FLARE='/Game/JH/ParticleSystem/Effects/AdvancedMagicFX15/'
TAIJI='/Game/JH/ParticleSystem/DZ_Effects/TaiJi/'
IMPACT='/Game/JH/ParticleSystem/Effects/AdvancedMagicFX01/'
FLASH='/Game/JH/ParticleSystem/Effects/MagicFxCollection01/'
SPECS={
    'sword_echo':{'frames':24,'ticks':24,'loop':False,'canvas':[128,96],'anchor':[64,48]},
    'zhenwu_wave':{'frames':30,'ticks':90,'loop':False,'canvas':[128,96],'anchor':[64,48]},
    'qi_impact':{'frames':24,'ticks':24,'loop':False,'canvas':[112,112],'anchor':[56,56]},
    'taiji_counter':{'frames':30,'ticks':30,'loop':False,'canvas':[128,128],'anchor':[64,64]},
    'wuxiang':{'frames':30,'ticks':60,'loop':False,'canvas':[144,144],'anchor':[72,72]},
    'taiji_charge':{'frames':30,'ticks':60,'loop':True,'canvas':[96,96],'anchor':[48,48]},
    'taiji_circle':{'frames':24,'ticks':48,'loop':False,'canvas':[144,144],'anchor':[72,72]},
    'ultra_field':{'frames':30,'ticks':90,'loop':False,'canvas':[160,160],'anchor':[80,80]},
}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def plain(path,root=WORKBENCH):
    path=Path(os.path.abspath(path))
    if not path.is_relative_to(root):raise ValueError('VFX path escapes owned root')
    for p in (path,*path.parents):
        if p.exists() and (p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&0x400):raise ValueError('VFX reparse point')
        if p==root:break
    return path

def checked_json(path,expected=None):
    path=plain(path)
    if not path.is_file() or path.stat().st_size>16*1024*1024 or expected and sha(path)!=expected:raise ValueError('VFX JSON changed/oversized')
    return json.loads(path.read_text('utf-8'))

def reference():
    manifest=checked_json(REFERENCE)
    if manifest.get('kind')!='original_vfx_reference' or manifest['source']['source_pak_sha256']!=PAK_SHA:raise ValueError('Original VFX source mismatch')
    names=set()
    for output in manifest['outputs']:
        rel=output['file']
        if rel in names or '\\' in rel or ':' in rel or '..' in Path(rel).parts or Path(rel).is_absolute():raise ValueError('VFX output path invalid')
        names.add(rel);p=plain(REFERENCE.parent/rel)
        if not p.is_file() or sha(p)!=output['sha256']:raise ValueError('Original VFX raw/pixel output changed')
    # Bind the original producer and its unchanged, strict dependencies.
    if sha(ASSETS/'collect.py')!=manifest['source_code']['collect.py']:raise ValueError('Original collection producer changed')
    contract=checked_json(SOURCE_CONTRACT)
    if contract['source_manifest_sha256']!=sha(REFERENCE) or contract['source_dataset_sha256']!=sha(REFERENCE.parent/'vfx-reference.json') or contract['source_code_sha256']!=sha(ASSETS/'source_contract.py'):raise ValueError('Source parameter contract changed')
    return manifest,checked_json(REFERENCE.parent/'vfx-reference.json'),contract

class Textures:
    def __init__(self,data):self.records={r['package']:r for r in data['textures']};self.used={};self.cache={}
    def get(self,package):
        if package not in self.records:raise ValueError('Unresolved actual original texture '+package)
        r=self.records[package];path=plain(REFERENCE.parent/r['png'])
        if sha(path)!=r['sha256']:raise ValueError('Original texture pixels changed')
        self.used[package]={**r,'file':str(path)}
        if package not in self.cache:
            with Image.open(path) as im:
                im.load()
                if im.mode!='RGBA' or im.size!=(r['width'],r['height']):raise ValueError('Original texture dimensions changed')
                self.cache[package]=im.copy()
        return self.cache[package].copy()

def opacity(image,amount):
    image=image.copy();image.putalpha(image.getchannel('A').point(lambda a:round(a*max(0,min(1,amount)))))
    return image

def recolour(image,channel='max',color=(170,230,255),gain=1):
    a=np.asarray(image).astype(np.float32)
    mask=np.max(a[:,:,:3],axis=2) if channel=='max' else a[:,:,{'R':0,'G':1,'B':2,'A':3}[channel]]
    # Opaque RGB-encoded SubUV black backgrounds become alpha. Source-alpha
    # ink assets keep their original RGB and alpha via a separate path.
    mask=np.clip(mask*gain,0,255);out=np.zeros(a.shape,dtype=np.uint8)
    out[:,:,:3]=color;out[:,:,3]=np.minimum(mask,a[:,:,3]).astype(np.uint8)
    return Image.fromarray(out,'RGBA')

def feather(image,fraction=.10):
    """Explicit 2D UV soft-edge matte for RGB masks touching a source tile.

    Cooked UE material/mesh clipping is unavailable in the Unity sprite route;
    this declared reconstruction avoids showing the rectangular source plane.
    It does not claim to reproduce the original shader's opacity expression.
    """
    a=np.asarray(image).copy();h,w=a.shape[:2]
    xs=np.minimum(np.arange(w),np.arange(w)[::-1])/max(1,w*fraction)
    ys=np.minimum(np.arange(h),np.arange(h)[::-1])/max(1,h*fraction)
    x=np.clip(xs,0,1);y=np.clip(ys,0,1);x=x*x*(3-2*x);y=y*y*(3-2*y)
    a[:,:,3]=np.rint(a[:,:,3].astype(float)*y[:,None]*x[None,:]).astype(np.uint8)
    return Image.fromarray(a,'RGBA')

def ink_pressure(textures):
    # Actual A61 has opaque alpha across a black RGB rectangle. It is a white
    # pressure/ink mask, unlike A51/A7 whose original alpha already silhouettes
    # the yin-yang/water swirl. Convert this specific mask, preserving the rest.
    return feather(recolour(textures.get(TAIJI+'Texture/fx_Ink_A61'),'max',(238,246,247)),.06)

def cell(image,columns,rows,index):
    if image.width%columns or image.height%rows or not 0<=index<columns*rows:raise ValueError('Invalid actual SubUV grid')
    w,h=image.width//columns,image.height//rows;x=index%columns*w;y=index//columns*h
    return image.crop((x,y,x+w,y+h))

def layer(canvas,image,size,center=None,angle=0,alpha=1):
    size=tuple(max(1,round(v)) for v in size)
    image=image.resize(size,Image.Resampling.LANCZOS)
    if angle:image=image.rotate(angle,Image.Resampling.BICUBIC,expand=True)
    image=opacity(image,alpha)
    center=center or (canvas.width/2,canvas.height/2)
    canvas.alpha_composite(image,(round(center[0]-image.width/2),round(center[1]-image.height/2)))

def smooth(t):return max(0,min(1,t))**2*(3-2*max(0,min(1,t)))
def envelope(u,attack=.12,release=.35):return max(.012,min(smooth(u/attack),smooth((1-u)/release)))

def render(kind,index,textures):
    spec=SPECS[kind];u=index/(spec['frames']-1);canvas=Image.new('RGBA',tuple(spec['canvas']),(0,0,0,0));cx,cy=spec['anchor']
    if kind in {'sword_echo','zhenwu_wave'}:
        fire=textures.get(SWORD+'Textures/T_ky_fire01_4x8')
        fire=cell(fire,4,8,min(31,round(u*31)))
        # The 4x8 layout is read from Required_13 of original waveSlash1.
        blade=feather(recolour(fire,'R',(210,241,255),1.15),.14).rotate(-90,expand=True)
        core=feather(recolour(fire,'G',(92,185,245),.75),.18).rotate(-90,expand=True)
        env=envelope(u,.10,.22 if kind=='zhenwu_wave' else .36)
        extent=(38+38*smooth(u/.16),45+20*smooth(u/.13))
        tail=recolour(textures.get(SWORD+'Textures/T_ky_dust_longStar'),'max',(100,185,240))
        layer(canvas,tail,(90,10),(cx-13,cy),alpha=env*.48)
        smoke=recolour(textures.get(SWORD+'Textures/T_ky_smoke2'),'max',(95,168,210))
        layer(canvas,smoke,(60,44),(cx-22-10*u,cy),angle=25+u*90,alpha=env*.25)
        layer(canvas,blade,extent,(cx-2,cy),alpha=env*.35)
        layer(canvas,core,extent,(cx-2,cy),alpha=env*.12)
        # The same source GA also references flare1's real 4x4 shockwave.
        # Project its right half as the leading curved edge. This is a declared
        # original-texture composite, not a generated polygon/ellipse or an
        # assertion that the UE source rendered this exact combined mesh.
        original_wave=cell(textures.get(FLARE+'Textures/T_ky_shockwave04_4x4'),4,4,min(15,round(u*15)))
        original_wave=original_wave.crop((original_wave.width//2,0,original_wave.width,original_wave.height))
        leading=feather(recolour(original_wave,'R',(207,242,255),1.5),.05)
        layer(canvas,leading,(32+5*smooth(u/.15),extent[1]+8),(cx+20,cy),alpha=env*.95)
        flare=textures.get(SWORD+'Textures/T_ky_flare_a')
        layer(canvas,flare,(18,18),(cx+12,cy),alpha=env*.65)
    elif kind=='qi_impact':
        env=envelope(u,.08,.48);s=20+78*smooth(u/.75)
        shine=cell(textures.get(FLARE+'Textures/T_ky_shine01_4x4'),4,4,min(15,round(u*15)))
        wave=cell(textures.get(FLARE+'Textures/T_ky_shockwave04_4x4'),4,4,min(15,round(u*15)))
        layer(canvas,recolour(wave,'R',(98,185,230)),(s,s),alpha=env*.8)
        layer(canvas,recolour(shine,'G',(240,251,255)),(s*.72,s*.72),alpha=env)
        ink=ink_pressure(textures)
        layer(canvas,ink,(s*.8,s*.55),angle=-15,alpha=env*.35)
    else:
        ink=textures.get(TAIJI+'Texture/fx_Ink_A51');swirl=textures.get(TAIJI+'Texture/fx_Ink_A7');ring=textures.get(TAIJI+'Texture/fx_Ink_A17')
        if kind=='taiji_charge':
            env=.55+.15*math.sin(u*2*math.pi);s=57+3*math.sin(u*2*math.pi)
            layer(canvas,ring,(s+12,s+12),angle=-u*360,alpha=env*.7)
            layer(canvas,ink,(s,s),angle=u*360,alpha=env)
            layer(canvas,swirl,(s+13,s+13),angle=-u*360,alpha=env*.65)
        else:
            env=envelope(u,.12,.35);width={'taiji_counter':98,'wuxiang':116,'taiji_circle':120,'ultra_field':140}[kind]
            s=width*(.38+.62*smooth(u/.3));speed={'taiji_counter':240,'wuxiang':360,'taiji_circle':270,'ultra_field':540}[kind]
            # The original ink/taiji images remain visible; optional white
            # pressure layers use original masks, never synthetic circles.
            layer(canvas,ring,(s,s),angle=-u*speed*.7,alpha=env*.85)
            layer(canvas,ink,(s*.78,s*.78),angle=u*speed,alpha=env*.9)
            layer(canvas,swirl,(s,s),angle=-u*speed,alpha=env*.85)
            if kind in {'taiji_counter','ultra_field'}:
                splash=ink_pressure(textures)
                layer(canvas,splash,(s*.95,s*.7),angle=30+u*90,alpha=env*.5)
            if kind in {'wuxiang','taiji_circle','ultra_field'}:
                corona=cell(textures.get(IMPACT+'Textures/T_circle9_4x4'),4,4,min(15,round(u*15)))
                layer(canvas,recolour(corona,'max',(132,213,245)),(s*1.02,s*1.02),alpha=env*.55)
                spark=recolour(textures.get(FLASH+'Textures/T_ky_decoLinesC'),'max',(205,240,255))
                layer(canvas,spark,(s*.25,s*.65),angle=u*speed,alpha=env*.45)
    # Last frames remain nonempty but almost transparent; native action end
    # owns destruction. Outer edge is transparent by construction/padding.
    canvas=feather(canvas,.04)
    if canvas.getchannel('A').getbbox() is None:raise ValueError('VFX reconstruction became invisible')
    return canvas

def create():
    manifest,data,contract=reference();target=plain(MANIFEST.parent,ASSETS)
    if target.exists():raise ValueError('Preserve existing complete VFX before regeneration')
    target.mkdir();textures=Textures(data);clips={};outputs=[]
    try:
        for kind,spec in SPECS.items():
            frames=[];pictures=[]
            for index in range(spec['frames']):
                im=render(kind,index,textures)
                # Effects have a fixed per-clip sampling density; retaining
                # designed world extents does not need 1280px texture quads.
                # This keeps the existing native atlas/page memory caps. It
                # never rescales individual body poses or changes hit boxes.
                sample_scale=min(1,96/max(spec['canvas']))
                pixel_size=[round(v*sample_scale) for v in spec['canvas']]
                anchor=[round(v*sample_scale) for v in spec['anchor']]
                im=im.resize(tuple(pixel_size),Image.Resampling.LANCZOS)
                relative=f'frames/{kind}/{index:03d}.png';p=target/relative;p.parent.mkdir(parents=True,exist_ok=True)
                with p.open('xb') as f:im.save(f,'PNG')
                with Image.open(p) as actual:
                    actual.load()
                    if actual.tobytes()!=im.tobytes():raise ValueError('VFX PNG pixel readback mismatch')
                entry={'file':relative,'sha256':sha(p),'size':list(im.size),'anchor':anchor,'world_scale_multiplier':1/sample_scale,'ticks':spec['ticks']//spec['frames'],'index':index,'alpha_bbox':list(im.getchannel('A').getbbox())}
                frames.append(entry);outputs.append({'file':relative,'sha256':entry['sha256']});pictures.append(im)
            clips[kind]={**spec,'pixel_canvas':pixel_size,'world_scale_multiplier':1/sample_scale,'sequence':frames,'scope':'Original texture/SubUV pixels with declared 2D projection, recolour and timing adaptation.'}
            preview=target/(kind+'.png');pictures[0].save(preview,'PNG',save_all=True,append_images=pictures[1:],duration=spec['ticks']*1000/60/spec['frames'],loop=0,disposal=0,blend=0)
            outputs.append({'file':preview.name,'sha256':sha(preview)})
            sheet=Image.new('RGB',(8*160,3*184),'#263342');draw=ImageDraw.Draw(sheet)
            indices=[round(i*(len(pictures)-1)/23) for i in range(24)]
            for i,j in enumerate(indices):
                im=pictures[j];x=(i%8)*160+(160-im.width)//2;y=(i//8)*184
                sheet.paste(im,(x,y),im);draw.text(((i%8)*160+4,y+163),f'{kind} f{j} t{j*spec["ticks"]/spec["frames"]/60:.2f}',fill='white')
            contact=target/(kind+'-contact.png');sheet.save(contact);outputs.append({'file':contact.name,'sha256':sha(contact)})
        result={'schema':1,'kind':'yuwen_original_texture_vfx_adaptation','source_pak_sha256':PAK_SHA,
                'reference_manifest':str(REFERENCE),'reference_manifest_sha256':sha(REFERENCE),'source_contract':str(SOURCE_CONTRACT),'source_contract_sha256':sha(SOURCE_CONTRACT),
                'producer':str(Path(__file__)),'producer_sha256':sha(Path(__file__)),'used_original_textures':textures.used,'clips':clips,'outputs':outputs,
                'source_scope':'132 source packages, 313 raw members, 54 decoded original Texture2Ds; declared roots are skill GA -> seven actual Cascade systems -> materials -> textures/SubUV.',
                'adaptation':{'engine':'Unity native sprite rig; no UE code/Blueprint/shader executes', 'composition':'Precomposed original-texture layers, finite life, RG SubUV channel masks, alpha conversion; original ink RGBA kept',
                              'orientation':'positive X flame peak via clockwise 90-degree source projection, negative X source-star/smoke tail; actor engine mirrors left', 'timing':'60 Hz BBEE finite timelines, separate 90-tick flight and 24-tick hit; no eight-frame placeholder',
                              'opacity':'A61 opaque black-backed RGB pressure texture becomes luminance alpha; original true-alpha A51/A7/A17 retain native alpha; RGB SubUV planes use explicit UV soft-edge matte; source flare1 shockwave right-half projects the sword leading arc; this is 2D material adaptation, not original shader evaluation',
                              'pixel_density':'Each effect clip sampled to a maximum 96-pixel canvas with a declared fixed world scale; source body sampling and the native 16-page memory cap stay fixed',
                              'limits':['Not an exact Cascade simulation or lossless shader copy','Original distortion, native mesh deformation and particle collisions are not implemented','Colors/scale/timing are declared BBEE adaptations; native scene acceptance pending']},
                'visual_acceptance':'pending','runtime_acceptance':'pending'}
        with MANIFEST.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
        print(json.dumps({'status':'vfx_reconstructed','manifest':str(MANIFEST),'sha256':sha(MANIFEST),'frames':sum(s['frames'] for s in SPECS.values()),'clips':len(clips),'runtime':'pending'},ensure_ascii=False))
    except BaseException:
        if plain(target,ASSETS)!=ASSETS/'adapted':raise ValueError('Refusing unrelated cleanup')
        shutil.rmtree(target);raise

def prepared():
    data=checked_json(MANIFEST)
    if data.get('kind')!='yuwen_original_texture_vfx_adaptation' or data.get('source_pak_sha256')!=PAK_SHA or data.get('producer_sha256')!=sha(Path(__file__)):raise ValueError('VFX producer/source drift; recreate full affected art batch')
    reference()
    if data['reference_manifest_sha256']!=sha(REFERENCE) or data['source_contract_sha256']!=sha(SOURCE_CONTRACT) or set(data['clips'])!=set(SPECS):raise ValueError('VFX source/clip contract drift')
    for out in data['outputs']:
        p=plain(MANIFEST.parent/out['file'],MANIFEST.parent)
        if sha(p)!=out['sha256']:raise ValueError('Adapted VFX file changed')
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare']);p.parse_args();create()

"""Bounded original UE4.26 Cascade references; source game stays read-only.

This independent package profile allows the larger actual ParticleSystem export
tables. The old nine-member and Paper2D decoders are not changed. It parses data,
never loads UE code, shaders or particle simulation binaries.
"""
from __future__ import annotations
import io
import hashlib
import json
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
WORKBENCH = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(WORKBENCH / "scripts"))
from wandering_reference import checked_read, unpack, fstring, ReferenceError, PakV11, PAK_PATH, EXPECTED_PAK_SHA256, output_directory, remove_owned_output, write_json_exclusive, plain_path
from wandering_decode_reference import Package, require, MAGIC


class VfxPackage(Package):
    """Exact traditional UE4.26 framing, capped larger object tables."""
    def __init__(self, asset, uexp):
        require(len(asset) <= 16*1024*1024 and len(uexp) <= 128*1024*1024, "VFX package exceeds caps")
        self.asset, self.uexp = asset, uexp
        stream = io.BytesIO(asset)
        require(unpack(stream,"<Iiiiii") == (MAGIC,-7,0,0,0,0),"Unsupported VFX package version")
        self.header_size = unpack(stream,"<i")[0]
        require(self.header_size == len(asset) and fstring(stream)=="None","VFX split header mismatch")
        self.flags, name_count, name_offset = unpack(stream,"<Iii")
        require(self.flags==0x80000000,"Unsupported VFX package flags")
        gather_count,gather_offset,export_count,export_offset,import_count,import_offset=unpack(stream,"<iiiiii")
        require(gather_count==gather_offset==0,"VFX localization table unsupported")
        require(0<name_count<=100000 and 0<export_count<=4096 and 0<import_count<=4096,"VFX object table caps")
        require(0<=name_offset<import_offset<export_offset<len(asset),"VFX table order mismatch")
        stream.seek(name_offset);self.names=[]
        for _ in range(name_count):self.names.append(fstring(stream));checked_read(stream,4)
        require(stream.tell()==import_offset,"VFX name-map boundary mismatch")
        self.imports=[]
        for _ in range(import_count):
            cp,cn=self.fname(stream),self.fname(stream);outer=unpack(stream,"<i")[0];name=self.fname(stream)
            self.imports.append({"class_package":cp,"class":cn,"outer_index":outer,"object":name})
        require(stream.tell()==export_offset,"VFX import-map boundary mismatch")
        self.exports=[];previous=len(asset)
        for _ in range(export_count):
            row=io.BytesIO(checked_read(stream,104));ci,si,ti,oi=unpack(row,"<iiii");name=self.fname(row);flags,size,offset=unpack(row,"<Iqq")
            require(offset==previous and size>=0 and offset+size<=len(asset)+len(uexp)-4,"VFX export ranges mismatch")
            previous=offset+size;self.exports.append({"class_index":ci,"super_index":si,"template_index":ti,"outer_index":oi,"name":name,"flags":flags,"size":size,"offset":offset})
        require(previous==len(asset)+len(uexp)-4 and uexp[-4:]==struct.pack("<I",MAGIC),"VFX split trailer/coverage mismatch")

    def object(self, index):
        if index==0:return None
        entry=self.resolve(index)
        if index<0:
            parent=self.resolve(entry['outer_index'])
            return {"index":index,"name":entry['object'],"class":entry['class'],"package":parent['object'] if parent and parent['class']=='Package' else None}
        exp=self.exports[index-1]
        return {"index":index,"name":exp['name'],"class":self.resolve(exp['class_index'])['object'],"package":None}

    def tags(self, stream):
        result=[]
        for _ in range(4096):
            name=self.fname(stream)
            if name=='None':return result
            kind=self.fname(stream);size,array_index=unpack(stream,'<ii')
            require(0<=size<=64*1024*1024 and 0<=array_index<4096,'VFX property bounds')
            extra={}
            if kind=='StructProperty':extra={'struct':self.fname(stream),'struct_guid':checked_read(stream,16).hex()}
            elif kind=='BoolProperty':extra={'boolean':unpack(stream,'<B')[0]};require(extra['boolean'] in (0,1),'VFX bool')
            elif kind in {'ByteProperty','EnumProperty'}:extra={'enum':self.fname(stream)}
            elif kind in {'ArrayProperty','SetProperty'}:extra={'inner':self.fname(stream)}
            elif kind=='MapProperty':extra={'key_kind':self.fname(stream),'value_kind':self.fname(stream)}
            else:require(kind in {'IntProperty','FloatProperty','ObjectProperty','NameProperty','StrProperty','TextProperty','SoftObjectProperty','Int64Property','UInt32Property','DoubleProperty'},'Unknown VFX property tag '+kind)
            has_guid=unpack(stream,'<B')[0];require(has_guid in (0,1),'VFX property GUID flag')
            if has_guid:extra['property_guid']=checked_read(stream,16).hex()
            result.append({'name':name,'kind':kind,'array_index':array_index,'raw':checked_read(stream,size),**extra})
        raise ReferenceError('VFX property cap')

    def describe(self, entry):
        value={k:v for k,v in entry.items() if k!='raw'};raw=entry['raw'];kind=entry['kind'];value['bytes']=len(raw);value['raw_sha256']=hashlib.sha256(raw).hexdigest()
        if kind=='ObjectProperty' and len(raw)==4:value['value']=self.object(struct.unpack('<i',raw)[0])
        elif kind=='FloatProperty' and len(raw)==4:value['value']=struct.unpack('<f',raw)[0]
        elif kind=='IntProperty' and len(raw)==4:value['value']=struct.unpack('<i',raw)[0]
        elif kind=='NameProperty' and len(raw)==8:value['value']=self.fname(io.BytesIO(raw))
        elif kind in {'ByteProperty','EnumProperty'} and len(raw)==8:value['value']=self.fname(io.BytesIO(raw))
        elif kind=='ByteProperty' and len(raw)==1:value['value']=raw[0]
        elif kind=='StructProperty' and entry['struct'] in {'Vector','LinearColor','Vector2D'} and len(raw) in (8,12,16):value['value']=list(struct.unpack('<'+'f'*(len(raw)//4),raw))
        elif kind=='ArrayProperty' and entry['inner']=='ObjectProperty':
            s=io.BytesIO(raw);count=unpack(s,'<i')[0];require(0<=count<=4096 and len(raw)==4+count*4,'VFX Object array')
            value['value']=[self.object(unpack(s,'<i')[0]) for _ in range(count)]
        elif kind=='StructProperty' and entry['struct'].startswith('RawDistribution'):
            s=io.BytesIO(raw);value['fields']=[self.describe(t) for t in self.tags(s)];value['lookup_tail_hex']=s.read().hex()
        elif kind=='ArrayProperty' and entry['inner']=='StructProperty':
            s=io.BytesIO(raw);count=unpack(s,'<i')[0];require(0<=count<=4096,'VFX struct array count')
            if count:
                inner_name=self.fname(s);inner_kind=self.fname(s);inner_size,inner_index=unpack(s,'<ii');inner_struct=self.fname(s);inner_guid=checked_read(s,16).hex();has_guid=unpack(s,'<B')[0]
                require(inner_kind=='StructProperty' and inner_index==0 and has_guid==0,'VFX struct array header')
                value['struct']=inner_struct
                if inner_struct in {'TextureParameterValue','ScalarParameterValue','VectorParameterValue','MaterialTextureInfo','ScalarParameterAtlasInstanceData'}:
                    value['elements']=[[self.describe(t) for t in self.tags(s)] for _ in range(count)]
                    value['array_tail_hex']=s.read().hex()
                else:value['native_struct_payload_hex']=s.read().hex()
        elif len(raw)<=1024:value['raw_hex']=raw.hex()
        return value


ROOTS=[
      'JH/Skills/WD_J_ZhenWuJianQi/GA_WD_J_ZhenWuJianQi',
      'JH/Skills/WD_J_LiuYunTaiJian/GA_WD_J_LiuYunTaiJian',
      'JH/Skills/WD_Z_LiuYunTaiQuan/GA_WD_Z_LiuYunTaiQuan',
      'JH/ParticleSystem/Effects/AdvancedMagicFX09/Particles/P_ky_waveSlash1',
      'JH/ParticleSystem/Effects/AdvancedMagicFX15/Particles/P_ky_flare1',
      'JH/ParticleSystem/DZ_Effects/TaiJi/particle/xuli2',
      'JH/ParticleSystem/DZ_Effects/TaiJi/particle/xuli4',
      'JH/ParticleSystem/DZ_Effects/TaiJi/particle/xuli1',
      'JH/ParticleSystem/Effects/AdvancedMagicFX01/Particles/P_flareInpact',
      'JH/ParticleSystem/Effects/MagicFxCollection01/KYmagicFX03/Particles/P_ky_flashImpact',
]


def texture(package, index, bulk):
    """Exact observed cooked desktop formats, all mips/bulk offsets checked."""
    import texture2ddecoder
    from PIL import Image
    stream=package.export(index);props=package.tags(stream)
    require(unpack(stream,'<i')[0]==0,'VFX Texture UObject GUID')
    require(checked_read(stream,4)==b'\x01\x00\x01\x00' and unpack(stream,'<i')[0]==1,'VFX cooked texture framing')
    fmt=package.fname(stream);require(fmt in {'PF_B8G8R8A8','PF_DXT1','PF_DXT5','PF_BC5','PF_BC7','PF_G8'},'Unsupported VFX texture format '+fmt)
    skip=unpack(stream,'<q')[0];w,h,slices=unpack(stream,'<iiI')
    require(0<w<=4096 and 0<h<=4096 and w*h<=4194304 and slices==1,'VFX texture dimensions')
    require(fstring(stream)==fmt,'VFX texture format disagreement')
    first,count=unpack(stream,'<ii');require(0<=first<=12 and 1<=count<=13,'VFX texture mip count')
    mips=[];pixels=None
    for mi in range(count):
        require(unpack(stream,'<i')[0]==1,'VFX cooked mip marker')
        flags,n,stored,offset=unpack(stream,'<Iiiq')
        require(0<=n==stored<=64*1024*1024,'VFX mip size')
        if flags in {0x48,0x40}:
            require(offset==package.exports[index]['offset']+stream.tell(),'VFX inline mip offset')
            payload=checked_read(stream,stored)
        elif flags in {0x101,0x100,0x401,0x501,0x10501}:
            require(bulk is not None and 0<=offset<=len(bulk)-stored,'VFX external mip bounds')
            payload=bulk[offset:offset+stored]
        else:raise ReferenceError('Unsupported VFX bulk flags '+hex(flags))
        floor=1 if fmt in {'PF_G8','PF_B8G8R8A8'} else 4
        mw,mh,depth=unpack(stream,'<iii');require(mw==max(floor,w>>mi) and mh==max(floor,h>>mi) and depth==1,f'VFX mip dimensions {package.exports[index]["name"]} platform={w,h} first={first} mip={mi} got={mw,mh,depth} flags={flags:x} bytes={stored}')
        block=8 if fmt=='PF_DXT1' else 16
        expected=mw*mh*({'PF_B8G8R8A8':4,'PF_G8':1}.get(fmt,0)) or ((mw+3)//4)*((mh+3)//4)*block
        require(stored==expected,'VFX mip block bytes')
        mips.append({'width':mw,'height':mh,'flags':hex(flags),'offset':offset,'bytes':stored,'sha256':hashlib.sha256(payload).hexdigest()})
        if mi==0:
            if fmt=='PF_B8G8R8A8':pixels=Image.frombytes('RGBA',(mw,mh),payload,'raw','BGRA',0,1)
            elif fmt=='PF_G8':pixels=Image.frombytes('L',(mw,mh),payload).convert('RGBA')
            else:
                decode={'PF_DXT1':texture2ddecoder.decode_bc1,'PF_DXT5':texture2ddecoder.decode_bc3,'PF_BC5':texture2ddecoder.decode_bc5,'PF_BC7':texture2ddecoder.decode_bc7}[fmt]
                pixels=Image.frombytes('RGBA',(mw,mh),decode(payload,mw,mh),'raw','BGRA',0,1)
    require(unpack(stream,'<i')[0]==0 and package.exports[index]['offset']+stream.tell()==skip,'VFX texture virtual/platform boundary')
    require(package.fname(stream)=='None' and stream.tell()==package.exports[index]['size'],'VFX additional format/export tail')
    return pixels,{'format':fmt,'width':w,'height':h,'first_mip':first,'mips':mips,'properties':[package.describe(t) for t in props]}


def main():
    from PIL import Image
    from wandering_character_reference import safe_bytes, png_bytes
    raw,receipts,packages,images={}, {}, {}, []
    pending=['/Game/'+stem for stem in ROOTS]
    target=output_directory()
    try:
      with PAK_PATH.open('rb') as reader:
        pak=PakV11(reader,EXPECTED_PAK_SHA256)
        def selected(member,cap):
            if member in raw:return raw[member]
            require(len(raw)<768,'VFX member cap')
            data,receipt=pak.read_selected(member,cap)
            require(sum(map(len,raw.values()))+len(data)<=512*1024*1024,'VFX total bytes cap')
            raw[member]=data;receipts[member]=receipt
            return data
        while pending:
            stem=pending.pop(0)
            if stem in packages:continue
            require(len(packages)<256 and stem.startswith('/Game/JH/'),'VFX package graph bound')
            prefix='Wandering_Sword/Content/'+stem.removeprefix('/Game/')
            a=selected(prefix+'.uasset',16*1024*1024);e=selected(prefix+'.uexp',128*1024*1024)
            package=VfxPackage(a,e);bulk=selected(prefix+'.ubulk',64*1024*1024) if prefix+'.ubulk' in pak.entries else None
            exports=[]
            for i,item in enumerate(package.exports):
                klass=package.resolve(item['class_index'])['object'];stream=package.export(i)
                if klass=='BlueprintGeneratedClass':continue
                tags=package.tags(stream)
                exports.append({'index':i+1,'class':klass,'name':item['name'],'properties':[package.describe(t) for t in tags],'tail_bytes':item['size']-stream.tell(),'tail_sha256':hashlib.sha256(stream.read()).hexdigest()})
                if klass=='Texture2D':
                    image,details=texture(package,i,bulk);images.append((stem,item['name'],image,details))
            imports=[x for x in package.imports if x['class']=='Package' and x['object'].startswith('/Game/')]
            # Follow only actual particle-art imports, never audio/gameplay code.
            art_refs=sorted({x['object'] for x in imports if x['object'].startswith('/Game/JH/ParticleSystem/')})
            packages[stem]={'package':stem,'exports':exports,'imports':imports,'art_dependency_packages':art_refs}
            pending.extend(x for x in art_refs if x not in packages and x not in pending)
            print(json.dumps({'reading':stem,'objects':len(exports),'textures':len(images),'packages':len(packages)}),flush=True)
        pak.assert_source_unchanged()
        outputs=[]
        for member,data in raw.items():
            path=target/'raw'/Path(*member.split('/'));outputs.append({'file':path.relative_to(target).as_posix(),'kind':'raw_member',**safe_bytes(path,data)})
        tex=[]
        for stem,name,image,details in images:
            path=target/'textures'/(hashlib.sha256(stem.encode()).hexdigest()[:16]+'_'+name+'.png')
            info=safe_bytes(path,png_bytes(image));rel=path.relative_to(target).as_posix()
            tex.append({'package':stem,'object':name,'png':rel,**info,**details})
            outputs.append({'file':rel,'kind':'original_texture_png',**info})
        dataset={'schema':1,'roots':['/Game/'+s for s in ROOTS],'packages':packages,'textures':tex,
                 'scope':'Tagged Cascade/material parameters and raw original texture pixels. Native meshes and shader tails retained with hashes, not simulated. BBEE cross-engine reconstruction remains separate.'}
        write_json_exclusive(target/'vfx-reference.json',dataset)
        outputs.append({'file':'vfx-reference.json','kind':'reference_json','sha256':hashlib.sha256((target/'vfx-reference.json').read_bytes()).hexdigest()})
        manifest={'kind':'original_vfx_reference','source':pak.summary(),'captured_utc':datetime.now(timezone.utc).isoformat(),
                  'source_code':{'collect.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
                  'members':[{**r,'output_relative':'raw/'+m} for m,r in receipts.items()], 'outputs':outputs,
                  'counts':{'packages':len(packages),'raw_members':len(raw),'raw_bytes':sum(map(len,raw.values())),'textures':len(tex)},'visual_acceptance':'pending','bbmod_ready':False}
        write_json_exclusive(target/'manifest.json',manifest)
        print(json.dumps({'status':'original_vfx_collected','manifest':str(target/'manifest.json'),'counts':manifest['counts']},ensure_ascii=False))
    except BaseException:
        remove_owned_output(target);raise

if __name__=='__main__':main()

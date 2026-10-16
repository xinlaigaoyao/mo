"""Bounded original UE4.26 Cascade references; source game stays read-only.

This independent package profile allows the larger actual ParticleSystem export
tables. The old nine-member and Paper2D decoders are not changed. It parses data,
never loads UE code, shaders or particle simulation binaries.
"""
from __future__ import annotations
import io
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
WORKBENCH = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(WORKBENCH / "scripts"))
from wandering_reference import checked_read, unpack, fstring, ReferenceError, PakV11, PAK_PATH, EXPECTED_PAK_SHA256
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
        value={k:v for k,v in entry.items() if k!='raw'};raw=entry['raw'];kind=entry['kind'];value['bytes']=len(raw)
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
        elif len(raw)<=64:value['raw_hex']=raw.hex()
        return value


def main():
    roots=[
      'JH/Skills/WD_J_ZhenWuJianQi/GA_WD_J_ZhenWuJianQi',
      'JH/Skills/WD_J_LiuYunTaiJian/GA_WD_J_LiuYunTaiJian',
      'JH/Skills/WD_Z_LiuYunTaiQuan/GA_WD_Z_LiuYunTaiQuan',
      'JH/ParticleSystem/Effects/AdvancedMagicFX09/Particles/P_ky_waveSlash1',
      'JH/ParticleSystem/Effects/AdvancedMagicFX15/Particles/P_ky_flare1',
      'JH/ParticleSystem/DZ_Effects/TaiJi/particle/xuli2',
      'JH/ParticleSystem/DZ_Effects/TaiJi/particle/xuli4',
    ]
    with PAK_PATH.open('rb') as reader:
        pak=PakV11(reader,EXPECTED_PAK_SHA256)
        for stem in roots:
            prefix='Wandering_Sword/Content/'+stem
            a,_=pak.read_selected(prefix+'.uasset',64*1024*1024);e,_=pak.read_selected(prefix+'.uexp',128*1024*1024)
            package=VfxPackage(a,e)
            exports=[]
            for i,item in enumerate(package.exports):
                klass=package.resolve(item['class_index'])['object'];stream=package.export(i)
                if klass=='BlueprintGeneratedClass':continue
                tags=package.tags(stream)
                exports.append({'index':i+1,'class':klass,'name':item['name'],'properties':[package.describe(t) for t in tags],'tail_bytes':item['size']-stream.tell()})
            print(json.dumps({'root':stem,'exports':exports,'imports':[x for x in package.imports if x['object'].startswith('/Game/')]},ensure_ascii=False),flush=True)
        pak.assert_source_unchanged()

if __name__=='__main__':main()

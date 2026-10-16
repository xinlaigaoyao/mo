"""Preview source pixels only; never invokes UE or a game executable."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[5]
SOURCE=ROOT/'references/wandering-sword/20261016T005054Z-5a4768831a59'
data=json.loads((SOURCE/'vfx-reference.json').read_text('utf-8'))
for start in range(0,len(data['textures']),18):
    sheet=Image.new('RGB',(1200,1152),'#202830');draw=ImageDraw.Draw(sheet)
    for n,t in enumerate(data['textures'][start:start+18]):
        x=(n%6)*200;y=(n//6)*384
        image=Image.open(SOURCE/t['png']).convert('RGBA');image.thumbnail((190,330))
        sheet.paste(image,(x+(200-image.width)//2,y),image)
        draw.text((x+3,y+332),t['object'][:24],fill='white')
        draw.text((x+3,y+348),t['package'].split('/')[5][:25],fill='#a0d8ff')
        draw.text((x+3,y+365),str((t['width'],t['height']))+' '+t['format'],fill='#bbbbbb')
    sheet.save(HERE/('source-contact-%02d.png'%(start//18+1)))
print('source contact pages:',(len(data['textures'])+17)//18)

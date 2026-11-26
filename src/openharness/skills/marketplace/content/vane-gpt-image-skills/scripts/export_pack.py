#!/usr/bin/env python3
"""Build grouped transparent GIFs and an optional decoded-GIF MP4 preview.

Includes code copyright (c) 2026 WoYun520 under the MIT License;
see ../references/third-party-LICENSE for the full license notice.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import hashlib
import html
import json
from math import cos, exp, pi, sin
from pathlib import Path
import re
from subprocess import Popen, PIPE
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageSequence

PIXELS = 160
SIZE = 320
TICKS = 24
DELAY = 80
NEAREST = Image.Resampling.NEAREST
WHITE = '#FFF8EF'

ICONS = {
    'spark': ['....#....','....#....','...###...','..#####..','#########','..#####..','...###...','....#....','....#....'],
    'heart': ['.###.###.','#########','#########','#########','.#######.','..#####..','...###...','....#....'],
    'tear': ['....#....','...###...','...###...','..#####..','.#######.','.#######.','..#####..','...###...'],
    'check': ['.......##','......##.','.....##..','##..##...','.####....','..##.....'],
    'question': ['..####.','.##..##','.....##','....##.','...##..','...##..','.......','...##..'],
    'alert': ['##','##','##','##','##','..','##','##'],
    'sleep': ['######','....##','...##.','..##..','.##...','######'],
    'steam': ['...##....','..####...','.######..','#########','.#######.','..#####..','...#.....','..#......'],
    'note': ['....####','....####','....#...','....#...','....#...','.####...','#####...','.###....'],
    'cross': ['##...##','.##.##.','..###..','...#...','..###..','.##.##.','##...##'],
    'bubble': ['..####..','.##..##.','##....##','##....##','.##..##.','..####..'],
    'dots': ['##.##.##','##.##.##'],
    'bolt': ['....##.','...##..','..##...','.######','....##.','...##..','..##...'],
    'arrow': ['....##.','.....##','#######','#######','.....##','....##.'],
    'petal': ['..##..','.####.','######','.####.','..##..'],
}

MOTIONS = {
    'nod','jump','sway','startle','tremble','ponder','breathe','stomp',
    'rush','peek','pulse','pop','offer','lean','droop','dance',
}

@dataclass(frozen=True)
class Job:
    number: int
    entry: dict
    atlas: str
    grid: tuple
    ink: str
    tint: str
    folder: str
    font: str
    font_index: int

def pulse(t, at, width):
    return exp(-((t-at)/width)**2)

def motion(kind, t):
    wave = sin(2*pi*t)
    shake = sin(8*pi*t)
    hit = pulse(t,.34,.13)
    if kind == 'nod':
        return 0, 4*hit, 4*hit, 1.5*wave
    if kind == 'jump':
        return 0, -13*hit+4*pulse(t,.14,.08), -3*hit+4*pulse(t,.14,.08), 2*wave
    if kind == 'sway':
        return 3*wave, 0, cos(2*pi*t), 6*wave
    if kind == 'startle':
        return 2*wave, -11*pulse(t,.27,.09)+3*pulse(t,.43,.09), -3*hit, -5*hit+2*wave
    if kind == 'tremble':
        return 3*shake, 1.6*cos(8*pi*t), 2*shake, 2*cos(8*pi*t)
    if kind == 'ponder':
        return wave, 0, wave, 8*pulse(t,.51,.21)
    if kind == 'breathe':
        return 0, 1.8*wave, 3*wave, 2*wave
    if kind == 'stomp':
        return 6*shake*hit, 3*pulse(t,.46,.08), 4*pulse(t,.46,.08), -5*shake*hit
    if kind == 'rush':
        return 10*wave, -6*(.5-.5*cos(4*pi*t)), 1, 5+3*wave
    if kind == 'peek':
        return 6*wave, -2*hit, 0, -4*wave
    if kind == 'pulse':
        return 0, -4*hit, 3*cos(4*pi*t), 3*wave
    if kind == 'pop':
        return 4*hit, -6*hit, -4*hit, 4*wave
    if kind == 'offer':
        return 2*wave, -2*hit, 4*hit, -3*wave
    if kind == 'lean':
        return 4*hit, 2*hit, 1, 8*hit
    if kind == 'droop':
        return -2*wave, 5*hit, 5*hit, -5*hit
    if kind == 'dance':
        return 4*wave, -6*(.5-.5*cos(4*pi*t)), 2*cos(4*pi*t), 6*wave
    raise ValueError(f'Unknown motion {kind!r}')

def outlined(layer, radius):
    border = Image.new('RGBA',layer.size,WHITE)
    border.putalpha(layer.getchannel('A').filter(ImageFilter.MaxFilter(radius*2+1)))
    border.alpha_composite(layer)
    return border

def draw_icon(layer, name, x, y, size, color, ink):
    if size < 1:
        return
    rows=ICONS[name]
    w,h=len(rows[0])*size,len(rows)*size
    mask=Image.new('L',(w+4,h+4))
    pen=ImageDraw.Draw(mask)
    for j,row in enumerate(rows):
        for k,cell in enumerate(row):
            if cell=='#':
                pen.rectangle((2+k*size,2+j*size,1+(k+1)*size,1+(j+1)*size),fill=255)
    badge=Image.new('RGBA',mask.size,ink)
    badge.putalpha(mask.filter(ImageFilter.MaxFilter(3)))
    face=Image.new('RGBA',mask.size,color)
    face.putalpha(mask)
    badge.alpha_composite(face)
    layer.alpha_composite(badge,(round(x-badge.width/2),round(y-badge.height/2)))

def effects(layer, icon, t, tint, ink, seed):
    if icon == 'none':
        return
    polarity = 1 if seed%2 else -1
    wave = sin(2*pi*t)
    hit = pulse(t,.33,.15)
    center = 124 if polarity > 0 else 36
    other = 160-center
    if icon in {'heart','petal','bubble','note','sleep'}:
        for j in range(3):
            phase=(t+j/3)%1
            size=1+int(.12<phase<.86)+int(.44<phase<.68 and j==0)
            draw_icon(layer,icon,center+polarity*(phase*10-j*5),81-44*phase-j*5,size,tint,ink)
        draw_icon(layer,'spark',other,53+3*wave,1,tint,ink)
    elif icon == 'tear':
        for j in range(4):
            phase=(2*t+j*.23)%1
            sign=1 if j%2 else -1
            draw_icon(layer,icon,80+sign*(42+phase*10),76+phase*37+(j//2)*8,
                      1+int(.16<phase<.74),tint,ink)
    else:
        draw_icon(layer,icon,center+2*wave,38-6*hit,2+int(hit>.57),tint,ink)
        draw_icon(layer,'spark' if icon in {'check','spark','question'} else 'dots',
                  other,65+4*wave,1+int(icon=='spark' and hit>.5),tint,ink)
        pen=ImageDraw.Draw(layer)
        pen.line((other-4,82,other+2,79),fill=tint,width=2)

def crop_sprite(job):
    with Image.open(job.atlas) as image:
        atlas=image.convert('RGBA')
    cols,rows=job.grid
    col,row=job.entry['cell']
    w,h=atlas.size
    bounds=job.entry.get('crop',[col*w//cols,row*h//rows,(col+1)*w//cols,(row+1)*h//rows])
    art=atlas.crop(bounds)
    original_alpha=art.getchannel('A')
    alpha=original_alpha.point(lambda a:255 if a>=128 else 0)
    if alpha.getbbox() is None:
        raise ValueError(f'No transparent sprite in cell {job.entry["cell"]} of {job.atlas}')
    # Remove disconnected dust while retaining meaningful separate props.
    w,h=art.size
    mask=alpha.load()
    seen=bytearray(w*h)
    components=[]
    for y in range(h):
        for x in range(w):
            pos=y*w+x
            if not mask[x,y] or seen[pos]:
                continue
            seen[pos]=1
            todo=[pos]
            pixels=[]
            while todo:
                pos=todo.pop()
                pixels.append(pos)
                xx,yy=pos%w,pos//w
                for nx,ny in ((xx-1,yy),(xx+1,yy),(xx,yy-1),(xx,yy+1)):
                    if 0<=nx<w and 0<=ny<h:
                        neighbour=ny*w+nx
                        if not seen[neighbour] and mask[nx,ny]:
                            seen[neighbour]=1
                            todo.append(neighbour)
            components.append(pixels)
    threshold=max(20,min(350,w*h//300))
    keep=[component for component in components if len(component)>=threshold]
    if not keep:
        keep=[max(components,key=len)]
    clean=Image.new('L',(w,h))
    pixels=clean.load()
    for component in keep:
        for pos in component:
            pixels[pos%w,pos//w]=255
    clean=clean.filter(ImageFilter.MaxFilter(5))
    alpha=ImageChops.multiply(original_alpha,clean)
    art.putalpha(alpha)
    art=art.crop(alpha.getbbox())
    ratio=min(212/art.height,236/art.width)
    return art.resize((max(1,round(art.width*ratio)),max(1,round(art.height*ratio))),Image.Resampling.LANCZOS)

def make_caption(text, ink, font_path, font_index):
    face=Image.new('RGBA',(SIZE,SIZE))
    d=ImageDraw.Draw(face)
    text=text.translate(str.maketrans({'！':'!','？':'?','～':'~'}))
    size=43 if len(text)<=4 else 38
    font=ImageFont.truetype(font_path,size,index=font_index)
    while font.getlength(text)>275:
        size-=1
        font=ImageFont.truetype(font_path,size,index=font_index)
    d.text((160,278),text,font=font,anchor='mm',fill=ink,stroke_width=1,stroke_fill=ink)
    face.putalpha(face.getchannel('A').point(lambda a:255 if a>=112 else 0))
    return outlined(face,4)

def draw_frame(sprite, label, job, t):
    dx,dy,squash,sway=motion(job.entry['motion'],t)
    layer=Image.new('RGBA',(SIZE,SIZE))
    w,h=sprite.size
    art=sprite.resize((max(1,w+round(squash*2)),max(1,h-round(squash*2))),Image.Resampling.LANCZOS)
    x=round((SIZE-art.width)/2+dx*2)
    y=max(8,round(244-art.height+dy*2))
    for top in range(0,art.height,6):
        bottom=min(art.height,top+6)
        shear=round((1-top/art.height)**1.7*sway*2)
        layer.alpha_composite(art.crop((0,top,art.width,bottom)),(x+shear,y+top))
    accents=Image.new('RGBA',(PIXELS,PIXELS))
    effects(accents,job.entry['icon'],t,job.tint,job.ink,job.number)
    layer.alpha_composite(accents.resize((SIZE,SIZE),NEAREST))
    layer.alpha_composite(label)
    return layer

def save_gif(path, frames):
    palette_input=Image.new('RGB',(SIZE*4,SIZE*6),WHITE)
    for j,im in enumerate(frames):
        palette_input.paste(im,(SIZE*(j%4),SIZE*(j//4)),im.getchannel('A'))
    palette=palette_input.quantize(colors=250)
    indexed=[]
    for im in frames:
        matte=Image.new('RGB',im.size,WHITE)
        alpha=im.getchannel('A')
        matte.paste(im,(0,0),alpha)
        img=matte.quantize(palette=palette,dither=Image.Dither.NONE)
        img.paste(255,mask=alpha.point(lambda value:255 if value<128 else 0))
        indexed.append(img)
    indexed[0].save(path,save_all=True,append_images=indexed[1:],duration=DELAY,loop=0,
                    disposal=2,transparency=255,optimize=False)

def clean_filename(text):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', text)

def verify(path):
    frames=set()
    duration=0
    with Image.open(path) as image:
        if image.size!=(SIZE,SIZE) or image.info.get('loop')!=0:
            raise ValueError(f'Invalid size or loop flag: {path}')
        for frame in ImageSequence.Iterator(image):
            duration+=frame.info['duration']
            rendered=frame.convert('RGBA')
            alpha=rendered.getchannel('A')
            box=alpha.getbbox()
            if alpha.getextrema()!=(0,255) or box is None or not all(0<k<SIZE for k in box):
                raise ValueError(f'Invalid alpha or clipped content: {path}')
            frames.add(hashlib.sha256(rendered.tobytes()).digest())
    if duration!=TICKS*DELAY or len(frames)<4:
        raise ValueError(f'Missing or inadequate motion: {path}')
    return len(frames)

def build_one(job):
    sprite=crop_sprite(job)
    label=make_caption(job.entry['text'],job.ink,job.font,job.font_index)
    frames=[draw_frame(sprite,label,job,k/TICKS) for k in range(TICKS)]
    path=Path(job.folder)/f'{job.number:03d}-{clean_filename(job.entry["text"])}.gif'
    save_gif(path,frames)
    poses=hashlib.sha256(sprite.tobytes()).hexdigest()
    return path,poses,verify(path)

def gallery(title, groups, folder):
    text=html.escape(title)
    sections=[]
    for group,paths in groups:
        cards=[]
        for path in paths:
            src=quote(path.relative_to(folder).as_posix())
            caption=html.escape(path.stem.split('-',1)[-1])
            num=html.escape(path.stem.split('-',1)[0])
            cards.append(f'<a href="{src}"><img src="{src}" alt="{caption}"><span>{num} / {caption}</span></a>')
        name=html.escape(group['name'])
        sections.append(f'<section><h2>{name}</h2><div class="grid">{"".join(cards)}</div></section>')
    page=f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{text}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:#172c42;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}main{{max-width:1120px;margin:auto;padding:48px 26px 90px}}header{{border-top:4px solid #24949a;padding-top:25px;margin-bottom:40px}}small{{font-size:12px;letter-spacing:.18em;color:#24868d;font-weight:700}}h1{{font-size:clamp(34px,7vw,64px);margin:12px 0}}p{{color:#506a7a;line-height:1.7}}h2{{font-size:20px;margin:32px 0 16px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}}a{{display:grid;text-decoration:none;background:#f7fafb;color:#203645;border:1px solid #d8e5e8;border-radius:8px;overflow:hidden}}img{{width:100%;display:block}}span{{padding:13px 15px;border-top:1px solid #e0e9eb;font-size:15px}}@media(max-width:700px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style><main><header><small>STICKER COLLECTION / ANIMATED GIFS</small><h1>{text}</h1><p>点击表情可单独打开，每一张都是循环动图。</p></header>{''.join(sections)}</main></html>"""
    (folder/'动图浏览.html').write_text(page,encoding='utf-8')

def decoded_frames(path, scale):
    items=[]
    with Image.open(path) as img:
        for frame in ImageSequence.Iterator(img):
            scaled=frame.convert('RGBA').resize((scale,scale),NEAREST)
            items.extend([scaled]*(frame.info['duration']//DELAY))
    if len(items)!=TICKS:
        raise ValueError(f'Unexpected timing in {path}')
    return items

def preview(title, groups, path, font_path, font_index):
    width,height=1440,1320
    video=Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                 '-s',f'{width}x{height}','-framerate','25','-i','pipe:0','-c:v','libx264',
                 '-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],stdin=PIPE)
    title_font=ImageFont.truetype(font_path,48,index=font_index)
    small=ImageFont.truetype(font_path,21,index=font_index)
    code=ImageFont.truetype(font_path,16,index=font_index)
    try:
        with video.stdin:
            for chapter,(group,files) in enumerate(groups,1):
                for start in range(0,len(files),16):
                    chapter_files=files[start:start+16]
                    base=Image.new('RGB',(width,height),'#FFFFFF')
                    pen=ImageDraw.Draw(base)
                    pen.rectangle((64,51,1376,57),fill='#24949A')
                    pen.text((64,75),title,fill='#172C42',font=title_font)
                    pen.text((69,151),f'{group["name"]}  ·  动态预览',fill='#506A7A',font=small)
                    pen.text((1140,106),'STICKER COLLECTION',fill='#24949A',font=code)
                    anchors=[]
                    for i,item in enumerate(chapter_files):
                        x=64+(i%4)*332; y=210+(i//4)*266
                        pen.rounded_rectangle((x,y,x+316,y+248),radius=8,fill='#F7FAFB',outline='#D8E5E8',width=2)
                        pen.text((x+14,y+13),item.stem.split('-',1)[0],fill='#719198',font=code)
                        anchors.append((x+48,y+12))
                    decoded=[decoded_frames(p,220) for p in chapter_files]
                    for k in range(TICKS*2):
                        im=base.copy()
                        for timeline,xy in zip(decoded,anchors):
                            tile=timeline[k%TICKS]
                            im.paste(tile,xy,tile.getchannel('A'))
                        raw=im.tobytes()
                        video.stdin.write(raw)
                        video.stdin.write(raw)
    finally:
        status=video.wait()
        if status:
            raise RuntimeError(f'FFmpeg returned {status}')

def export(args):
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    count=manifest['count']
    groups=[]
    jobs=[]
    all_text=set()
    seen_cells=set()
    args.output.mkdir(parents=True,exist_ok=True)
    folder=args.output/'GIF合集'
    folder.mkdir()
    for idx,group in enumerate(manifest['groups'],1):
        group_dir=folder/f'{idx:02d}-{clean_filename(group["name"])}'
        group_dir.mkdir()
        first=len(jobs)
        atlas=str((args.manifest.parent/group['atlas']).resolve())
        cols,rows=group['grid']
        for entry in group['entries']:
            txt=entry['text'].strip()
            cell=tuple(entry['cell'])
            assert len(cell)==2 and 0<=cell[0]<cols and 0<=cell[1]<rows
            assert txt and txt not in all_text, f'Duplicate or empty text: {txt}'
            assert (atlas,cell) not in seen_cells, f'Duplicate atlas cell: {atlas} {cell}'
            assert entry['motion'] in MOTIONS and entry['icon'] in {*ICONS,'none'}
            all_text.add(txt)
            seen_cells.add((atlas,cell))
            jobs.append(Job(len(jobs)+1,entry,atlas,(cols,rows),group['ink'],group['tint'],
                            str(group_dir),args.font,args.font_index))
        groups.append((group,slice(first,len(jobs))))
    assert len(jobs)==count and jobs
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        results=list(executor.map(build_one,jobs))
    paths=[item[0] for item in results]
    assert len(set(item[1] for item in results))==count,'Duplicate visual poses'
    visible_groups=[(group,paths[span]) for group,span in groups]
    gallery(manifest['title'],visible_groups,folder)
    bundle=args.output/f'{clean_filename(manifest["title"])}-{count}张GIF.zip'
    with ZipFile(bundle,'w',ZIP_DEFLATED) as z:
        for path in [*paths,folder/'动图浏览.html']:
            z.write(path,path.relative_to(folder).as_posix())
    with ZipFile(bundle) as z:
        assert z.testzip() is None
        assert len([n for n in z.namelist() if n.endswith('.gif')])==count
        for path in paths:
            assert z.read(path.relative_to(folder).as_posix())==path.read_bytes()
    if args.preview:
        preview(manifest['title'],visible_groups,args.output/'动态预览.mp4',args.font,args.font_index)
    print(json.dumps({'gif_count':count,'unique_art':count,'unique_frame_min':min(r[2] for r in results),
                      'zip':str(bundle),'preview':args.preview},ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('output',type=Path,help='Empty working destination')
    parser.add_argument('--font',required=True,help='Local font file covering all caption glyphs')
    parser.add_argument('--font-index',type=int,default=0)
    parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--preview',action='store_true',help='Build a chaptered MP4 from actual decoded GIF frames')
    export(parser.parse_args())

if __name__=='__main__':
    main()

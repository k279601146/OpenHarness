#!/usr/bin/env python3
"""Export actual animation keyframes from sprite sheets; see frame-manifest.md."""
import argparse
import html
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image, ImageDraw, ImageFont, ImageSequence

SIZE = 320

def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', s)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path, help='New output directory')
    parser.add_argument('--font', required=True)
    parser.add_argument('--pixel-art', action='store_true', help='Use nearest-neighbor resizing for pixel-style frames')
    args = parser.parse_args()
    m = json.loads(args.manifest.read_text(encoding='utf-8'))
    entries = m['entries']
    if not entries or len({e['text'] for e in entries}) != len(entries):
        raise ValueError('Entries must be nonempty and captions unique')
    args.output.mkdir(parents=True, exist_ok=False)
    gifs = args.output / 'GIF'; gifs.mkdir()
    font = ImageFont.truetype(args.font, 34)
    paths = []
    for n, e in enumerate(entries, 1):
        sheet = Image.open(args.manifest.parent / e['sheet']).convert('RGBA')
        cols, rows = e['grid']
        order = e['frames']; durations = e['durations_ms']
        if len(order) < 2 or len(order) != len(durations) or min(durations) < 10:
            raise ValueError('Each frame requires a duration >= 10ms')
        images = []
        for col, row in order:
            if not (0 <= col < cols and 0 <= row < rows):
                raise ValueError('Frame cell out of range')
            box = (round(col*sheet.width/cols), round(row*sheet.height/rows), round((col+1)*sheet.width/cols), round((row+1)*sheet.height/rows))
            tile = sheet.crop(box)
            tile.thumbnail((300, 270), Image.Resampling.NEAREST if args.pixel_art else Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (SIZE,SIZE), (255,255,255,0) if m.get('transparent',False) else 'white')
            canvas.alpha_composite(tile, ((SIZE-tile.width)//2, 0))
            draw = ImageDraw.Draw(canvas)
            draw.text((SIZE//2,276), e['text'], font=font, fill='#30415B', anchor='mt', stroke_width=0)
            images.append(canvas)
        if len({i.tobytes() for i in images}) < 2:
            raise ValueError('No distinct images: ' + e['text'])
        path = gifs / f'{n:02d}-{safe_name(e["text"])}.gif'
        # Shared palette on a white matte; transparency index reserved for alpha<128.
        palette_img = Image.new('RGB', (SIZE*len(images),SIZE), 'white')
        for j, im in enumerate(images): palette_img.paste(im, (SIZE*j,0), im.getchannel('A'))
        palette = palette_img.quantize(colors=255)
        indexed = []
        for im in images:
            matte = Image.new('RGB', im.size, 'white'); matte.paste(im, mask=im.getchannel('A'))
            ind = matte.quantize(palette=palette, dither=Image.Dither.NONE)
            if m.get('transparent',False): ind.paste(255, mask=im.getchannel('A').point(lambda a: 255 if a < 128 else 0))
            indexed.append(ind)
        kw = dict(save_all=True, append_images=indexed[1:], duration=durations, loop=0, disposal=2, optimize=False)
        if m.get('transparent',False): kw['transparency']=255
        indexed[0].save(path, **kw)
        with Image.open(path) as check:
            if check.n_frames < 2 or check.size != (SIZE,SIZE): raise ValueError('Invalid output: '+str(path))
        paths.append(path)
    cards=''.join(f'<figure><img src="GIF/{html.escape(p.name,quote=True)}" alt="{html.escape(entries[i]["text"],quote=True)}"><figcaption>{i+1:02d}</figcaption></figure>' for i,p in enumerate(paths))
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>动态表情预览</title><style>body{font-family:system-ui;background:#f6f8fa;margin:0;padding:32px;color:#30415b}main{max-width:1100px;margin:auto}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}figure{margin:0;background:white;border-radius:12px;overflow:hidden;position:relative}img{width:100%;display:block}figcaption{position:absolute;top:10px;left:12px;color:#789;font-size:12px}@media(max-width:650px){.grid{grid-template-columns:repeat(2,1fr)}}</style><main><h1>动态 IP 表情预览</h1><p>点击或保存单张 GIF；动作由角色连续画面构成。</p><div class="grid">'+cards+'</div></main></html>'
    (args.output/'整体预览.html').write_text(page,encoding='utf-8')
    with ZipFile(args.output/'动态表情合集.zip','w',ZIP_DEFLATED) as z:
        for p in paths: z.write(p, p.relative_to(args.output))
        z.write(args.output/'整体预览.html', '整体预览.html')
    with ZipFile(args.output/'动态表情合集.zip') as z:
        if z.testzip() is not None: raise ValueError('Invalid ZIP')
    print(json.dumps({'count':len(paths),'output':str(args.output.resolve())},ensure_ascii=False))

if __name__=='__main__': main()

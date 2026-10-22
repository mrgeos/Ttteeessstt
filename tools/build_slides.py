#!/usr/bin/env python3
"""Build slide images and zoom tiles from PDF pages.

  python3 tools/build_slides.py slide NN file.pdf [page]   render one slide
  python3 tools/build_slides.py manifest                  rewrite the slide list in index.html

A slide is rendered once at ZOOM_DPI and resized into:
  slides/NN-{1280,2048,3200,thumb}.webp   plain images (3200 = level 0)
  slides/NN/{1,2}/C_R.webp                512 px tiles for zoom levels 1 (2x) and 2 (3x)
  slides/NN/info.json                     sizes and a content hash used for cache busting
Run `manifest` after adding, removing or replacing slides.
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLIDES = os.path.join(ROOT, 'slides')
ZOOM_DPI = 138          # level 2; level 1 is 2/3 of it, level 0 is 1/3
TILE = 512


def webp(img, path, q=80):
    img.save(path, 'WEBP', quality=q, method=4)


def render(pdf, page, nn):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'p')
        subprocess.run(['pdftoppm', '-r', str(ZOOM_DPI), '-f', str(page), '-l', str(page),
                        '-png', '-singlefile', pdf, out], check=True)
        big = Image.open(out + '.png').convert('RGB')
    W, H = big.size
    # Make every level an exact multiple of level 0 so tiles line up with the plain image.
    bw, bh = round(W / 3), round(H / 3)
    if (W, H) != (3 * bw, 3 * bh):
        big = big.resize((3 * bw, 3 * bh), Image.LANCZOS)
    size = lambda k: (bw * k, bh * k)
    base = big.resize(size(1), Image.LANCZOS)
    webp(base, f'{SLIDES}/{nn}-3200.webp', 82)
    for w in (2048, 1280):
        webp(base.resize((w, round(base.height * w / base.width)), Image.LANCZOS), f'{SLIDES}/{nn}-{w}.webp')
    webp(base.resize((360, round(base.height * 360 / base.width)), Image.LANCZOS), f'{SLIDES}/{nn}-thumb.webp', 70)

    d = os.path.join(SLIDES, nn)
    shutil.rmtree(d, ignore_errors=True)
    levels = []
    for lvl, k in ((1, 2), (2, 3)):
        img = big if k == 3 else big.resize(size(k), Image.LANCZOS)
        lw, lh = img.size
        os.makedirs(f'{d}/{lvl}')
        # Tiles overlap their right / bottom neighbour by 1 px so no seam shows when scaled.
        for r in range(0, (lh + TILE - 1) // TILE):
            for c in range(0, (lw + TILE - 1) // TILE):
                x, y = c * TILE, r * TILE
                webp(img.crop((x, y, min(x + TILE + 1, lw), min(y + TILE + 1, lh))), f'{d}/{lvl}/{c}_{r}.webp', 78)
        levels.append([lw, lh])
    info = {'w': base.width, 'h': base.height, 'levels': levels,
            'v': hashlib.md5(big.resize((320, round(320 * H / W))).tobytes()).hexdigest()[:8]}
    with open(f'{d}/info.json', 'w') as f:
        json.dump(info, f)
    print(nn, info)


def manifest():
    nums = sorted(n for n in os.listdir(SLIDES) if re.fullmatch(r'\d\d', n))
    rows = []
    for i, n in enumerate(nums):
        assert n == f'{i + 1:02d}', f'slide numbers must be consecutive, got {n}'
        with open(f'{SLIDES}/{n}/info.json') as f:
            rows.append(json.load(f))
    body = '[\n' + ',\n'.join('    ' + json.dumps(r, separators=(',', ':')) for r in rows) + '\n  ]'
    path = os.path.join(ROOT, 'index.html')
    html = open(path, encoding='utf-8').read()
    html, n = re.subn(r'/\*SLIDES\*/.*?/\*/SLIDES\*/', lambda m: f'/*SLIDES*/{body}/*/SLIDES*/', html, flags=re.S)
    assert n == 1, 'slide list markers not found in index.html'
    html = re.sub(r'(<span class="count" id="count"[^>]*>)1 / \d+', rf'\g<1>1 / {len(rows)}', html)
    open(path, 'w', encoding='utf-8').write(html)
    print(f'{len(rows)} slides written to index.html')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['slide'] and len(a) in (3, 4):
        render(a[2], int(a[3]) if len(a) == 4 else 1, f'{int(a[1]):02d}')
    elif a == ['manifest']:
        manifest()
    else:
        sys.exit(__doc__)

#!/usr/bin/env python3
"""Generate artificial illustration photos for offline testing, not semantic AI training."""
from pathlib import Path
from PIL import Image, ImageDraw

out=Path('demo_images');out.mkdir(exist_ok=True)
for name,shift in [('disque_rouge_1.jpg',0),('disque_rouge_2.jpg',3),('carre_bleu.jpg',0)]:
    im=Image.new('RGB',(640,420),'#eee9df');d=ImageDraw.Draw(im)
    if name.startswith('disque'):
        d.ellipse((230+shift,110,410+shift,290),fill='#cf3639',outline='#9f2429',width=5)
    else:
        d.rectangle((230,110,410,290),fill='#296fb8',outline='#174273',width=5)
    im.save(out/name,quality=90)
    print(out/name)

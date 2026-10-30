"""Generate the simple native application icon; requires Pillow only at build time."""
from pathlib import Path
from PIL import Image, ImageDraw

folder = Path(__file__).parent / 'assets'
folder.mkdir(exist_ok=True)
im = Image.new('RGBA', (256, 256))
d = ImageDraw.Draw(im)
d.rounded_rectangle((8, 8, 248, 248), radius=52, fill='#142b43')
d.rounded_rectangle((60, 36, 184, 218), radius=16, fill='#eaf3fa')
d.polygon([(148, 36), (184, 72), (148, 72)], fill='#9abbd4')
d.line((82, 92, 142, 92), fill='#92b0c7', width=10)
d.line((82, 114, 132, 114), fill='#92b0c7', width=10)
d.arc((123, 108, 205, 186), 165, 305, fill='#21c9b7', width=14)
d.rounded_rectangle((111, 158, 206, 222), radius=13, fill='#0d9e93')
d.ellipse((152, 178, 166, 192), fill='white')
d.rectangle((157, 188, 161, 203), fill='white')
im.save(folder / 'app.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
im.save(folder / 'app.png')

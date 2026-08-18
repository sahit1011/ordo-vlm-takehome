"""Render a synthetic dev eval set with exact auto-generated ground truth.

NOT the assignment eval set (that must be the user's own photos) — this is a
provably-unseen, difficulty-controlled set for pipeline development and ladder
mechanics. Categories mirror the assignment's list.

Usage: python3 harness/make_dev_set.py [seed]
Writes eval/dev_photos/*.jpg and eval/dev_ground_truth.csv
"""

import csv
import pathlib
import random
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "eval/dev_photos"
CSV = ROOT / "eval/dev_ground_truth.csv"
W, H = 1600, 1200

FONT_DIRS = ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental"]


def font(names, size):
    for n in names:
        for d in FONT_DIRS:
            for ext in (".ttf", ".ttc", ".otf"):
                p = pathlib.Path(d) / (n + ext)
                if p.exists():
                    try:
                        return ImageFont.truetype(str(p), size)
                    except OSError:
                        pass
    return ImageFont.load_default(size)


SANS = lambda s: font(["Helvetica", "Arial"], s)
SERIF = lambda s: font(["Times New Roman", "Georgia"], s)
MONO = lambda s: font(["Courier New", "Menlo"], s)
HAND = lambda s: font(["Bradley Hand Bold", "MarkerFelt", "Noteworthy", "Comic Sans MS"], s)

rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 7)

MENU_ITEMS = ["Masala Dosa", "Paneer Tikka", "Veg Biryani", "Butter Naan", "Dal Makhani",
              "Chicken 65", "Filter Coffee", "Mango Lassi", "Gobi Manchurian", "Idli Sambar"]
MEDS = [("Dolo 650", "Paracetamol 650mg", "NOV 2027"), ("Azithral 500", "Azithromycin 500mg", "MAR 2028"),
        ("Pantocid 40", "Pantoprazole 40mg", "JUL 2027"), ("Cetrizine 10", "Cetirizine 10mg", "JAN 2028")]
BOOKS = ["The Pragmatic Programmer", "Deep Learning", "Clean Code", "Thinking Fast and Slow",
         "The Design of Everyday Things", "Zero to One", "Atomic Habits"]
STREETS = ["MG Road", "Brigade Road", "Church Street", "Residency Road", "Infantry Road"]
STORES = ["Nilgiris Fresh Mart", "Ratna Stores", "Apollo Pharmacy", "Cafe Coffee Day"]


def paper(color=(248, 246, 240)):
    img = Image.new("RGB", (W, H), color)
    return img, ImageDraw.Draw(img)


def render_menu():
    img, d = paper()
    name = rng.choice(["ANNAPURNA CAFE", "HOTEL SWAGATH", "UDUPI PALACE"])
    d.text((W//2 - 260, 60), name, font=SERIF(72), fill=(40, 30, 20))
    items = rng.sample(MENU_ITEMS, 6)
    prices = [rng.randrange(40, 400, 10) for _ in items]
    y = 240
    for it, p in zip(items, prices):
        d.text((180, y), it, font=SANS(52), fill=(30, 30, 30))
        d.text((1150, y), f"Rs {p}", font=SANS(52), fill=(30, 30, 30))
        y += 110
    k = rng.randrange(6)
    return img, [(f"How much does the {items[k]} cost?", str(prices[k]), f"rs {prices[k]}|₹{prices[k]}")]


def render_receipt():
    img, d = paper((252, 252, 250))
    store = rng.choice(STORES)
    d.text((450, 60), store, font=MONO(48), fill=(20, 20, 20))
    items = rng.sample(MENU_ITEMS, 4)
    prices = [rng.randrange(20, 300) for _ in items]
    y = 200
    for it, p in zip(items, prices):
        d.text((250, y), f"{it[:18]:<20s}", font=MONO(40), fill=(30, 30, 30))
        d.text((1050, y), f"{p}.00", font=MONO(40), fill=(30, 30, 30))
        y += 80
    total = sum(prices)
    d.text((250, y + 40), "TOTAL", font=MONO(52), fill=(0, 0, 0))
    d.text((1020, y + 40), f"{total}.00", font=MONO(52), fill=(0, 0, 0))
    return img, [("What is the total on the receipt?", str(total), f"{total}.00|rs {total}")]


def render_medicine():
    img, d = paper((235, 242, 248))
    name, generic, exp = rng.choice(MEDS)
    d.rectangle([100, 100, W-100, H-100], outline=(60, 90, 160), width=6)
    d.text((200, 220), name, font=SANS(88), fill=(20, 40, 120))
    d.text((200, 400), generic, font=SANS(48), fill=(50, 50, 50))
    d.text((200, 700), f"EXP: {exp}", font=MONO(44), fill=(120, 30, 30))
    d.text((200, 800), f"10 TABLETS", font=SANS(40), fill=(50, 50, 50))
    return img, [(f"What is the expiry date on the {name}?", exp, exp.replace(" ", " 20"))]


def render_sign():
    img, d = paper((28, 60, 34))
    street = rng.choice(STREETS)
    d.rectangle([150, 400, W-150, 800], fill=(18, 90, 48), outline=(240, 240, 240), width=10)
    d.text((300, 520), street, font=SANS(110), fill=(250, 250, 250))
    dist = rng.choice([1, 2, 3, 5])
    d.text((300, 660), f"{dist} km", font=SANS(72), fill=(250, 250, 100))
    return img, [(f"How far is {street}?", f"{dist} km", f"{dist}km|{dist} kilometers")]


def render_note():
    img, d = paper((250, 248, 235))
    task = rng.choice(["Call plumber at 4pm", "Buy milk and eggs", "Dentist Tuesday 10am",
                       "Pay electricity bill", "Gym at 6:30"])
    d.text((150, 150), "Reminder:", font=HAND(80), fill=(40, 40, 90))
    d.text((150, 380), task, font=HAND(92), fill=(30, 30, 30))
    key = task.split()[-1]
    return img, [("What does the note remind me to do?", task.split(" at ")[0].lower(), key.lower())]


def render_whiteboard():
    img, d = paper((250, 250, 252))
    items = rng.sample(["ship v2 API", "fix login bug", "standup 9:30", "demo Friday",
                        "review PR 42", "deploy staging"], 3)
    d.text((120, 80), "TODO", font=HAND(90), fill=(160, 30, 30))
    y = 280
    for it in items:
        d.text((160, y), f"- {it}", font=HAND(70), fill=(30, 60, 130))
        y += 160
    return img, [("What is the first item on the whiteboard?", items[0], items[0].split()[-1])]


def render_books():
    img, d = paper((60, 45, 35))
    titles = rng.sample(BOOKS, 4)
    x = 150
    colors = [(140, 40, 40), (40, 80, 140), (40, 110, 60), (130, 100, 30)]
    for t, c in zip(titles, colors):
        d.rectangle([x, 150, x + 280, 1050], fill=c)
        tmp = Image.new("RGB", (900, 280), c)
        td = ImageDraw.Draw(tmp)
        td.text((30, 90), t[:26], font=SANS(56), fill=(240, 235, 225))
        img.paste(tmp.rotate(90, expand=True), (x, 150))
        x += 330
    return img, [("What is the title of the leftmost book?", titles[0], titles[0].split()[0])]


def render_appliance():
    img, d = paper((25, 25, 28))
    temp = rng.choice([18, 21, 23, 26])
    mode = rng.choice(["COOL", "HEAT", "AUTO"])
    d.rectangle([350, 300, 1250, 850], fill=(10, 12, 10), outline=(80, 80, 80), width=8)
    d.text((480, 400), f"{temp}°C", font=MONO(160), fill=(90, 230, 120))
    d.text((480, 660), mode, font=MONO(80), fill=(90, 230, 120))
    return img, [("What temperature is the AC set to?", f"{temp}", f"{temp} c|{temp}°c|{temp} degrees")]


def degrade(img, level):
    """easy: clean · medium: one stressor · hard: two stressors."""
    ops = []
    if level == "medium":
        ops = [rng.choice(["rotate", "blur", "dim", "noiseq"])]
    elif level == "hard":
        ops = rng.sample(["rotate_hard", "blur_hard", "dim_hard", "glare", "occlude"], 2)
    for op in ops:
        if op == "rotate":
            img = img.rotate(rng.uniform(8, 14), expand=True, fillcolor=(90, 90, 90))
        elif op == "rotate_hard":
            img = img.rotate(rng.uniform(20, 30), expand=True, fillcolor=(70, 70, 70))
        elif op == "blur":
            img = img.filter(ImageFilter.GaussianBlur(1.4))
        elif op == "blur_hard":
            img = img.filter(ImageFilter.GaussianBlur(2.6))
        elif op == "dim":
            img = ImageEnhance.Brightness(img).enhance(0.5)
        elif op == "dim_hard":
            img = ImageEnhance.Brightness(img).enhance(0.32)
            img = ImageEnhance.Contrast(img).enhance(0.8)
        elif op == "glare":
            glare = Image.new("L", img.size, 0)
            gd = ImageDraw.Draw(glare)
            cx, cy = rng.randrange(img.width), rng.randrange(img.height // 2)
            for r in range(500, 0, -12):
                gd.ellipse([cx-r, cy-r, cx+r, cy+r], fill=int(200 * (1 - r/500)))
            img = Image.composite(Image.new("RGB", img.size, (255, 255, 253)), img, glare)
        elif op == "occlude":
            od = ImageDraw.Draw(img)
            ow, oh = img.width // 5, img.height // 4
            ox, oy = rng.randrange(img.width - ow), rng.randrange(img.height - oh)
            od.rectangle([ox, oy, ox+ow, oy+oh], fill=(35, 30, 28))
    return img


RENDERERS = [("menu", render_menu, 4), ("receipt", render_receipt, 4),
             ("medicine", render_medicine, 3), ("street-sign", render_sign, 3),
             ("handwritten", render_note, 3), ("whiteboard", render_whiteboard, 2),
             ("book-spines", render_books, 2), ("appliance", render_appliance, 3)]
# global 8-cycle → 9 easy / 9 medium / 6 hard over 24 images ≈ 38/38/25
LEVELS = ["easy", "medium", "hard", "easy", "medium", "easy", "hard", "medium"]


TRAIN_POOLS = {
    # disjoint content for LoRA training — nothing shared with the dev set
    "MENU_ITEMS": ["Chole Bhature", "Egg Curry", "Tomato Soup", "Veg Pulao", "Fish Fry",
                   "Masala Chai", "Badam Milk", "Onion Pakoda", "Curd Rice", "Mutton Korma"],
    "MEDS": [("Crocin 500", "Paracetamol 500mg", "SEP 2027"), ("Allegra 120", "Fexofenadine 120mg", "MAY 2028"),
             ("Omez 20", "Omeprazole 20mg", "DEC 2027"), ("Zincovit", "Multivitamin+Zinc", "FEB 2028")],
    "BOOKS": ["Sapiens", "The Lean Startup", "Educated", "Project Hail Mary",
              "The Psychology of Money", "Ikigai", "Deep Work"],
    "STREETS": ["Anna Salai", "Linking Road", "Park Street", "FC Road", "Baner Road"],
    "STORES": ["More Supermarket", "MedPlus", "Chai Point", "Big Bazaar"],
}


def main():
    global OUT, CSV
    if "--train" in sys.argv:
        # swap in disjoint pools and write to the training location
        g = globals()
        for k, v in TRAIN_POOLS.items():
            g[k][:] = v if isinstance(g[k], list) else v
        OUT = ROOT / "eval/train_synth"
        CSV = ROOT / "eval/train_synth_gt.csv"
        for i, (cat, fn, count) in enumerate(RENDERERS):
            RENDERERS[i] = (cat, fn, count * 8)   # ~192 training images
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    i = 0
    for cat, fn, count in RENDERERS:
        for j in range(count):
            level = LEVELS[i % len(LEVELS)]
            img, qas = fn()
            img = degrade(img, level)
            name = f"d{i:02d}_{cat}_{level}.jpg"
            img.convert("RGB").save(OUT / name, quality=90)
            for q, a, acc in qas:
                rows.append({"id": f"d{i:02d}", "file": f"dev_photos/{name}", "category": cat,
                             "difficulty": level, "conditions": "synthetic",
                             "question": q, "answer": a, "accept_also": acc, "notes": "dev-set"})
            i += 1
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["difficulty"]] = counts.get(r["difficulty"], 0) + 1
    print(f"wrote {i} images, {len(rows)} QA rows -> {CSV}")
    print("difficulty spread:", counts)


if __name__ == "__main__":
    main()

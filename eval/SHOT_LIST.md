# Eval photo shot list — 32 photos

**You must take every photo yourself, on your own phone.** No downloads, no
public images — the whole point is the model has never seen these.

## Capture protocol (applies to every photo)

- Shoot from **ear height**, phone held roughly where an ear-worn camera would
  sit. Don't crouch or lean in to frame nicely — Ordo's camera can't.
- Main 1x lens only. No zoom, no macro mode, no editing, no HDR toggling.
- **One take per item.** If it comes out blurry, that's data — keep it
  (unless the target is 100% unreadable to *you* — then one retake, note it).
- Keep original resolution. Transfer without recompression (AirDrop-equivalent
  / USB / Google Drive "original quality").

## The grid — 32 photos across 9 categories

| # | Category | Count | Easy | Medium | Hard |
|---|----------|-------|------|--------|------|
| 1 | Restaurant menu | 4 | 1 | 2 | 1 |
| 2 | Product label (food/cosmetic) | 4 | 2 | 1 | 1 |
| 3 | Street sign / shop board | 4 | 2 | 1 | 1 |
| 4 | Handwritten note | 4 | 1 | 2 | 1 |
| 5 | Receipt | 4 | 1 | 1 | 2 |
| 6 | Medicine packaging | 3 | 1 | 1 | 1 |
| 7 | Book spine(s) on shelf | 3 | 1 | 1 | 1 |
| 8 | Whiteboard | 3 | 1 | 1 | 1 |
| 9 | Appliance display (microwave, AC remote, washing machine, router) | 3 | 1 | 1 | 1 |
|   | **Total** | **32** | **13** | **11** | **8** |

## What makes a photo easy / medium / hard

- **Easy**: daylight or good indoor light, roughly straight-on, target text
  fills a decent part of the frame, printed text.
- **Medium**: one complicating factor — e.g. dim indoor light, OR ~30° angle,
  OR the text is small in frame (shot from normal conversation distance).
- **Hard**: two or more factors, or one severe factor. Distribute these
  across the hard slots so each stressor appears at least once:
  - [ ] low light / night (no flash)
  - [ ] sharp angle, 45°+ off-axis
  - [ ] glare or reflection on the surface (glossy menu, glass, foil)
  - [ ] small text at distance (sign across the street, price tag from 2 m)
  - [ ] partial occlusion (hand/object covering part of the text)
  - [ ] crumpled or curved surface (receipt, wrapped label)

## Question + ground truth

For each photo, fill one row in `eval/ground_truth.csv`. Rules:

- The **question is what you'd actually say out loud** ("how much is the
  paneer tikka?", "what's the expiry date on this?"), not an OCR command.
- The **answer must be short and objective** — a price, a name, a date, a
  time, a word. If two people could reasonably disagree, pick a different
  question about the same photo.
- `accept_also`: alternative phrasings that should count as correct,
  separated by `|` (e.g. `280|rs 280|₹280`).

## LoRA training set — 50+ photos, shot separately

Same 9 categories, same protocol, but **completely different scenes, objects,
places, and documents** — nothing that appears in the eval 32 may appear here.
These go in `eval/train_photos/`. Speed over care: burst through them, no
difficulty bookkeeping needed. I'll draft question/answer pairs for them
automatically for you to spot-check.

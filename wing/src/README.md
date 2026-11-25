# wing/src — creative sources

Generators for the SEASON 01 creatives. Everything in `wing/` outside this folder
is produced from here, so the PNGs can always be rebuilt.

| file | what it makes |
|---|---|
| `av.py` | the illustrated guest portraits (SVG, 6 hairstyles x 4 tones) |
| `gen.py` | session data (ACTS) + builds `../season01.html` from `season-tpl.html` |
| `season-tpl.html` | the lineup page template (`{{ARC}}` / `{{WEB}}` placeholders) |
| `arc.svg` | the flight-arc graphic (peak = the June expedition) |
| `carousel.py` | builds `carousel.html`, the 7 Instagram slides at 1080x1350 |
| `poster.html` | the single 4:5 poster, exported as `../WING_SEASON01.png` |

## Rebuild

```sh
python3 gen.py        # lineup page
python3 carousel.py   # carousel.html
```

Then screenshot each `#s1`..`#s7` (carousel) or `#poster` with Playwright at
`deviceScaleFactor: 2` to get 2160x2700 PNGs.

Guest portraits are placeholders. To drop in a real photo, replace the `<svg>`
inside `<span class="ph">` with `<img src="...">`; the CSS applies grayscale and
a contrast bump so headshots shot under different conditions still look like a set.

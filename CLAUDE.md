# coldstart-sky-site

Static site, no build step. Publish dir is `site/` (Netlify). Dev server: `npx serve site`.

## The concept

"A journey with AI." The visitor flies through a futuristic stratosphere; content modules approach from the distance and zoom past as they scroll. Home (`site/index.html`) = day flight, broad audience. `/finance/` = night flight, same engine, for hedge funds / family offices / PE.

## Architecture

- `site/js/journey.js` — the scroll-flight engine. Fixed `.stage` (camera) + tall `.journey-track` for scroll distance, one GSAP timeline scrubbed by ScrollTrigger. **No pinning** (pin + Lenis janks). Modules get approach (35%) → dwell (40%, reading window) → depart (25%) beats. Exit z is 850, clamped below the 1200px perspective — never let anything cross the camera plane (Safari flickers).
- Modules are `<section class="module" data-module>` inside `.scene`, read in DOM order. **Adding a module = adding HTML; never edit journey.js for content.** Optional attrs: `data-chapter="Name"` (creates an altimeter tick), `data-x`/`data-y` (lateral offset in vw/vh), `data-flare` (triggers the sun-flare moment), `data-module="hero"` (starts on screen, no card chrome).
- Page config lives on `<body>`: `data-theme` (day|night), `data-sky` (JSON band list with `until` progress fractions), `data-peak-alt`.
- `site/css/tokens.css` — all palette/type tokens; night theme = `[data-theme="night"]` overrides. Theme changes happen here, not in journey.css.
- Mobile + `prefers-reduced-motion` = static branch (`html.is-static`): gradient sky, stacked modules, videos never load. Handled by `gsap.matchMedia` in journey.js + overrides at the bottom of journey.css.

## Copy

`copy/positioning.md` is the flight plan; `copy/home-modules.md` and `copy/finance-modules.md` hold module copy. **Hard limits: heading ≤6 words, body ≤40 words, ≤3 arrow bullets** — these fit the dwell window; longer copy is unreadable mid-flight. Voice rules: contractions, arrow bullets, no leverage/streamline/optimize/etc.

## Sky assets

6 video loops + 6 stills (day-1..3, night-1..3) in `site/assets/sky/`. Generated via KIE.AI (`KIE_AI_API_KEY` in `.env`): Nano Banana 2 ref image → Seedance 2 video. Pipeline:

```
python3 scripts/generate-sky.py            # reads scripts/sky-manifest.json, idempotent, skips existing raws
./scripts/process-video.sh                 # ffmpeg: crossfade-loop, mp4+webm encode, poster extract
```

Budgets: mp4 ≤2.5MB, webm ≤1.6MB, poster ≤80KB. To redo one band: delete its file in `assets-src/raw/`, tweak its manifest prompt, rerun. Versioned filenames on regen (assets are cached immutable).

## Deploy

Any static host works; `netlify.toml` sets the publish dir to `site/` and long-cache headers for `/assets/*`. The contact form uses Netlify Forms (`data-netlify="true"`); on another host, point the form at your own endpoint.

# ColdStart: scroll-flight landing page (day + night)

![tests](https://github.com/ChuchoMonster/coldstart-sky-site/actions/workflows/tests.yml/badge.svg)

A static, scroll-driven landing page for ColdStart, a small AI-systems consultancy. As you scroll, the camera "flies" up through the sky and content cards approach from the distance, hold long enough to read, then pass the camera. Two versions share one engine:

- `site/index.html`: day flight (general audience)
- `site/finance/index.html`: night flight (funds, family offices, PE)

No framework and no build step: plain HTML/CSS/JS, GSAP + ScrollTrigger, and Lenis for smooth scrolling.

## How it works

- **`site/js/journey.js`**: the scroll engine (~250 lines). A fixed `.stage` acts as the camera, and a tall `.journey-track` provides scroll distance. One GSAP timeline, scrubbed by ScrollTrigger, moves each `<section data-module>` along the z-axis in three beats: approach (35%), dwell (40%, the reading window) and depart (25%). There is no pinning, because pin + Lenis causes judder. Exit depth is clamped below the 1200px perspective so nothing crosses the camera plane, which makes Safari flicker.
- **Content is just HTML.** To add a module, add a `<section>`; the engine reads modules in DOM order. Optional attributes: `data-chapter` (adds an altimeter tick), `data-x`/`data-y` (lateral offset), `data-flare` (sun-flare moment), `data-module="hero"`.
- **Page config lives on `<body>`**: `data-theme` (day|night), `data-sky` (JSON list of sky bands with the scroll fraction each one ends at), `data-peak-alt`.
- **Theming**: `site/css/tokens.css`; night is a `[data-theme="night"]` override.
- **Fallback**: on mobile and with `prefers-reduced-motion`, the page switches to a static layout (gradient sky, stacked cards) and the videos never load.

## Sky video pipeline

The six sky loops (`site/assets/sky/day-1..3`, `night-1..3`) were produced by two scripts:

1. **`scripts/generate-sky.py`** reads `scripts/sky-manifest.json` (one image prompt + one video prompt per band). For each band it asks kie.ai's Nano Banana 2 model for a reference still, then passes that still to Seedance 2 to make a 10-second 1080p video. It skips any band whose raw video already exists in `assets-src/raw/`, so it only spends credits on what's missing. To redo one band, delete its raw file, edit its prompt and rerun.
2. **`scripts/process-video.sh`** (ffmpeg) turns each 10s clip into a seamless ~8.5s loop by crossfading the last 1.5s onto the start, so the last frame matches the first. It then encodes mp4 (H.264) and webm (VP9), pulls a poster frame and warns if a file is over budget (mp4 2.5MB, webm 1.6MB, poster 80KB).

Raw generations (`assets-src/raw/`) are not in this repo, but the processed loops are.

## What's AI-generated vs hand-built

- **AI-generated**: the sky stills and video loops (kie.ai: Nano Banana 2 → Seedance 2), from the prompts in `sky-manifest.json`.
- **Hand-built (with Claude Code as a pair programmer)**: the page structure, scroll engine, CSS, copy, and both pipeline scripts.
- **Third-party**: GSAP 3.13 + ScrollTrigger (GreenSock standard license), Lenis (MIT), and self-hosted Archivo, Instrument Sans and IBM Plex Mono fonts (SIL OFL), in `site/js/vendor/` and `site/assets/fonts/`.

## Run / preview

```bash
npx serve site          # or: python3 -m http.server -d site 8080
```

The page uses root-absolute paths (`/css/...`, `/assets/...`), so serve `site/` as the web root; don't open the file directly in the browser.

To regenerate sky footage (optional; costs kie.ai credits):

```bash
cp .env.example .env    # add your key
python3 scripts/generate-sky.py
./scripts/process-video.sh   # needs ffmpeg/ffprobe with libx264 + libvpx-vp9
```

## Tests

- Run `python3 -m unittest discover -s tests -v` from the repo root. Standard library only, nothing to install.
- `generate-sky.py` is tested with the kie.ai API mocked; `process-video.sh` runs against fake `ffmpeg`/`ffprobe`, so no credits are spent and no video is encoded.
- Static checks on `site/`: each page's `data-sky` config matches its sky videos, every local link and asset resolves, video files stay within budget, and module copy stays inside the word limits.
- CI runs the same command on every push and pull request (`.github/workflows/tests.yml`).

## Environment variables

| Name | Used by | Needed to view the site? |
|---|---|---|
| `KIE_AI_API_KEY` | `scripts/generate-sky.py` (read from the environment or `.env`) | No |

## Notes

- The contact form uses Netlify Forms (`data-netlify="true"`). On any other host it won't submit until you point it at your own endpoint.
- `copy/` holds the positioning and per-module copy. Module copy has hard limits (heading ≤6 words, body ≤40 words) so it can be read during the dwell window.
- `CLAUDE.md` is the project guide used with Claude Code.

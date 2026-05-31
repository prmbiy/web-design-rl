# Replicate the website design in HTML + CSS

You are given screenshots of a multi-page website. Your job is to replicate the visual design
as closely as possible in plain HTML and CSS.

## Inputs

### Screenshots — `/task/screenshots/`

One full-page PNG per page, captured at 1440px viewport width.

- `/task/screenshots/blog.png`
- `/task/screenshots/docs.png`
- `/task/screenshots/features.png`
- `/task/screenshots/home.png`
- `/task/screenshots/pricing.png`


### Screen recordings — `/task/screenrecordings/`

One mp4 per page, captured at 1440px wide. Each recording scrolls the page from top to bottom
and shows on-load animations, scroll-triggered reveals, and any looped ambient motion.

- `/task/screenrecordings/blog.mp4`
- `/task/screenrecordings/docs.mp4`
- `/task/screenrecordings/features.mp4`
- `/task/screenrecordings/home.mp4`
- `/task/screenrecordings/pricing.mp4`

`ffmpeg` and `ffprobe` are on `$PATH` if you want to extract individual frames for closer inspection.

## What to produce

Write one self-contained HTML file per page to `/app/site/`. The filenames must match the
screenshot names exactly:

- `/app/site/blog.html`
- `/app/site/docs.html`
- `/app/site/features.html`
- `/app/site/home.html`
- `/app/site/pricing.html`

Each file must be fully self-contained — all CSS inside a `<style>` tag in the same file.
Do not reference external stylesheets or local image files. Google Fonts via `@import` inside
the `<style>` tag is fine.

The recordings show the motion design. Replicate animations using CSS or vanilla JS as closely as you can.

## Rules

- Plain HTML + CSS + vanilla JS only. No React, Vue, Svelte, Tailwind, Bootstrap, or other frameworks.
- No external images or assets. If the design uses images, use CSS backgrounds, SVG shapes, or
  placeholder `<div>` blocks styled to match the visual intent.
- Match layout, colour, typography, spacing, and component structure as closely as the screenshots allow.
- Where text is too small to read in the screenshot, use plausible filler that matches the visible style.

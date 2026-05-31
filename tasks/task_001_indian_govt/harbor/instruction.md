# Replicate the website design in HTML + CSS

You are given screenshots of a multi-page website. Your job is to replicate the visual design
as closely as possible in plain HTML and CSS.

## Inputs

### Screenshots — `/task/screenshots/`

One full-page PNG per page, captured at 1440px viewport width.

- `/task/screenshots/about.png`
- `/task/screenshots/contact.png`
- `/task/screenshots/home.png`
- `/task/screenshots/schemes.png`
- `/task/screenshots/tenders.png`


## What to produce

Write one self-contained HTML file per page to `/app/site/`. The filenames must match the
screenshot names exactly:

- `/app/site/about.html`
- `/app/site/contact.html`
- `/app/site/home.html`
- `/app/site/schemes.html`
- `/app/site/tenders.html`

Each file must be fully self-contained — all CSS inside a `<style>` tag in the same file.
Do not reference external stylesheets or local image files. Google Fonts via `@import` inside
the `<style>` tag is fine.

## Rules

- Plain HTML + CSS + vanilla JS only. No React, Vue, Svelte, Tailwind, Bootstrap, or other frameworks.
- No external images or assets. If the design uses images, use CSS backgrounds, SVG shapes, or
  placeholder `<div>` blocks styled to match the visual intent.
- Match layout, colour, typography, spacing, and component structure as closely as the screenshots allow.
- Where text is too small to read in the screenshot, use plausible filler that matches the visible style.

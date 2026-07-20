# TheJenniWren — Carousel Design Rules & Production Workflow

This is the binding spec for every Instagram carousel built for this account.
Read this AND `carousel_lib.py` before building anything. Do not improvise
margins, fonts, spacing, or QC steps — follow this exactly.

---

## 0. FIRST STEPS IN A NEW CHAT

1. `view` this file.
2. `view` `carousel_lib.py` in the same project folder.
3. Import/reuse those functions rather than rewriting them from scratch.
4. Propose the narrative arc (headline + 1-line body summary per slide)
   and get approval BEFORE writing any image-generation code.
5. Run the headline pre-calculation step (`precalc_report`) on every
   proposed headline BEFORE building. Rewrite any line that limits below
   ~95pt or ~72% canvas width — never just accept a small/narrow font.
6. Build all slides.
7. `view` every single rendered slide. Check for:
   - body text clipping (an orphaned half-word or sentence cut off
     right above the footer)
   - sparse slides (big dead space between body text and footer)
   - headline lines that look narrow/weak compared to others in the set
8. Fix anything wrong with a targeted rebuild of just that slide.
9. `present_files` the full set.

Never skip step 5 (pre-calc) or step 7 (visual QC). These are the two
steps that have caused every visual bug in past sessions when skipped.

---

## 1. CANVAS

- **1080 × 1350 px** (Instagram portrait carousel). Never resize.

## 2. COLOR SYSTEM — exactly 3 colors

- Background: `#0A0A0A` (near-black)
- Text: white `#FFFFFF`
- Accent: pink `#FF0A72`

No other colors, ever. (See Change Log — `draw_check()` defaults to pink
for both check and X states rather than introducing a green/red pair,
specifically to hold this rule. Flag before deviating.)

## 3. FONTS — never substitute

- **Headlines:** Barlow Condensed ExtraBold only, ALL CAPS.
  `/home/claude/fonts/barlow/BarlowCondensed-ExtraBold.ttf`
- **Body:** Libre Baskerville Regular only.
  `/home/claude/fonts/baskerville/static/LibreBaskerville-Regular.ttf`
- **Brand signature (footer):** Libre Baskerville/Lora Italic.
  `/home/claude/fonts/baskerville/static/LibreBaskerville-Italic.ttf`
  — **falls back to Lora Italic automatically** if the Baskerville
  Italic file is missing in the environment (`carousel_lib.py`'s `lf()`
  now handles this; previously undocumented in code — see Change Log).
  Lora Italic path: `/home/claude/fonts/lora/static/Lora-Italic.ttf`
  — **confirm this exact path in the live environment**; it's a
  placeholder guess, not verified.

If fonts are missing in a new environment, locate the equivalent files
first — do not silently fall back to a different typeface, except for
the one approved italic fallback above.

## 4. MARGIN SYSTEM

- Headline left/right margin: **54px** each. Usable width = 972px.
- Body text left/right margin: **68px** each (tighter than headline
  margin is fine; body should feel slightly inset from the headline).
- Footer left inset: 54px. Bottom inset: ~60px.
- Top label pill: left inset 54px, top margin ~32px (or ~26px if `big=True`).

## 5. HEADLINE RULES

- ALL CAPS, left-aligned, Barlow ExtraBold only.
- Tight line-height: lines stack densely — never airy or floating.
  Line-advance is now metrics-based, `(ascent + descent) × 0.88`, not
  `font.size × 0.85` as in the prior library version — see Change Log
  item 1. Visually this is still "tight stacking"; the number just
  comes from font metrics instead of raw point size, for consistency
  across letterforms.
- **Every headline needs a minimum of 2 pink lines** out of however many
  lines it has. Hard requirement, not down to taste per-slide.
- Headline block should fill **84–96% of usable width** (the `fit_head`
  function in the library already encodes this — don't override it
  with a manual font size unless you have a specific overflow problem).
- `fit_head()` now ALSO caps total block height at `HEAD_MAX_H`
  (~567px, 42% of canvas) — not just line width. See Change Log item 2.
  This value is a provisional estimate, not a confirmed spec — if a
  3-line headline at max width still runs tight against the divider,
  tune `HEAD_MAX_H` in the library rather than overriding per-slide.
- **Pre-calculate before writing copy.** Use `precalc_report()` on your
  draft headline lines. Standard search range is **(100, 180)**, not
  (100, 150) — confirmed against memory; `max_sz()` in the library
  already defaults `hi=180`. If the limiting line comes back under
  ~95pt, REWRITE THE WORDS rather than accepting a small font. A
  16–30pt spread between the smallest and largest line in a headline
  is healthy; 70+ pt spread means one line is dragging the whole block
  down and needs a rewrite.
- 3 lines is the standard length for a full-size headline (100–180pt+).
  2-line headlines run larger and work well for punchy cover slides.
  Avoid 4+ line headlines — split the idea across two slides instead.
- An intentionally short, isolated punch word/phrase rendered very
  large and narrow is a DELIBERATE editorial device — not a bug to
  "fix" by padding the line out. For this case, prefer
  `draw_stat_callout()` with an explicit `stat_size`, which bypasses
  `fit_head()`'s width-fill logic entirely, rather than fighting
  `fit_head()` on a headline line it isn't suited for.

## 6. BODY TEXT RULES

- Libre Baskerville Regular. **Hard floor of 44pt is now code-enforced**
  in `draw_body()` (`BODY_MIN_SIZE = 44`) — previously just a written
  convention. Default 46-48pt.
- Line height ratio 1.32 of (ascent+descent).
- Word-wrapped to fit within 68px margins, color-segmented inline.
- Long URLs are now broken after slashes automatically before wrapping
  (`break_urls()`, called inside `wrap_lines()`) — previously the
  wrapper treated a full URL as one unbreakable token. See Change Log
  item 6.
- **The `draw_body` function silently truncates** any text that would
  render past `FOOTER_SAFE` (H-130px) — there is no error, the words
  just don't appear. This is the #1 cause of "wonky" output. ALWAYS
  view the rendered slide and confirm the last visible body line ends
  on a complete, sensible clause/sentence — not a half-cut word.
- If a slide looks sparse (body ends with a lot of dead black space
  before the footer), that's also a problem: ADD more sourced detail,
  a sharper closing line, or an extra fact. Aim for body copy that
  fills roughly 3-7 lines depending on headline size.
- One emphasized (pink) phrase or stat per 1-2 sentences is the right
  density.

## 7. STRUCTURAL CHROME (every slide)

- 9px pink top bar, 8px pink bottom bar (full width).
- Top-left: pink label pill (e.g. "BREAKING · SOURCE", "TIMELINE",
  "DOCUMENT EVIDENCE", "BY THE NUMBERS" — one label per Core Template,
  matching the sample images).
- Top-right: slide counter ("01 / 08") in white Barlow.
- Pink divider bar (6px tall, 90% width) between headline and body,
  with ~30px gap above and below it.
- Bottom-left: "TheJenniWren" in italic Baskerville/Lora.
- Bottom-right: pink triangle "next slide" arrow — present on every
  slide EXCEPT the final slide (`draw_footer(draw, arrow=False)`).

## 7A. HEADLINE STACKING + DIVIDER SYSTEM (FIXED PRODUCTION SPEC — NOT AESTHETIC JUDGMENT CALLS)

These values are encoded in `carousel_lib.py`. Do not eyeball spacing,
do not "improve" it slide-by-slide, and do not introduce new numbers
that drift from the constants below — if a number needs to change,
change it once in the library, not slide-by-slide in a build script.

**Headline line spacing**
- Line advance: `(ascent + descent) × 0.88` (metrics-based — changed
  from the prior `font.size × 0.85`, see Change Log item 1). Still
  reads as tight-stacked, one dense visual block.
- Zero paragraph spacing between lines — `draw_headline` already
  handles this.

**Pink divider (mandatory on every slide with a headline)**
- Color: `#FF0A72`, thickness `DIVIDER_H = 6px`, width `DIVIDER_W` =
  90% of canvas (972px), left-aligned with the headline block.
- Gap above the divider: `DIVIDER_GAP = 30px`.
- Gap below the divider: `BODY_GAP = 32px`.
- A slide with a full headline and no divider is incomplete — do not
  ship it.

**Vertical rhythm (top to bottom, fixed — do not improvise)**
1. Top bar / label pill
2. Label → headline gap: `HEAD_Y = 185px` from top of canvas
3. Headline block (tight-stacked, height-capped at `HEAD_MAX_H`)
4. Headline → divider gap: 30px
5. Divider (6px, 90% width)
6. Divider → body gap: 32px
7. Body text (auto-sized, truncates at `FOOTER_SAFE`, floors at 44pt)

**Width utilization**
- Headline block: 84–96% of `HEAD_MAX_W` (972px usable width) via
  `fit_head()`. Stat callouts (Big Number) use `fit_head_custom()`
  with a wider 90–98% target via `draw_stat_callout()` — different
  element, different fill target, same underlying mechanism.
- Body max width stays at 68px margins (936px usable).

## 7B. NON-TEXT TEMPLATE ELEMENTS (NEW SECTION)

The prior version of this file only documented text-based slide
elements. The Handbook v4.1's 16-template system requires several
non-text-primary templates (Big Number, Photo Story, Document
Evidence, Timeline, Scorecard, The Trick) that the old `carousel_lib.py`
had no functions for at all, despite being referenced as "already
built in past sessions" in project memory. They were not actually in
the uploaded file. The following functions were built fresh from the
sample reference images and are flagged **provisional** — visually
matched to the samples, not verified against a confirmed pixel spec
(none currently exists — see note at the top of `carousel_lib.py`).

- **`draw_stat_callout()`** — Big Number template. Huge pink digits +
  pink-pill context label beneath. Use `stat_size` explicitly for
  short values (e.g. "25") rather than letting auto-fit stretch a
  short string to fill width oddly.
- **`new_photo_story_canvas()` / `new_photo_fade_canvas()`** — Photo
  Story template. Top photo, gradient fade to black, text renders in
  the black zone. `new_photo_fade_canvas()` is the general-purpose
  version (any edge, any fade start); `new_photo_story_canvas()` is a
  pre-tuned wrapper matching the Photo Story sample specifically.
- **`draw_document_card()`** — Document Evidence template. Off-white
  card, pink highlight bar behind key line(s), optional curved arrow
  annotation. Currently a flat-color card, not a torn-paper texture
  asset — swap in a real texture PNG if Jennifer has one.
- **`draw_timeline()`** — Timeline template. Dynamic-height vertical
  timeline; each entry's height is driven by how many lines its
  description wraps to, so a longer entry naturally takes more
  vertical room without manual per-entry y-offsets.
- **`draw_check()`** — Scorecard "Delivered?" column icon (check or X).
  Defaults to pink for both states to hold the 3-color brand rule —
  flag before introducing green/red.
- **`draw_call_block()`** — full-width highlighted statement bar
  (e.g. "DISTRACT. DIVIDE. DETAIN." in The Trick; the closer bar in
  Scorecard). Dynamic height based on text wrap.

## 8. OUTPUT & DELIVERY

- Save to `/mnt/user-data/outputs/[topic]_carousel/slide_NN.png`
  (zero-padded two-digit numbers).
- View every slide individually before presenting.
- Use `present_files` with all slide paths, in order, as the final step.
- Standard carousel length: 5 (tight/hard-hitting), 7-8 (full arc), or
  9-10 (dense investigative story with many distinct facts). Match
  length to story complexity — don't pad a short story to hit a number.

## 9. VOICE & EDITORIAL RULES (carried over from prior sessions + Handbook v4.1)

- Headlines: accurate over sensational, never misleading clickbait.
- Avoid "THIS IS NOT / THIS IS" parallel negation structure.
- Avoid "is this/isn't this" rhetorical structures.
- Avoid the word "just" in headlines (and per Handbook 1A.2/1A.3, avoid
  it in all copy — this file previously scoped it to headlines only).
- Never use "GOP" — always "Republicans."
- Never use agency acronyms without plain-language identification on
  first use.
- Full names on first reference (Handbook 1.9 — not previously called
  out in this file).
- Body copy must use DIFFERENT facts/language than the headline on the
  same slide (complement, don't repeat).
- Captions must use different facts and language than the carousel
  slides themselves; sources go at the bottom of the caption.
- Pinned comments are for engagement/action prompts ONLY — no sources,
  no new facts.
- Platform-savvy spelling substitutions are intentional for algorithmic
  moderation — preserve them when given, don't "fix" them.
- Jennifer's son **had** an IEP — past tense, always.
- **Flagged conflict, not resolved silently:** the pasted "Permanent
  Project Instructions" say headlines should avoid questions. Several
  established sample slides (e.g. the Explainer "WHAT IS TEMPORARY
  PROTECTED STATUS?") use question headlines as a working pattern.
  This file does not take a position — confirm with Jennifer which
  standard governs going forward and update here once decided.

## 10. KNOWN GOOD PATTERNS FROM PAST CAROUSELS

- Pink emphasis pattern A ("bookend"): line 1 + line 3 of a 3-line
  headline in pink, line 2 white.
- Pink emphasis pattern B ("bottom-loaded"): lines 2+3 pink, line 1
  white.
- Quote slides: quote attribution label in pink, quote itself in white,
  OR open/close quote marks in pink framing white-text quote.
- Multi-source investigative arc (8-10 slides): hook → setup/context →
  name a person or mechanism → the conflict/money → the cover-up or
  evidence → bipartisan or expert reaction → bottom line/stakes → CTA.
- Personal/voice-driven carousels: consider leading with the most
  emotionally direct, first-person slide as slide 1.

---

## CHANGE LOG

- Initial version compiled from carousel production sessions, June 2026.
- Added Section 7A (Headline Stacking + Divider System) as a fixed,
  non-negotiable production spec, June 20 2026.
- **July 18 2026 — major consolidation pass** (this revision):
  1. `draw_headline()` line-advance changed from `font.size × 0.85` to
     metrics-based `(ascent + descent) × 0.88`, per cross-session
     memory flagging the old bbox/font.size approach as inconsistent
     across letterforms.
  2. `fit_head()` now checks total block height against `HEAD_MAX_H`
     in addition to line width — prevents a width-legal 3-line
     headline from crashing into the divider zone.
  3. Confirmed and documented the (100, 180) headline search range
     (was already correct in `max_sz()`, but the reference example
     in the library used a misleading (100, 130) placeholder — fixed).
  4. `BODY_MIN_SIZE = 44` is now code-enforced in `draw_body()`, not
     just a written convention.
  5. Italic font loading (`lf()`) now falls back to Lora Italic
     automatically if Baskerville Italic is missing — was previously
     undocumented in code and would have hard-crashed.
  6. Long URLs in body text are now auto-broken after slashes
     (`break_urls()`) before word-wrapping.
  7. `wrap_lines()` extracted as a standalone reusable function.
  8. `fit_head_custom()` added for non-standard width-fill targets
     (e.g. Big Number stat digits).
  9. Added Section 7B and six new functions (`draw_stat_callout`,
     `new_photo_fade_canvas`, `new_photo_story_canvas`,
     `draw_document_card`, `draw_timeline`, `draw_check`,
     `draw_call_block`) that memory referenced as already built in
     past sessions but were NOT present in the uploaded
     `carousel_lib.py`. Rebuilt from the sample reference images and
     flagged provisional — not verified against a confirmed pixel
     spec, because the uploaded Core Template Production
     Specifications v2.0 document contains no actual per-template
     engineering detail (every section is placeholder text referring
     back to "the original production specification," which was not
     included in this upload).
  10. Flagged, not resolved: a conflict between the pasted "Permanent
      Project Instructions" ("avoid questions" in headlines) and
      established sample slides that use question headlines.
  11. Corrected template numbering references in this file's language
      to match Handbook v4.1's confirmed 16-template system and the
      resolved Cover-05 = Big Number naming (previously a known
      conflict in project memory — the Core Template Production
      Specifications v2.0 doc's Template 02 entry confirms this
      mapping).

If design rules change going forward, UPDATE THIS FILE in the same
session and note the date/reason here, so the next chat inherits the
change correctly.

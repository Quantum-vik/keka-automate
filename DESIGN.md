---
name: Auto-Keka
description: A page of the printed office wall calendar, rendered as an attendance dashboard.
colors:
  paper: "#ffffff"
  board: "#f1f3f7"
  ink: "#17191f"
  ink-2: "#4f5665"
  ink-3: "#687083"
  rule: "#dde1e8"
  rule-2: "#c3c8d2"
  cell: "#e3e6ee"
  grey-soft: "#eef0f3"
  band: "#2a39a8"
  band-ink: "#ffffff"
  band-2: "rgba(255,255,255,.16)"
  blue: "#2a39a8"
  blue-soft: "#e9ecfa"
  primary: "#2a39a8"
  primary-hover: "#22308f"
  red: "#c3202b"
  red-soft: "#fcebec"
  amber: "#8f5300"
  amber-mark: "#b87700"
  amber-soft: "#fdf3e1"
  paper-dark: "#16181d"
  board-dark: "#1e2128"
  ink-dark: "#eceef3"
  ink-2-dark: "#aeb4c0"
  ink-3-dark: "#8f96a4"
  rule-dark: "#2b2f38"
  rule-2-dark: "#3d424e"
  cell-dark: "#2b2f39"
  grey-soft-dark: "#23262e"
  band-dark: "#1f2a74"
  band-2-dark: "rgba(255,255,255,.14)"
  blue-dark: "#9aa8ff"
  blue-soft-dark: "rgba(154,168,255,.13)"
  primary-dark: "#4252d6"
  primary-hover-dark: "#5162e6"
  red-dark: "#ff7279"
  red-soft-dark: "rgba(255,114,121,.13)"
  red-fill-dark: "#b3232d"
  amber-dark: "#f2b24c"
  amber-soft-dark: "rgba(242,178,76,.12)"
typography:
  display:
    fontFamily: "Bahnschrift, Avenir Next Condensed, Roboto Condensed, Nimbus Sans Narrow, Liberation Sans Narrow, Arial Narrow, DejaVu Sans Condensed, sans-serif"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Bahnschrift, Avenir Next Condensed, Roboto Condensed, Nimbus Sans Narrow, Liberation Sans Narrow, Arial Narrow, DejaVu Sans Condensed, sans-serif"
    fontSize: "34px"
    fontWeight: 700
    lineHeight: 1.1
  title:
    fontFamily: "Bahnschrift, Avenir Next Condensed, Roboto Condensed, Nimbus Sans Narrow, Liberation Sans Narrow, Arial Narrow, DejaVu Sans Condensed, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.15
    fontFeature: "tnum"
  numeral-sm:
    fontFamily: "Bahnschrift, Avenir Next Condensed, Roboto Condensed, Nimbus Sans Narrow, Liberation Sans Narrow, Arial Narrow, DejaVu Sans Condensed, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    fontFeature: "tnum"
  section:
    fontFamily: "Segoe UI Variable Text, Segoe UI, -apple-system, BlinkMacSystemFont, Adwaita Sans, Cantarell, Noto Sans, Ubuntu, Liberation Sans, sans-serif"
    fontSize: "15px"
    fontWeight: 700
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, -apple-system, BlinkMacSystemFont, Adwaita Sans, Cantarell, Noto Sans, Ubuntu, Liberation Sans, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, -apple-system, BlinkMacSystemFont, Adwaita Sans, Cantarell, Noto Sans, Ubuntu, Liberation Sans, sans-serif"
    fontSize: "13px"
    fontWeight: 600
  code:
    fontFamily: "ui-monospace, Cascadia Mono, SF Mono, DejaVu Sans Mono, monospace"
    fontSize: "12px"
    lineHeight: 1.7
rounded:
  mark: "2px"
  field: "6px"
  r: "8px"
  r-lg: "12px"
  date-ring: "23px"
spacing:
  hairline-gap: "6px"
  actions-gap: "10px"
  field-gap: "12px"
  sect: "18px"
  page-top: "20px"
  section-gap: "22px"
  gutter: "24px"
  page-bottom: "28px"
  firstrun-top: "48px"
components:
  titlebar:
    backgroundColor: "{colors.band}"
    textColor: "{colors.band-ink}"
    height: "44px"
    padding: "0 6px 0 14px"
  button-outline:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.r}"
    height: "44px"
    padding: "0 12px"
  button-outline-hover:
    backgroundColor: "{colors.board}"
  button-outline-active:
    backgroundColor: "{colors.blue-soft}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.band-ink}"
    rounded: "{rounded.r}"
    height: "40px"
    padding: "0 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-ghost:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r}"
    height: "40px"
    padding: "0 16px"
  banner:
    backgroundColor: "{colors.blue-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r}"
    padding: "10px 12px 10px 14px"
  banner-pending:
    backgroundColor: "{colors.amber-soft}"
  banner-paused:
    backgroundColor: "{colors.grey-soft}"
  banner-fail:
    backgroundColor: "{colors.red}"
    textColor: "{colors.band-ink}"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    height: "40px"
    padding: "0 11px"
  sheet:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.r-lg}"
    width: "480px"
    padding: "0 24px 18px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.r}"
    padding: "11px 16px"
  toast-error:
    backgroundColor: "{colors.red}"
    textColor: "{colors.band-ink}"
---

# Design System: Auto-Keka

## Overview

**Creative North Star: "The Office Wall Calendar"**

The dashboard is a page of the printed wall calendar every Indian workplace hangs: dates in heavy condensed black, off-days in calendar red, one printer's ultramarine band carrying the name. The ground is cool white coated paper, never cream; the ink is printing black. Sections are divided by hairline rules and spacing, not by boxes.

Density is calm and glanceable: one body size (14px) does the work, and condensed numerals carry everything a user reads at a glance (status, times, counts, dates). State is carried by form as well as hue, so the page still reads in greyscale. The world explicitly rejects the category default: identical rounded glass cards around a giant gradient timer.

The window sits open all day in WebKitGTK, which paints on the CPU. Cheap idle paint is a design constraint, not an optimization.

**Key Characteristics:**
- One ultramarine band; everything below is paper and ink.
- Heavy condensed system numerals for figures and headlines; system UI sans for words.
- Hairline rules divide; no card boxes on the dashboard.
- Solid means done, dashed means pending.
- Red only for off-days and failures; amber for pending trouble.

## Colors

Paper, black ink, and one printer's ultramarine, with calendar red and amber held back for meaning. Light and dark follow the OS (`prefers-color-scheme`); every `-dark` token is the same role on the dark page.

### Primary
- **Calendar Ultramarine** (band / blue / primary): the titlebar band, live state (state mark, worked rail, device-pass cells), today's ring in the week row, focus rings, links, and the primary save. In dark mode the band deepens (band-dark), live-state ink lifts to a light periwinkle (blue-dark) for contrast, and the filled primary brightens (primary-dark).
- **Ultramarine Wash** (blue-soft): the info banner, the OTP strip, first-run notes, field focus halo, button press.

### Secondary
- **Holiday Red** (red, red-soft): off-days in the week row, holiday time-off rows, expired sign-in, the failure banner, error toast, field errors. Filled red surfaces in dark mode use the deeper red-fill-dark so white text stays legible.

### Tertiary
- **Pending Amber** (amber for text, amber-mark for marks and fills, amber-soft for strips): overdue punch, reconnecting sign-in, device pass running low, rate-limited banner, late-day count.

### Neutral
- **Coated Paper** (paper): page, sheet, inputs, outline buttons.
- **Board** (board): hover fill, setup log well.
- **Printing Black** (ink), **Second Ink** (ink-2), **Third Ink** (ink-3): text in three steps; ink-2 carries labels, meta lines and section heads; ink-3 carries placeholders, done/dim states, and the idle state mark.
- **Hairline** (rule) and **Strong Hairline** (rule-2): section dividers; button and field strokes, the dashed rail track, scrollbar thumbs.
- **Empty Cell** (cell) and **Quiet Strip** (grey-soft): unfilled device-pass cells; the paused banner.

### Named Rules
**The One Band Rule.** Ultramarine is spent only on the band, live state, today, focus, and the primary save. Never as a section fill or decorative accent.

**The Holiday Red Rule.** Red marks off-days and failures, nothing else. Amber marks trouble that is still pending. Never use either for emphasis or decoration; the window close hover (#c42b1c) is the one desktop-convention exception.

## Typography

**Display Font:** the narrowest heavy grotesque each OS ships (Bahnschrift, Avenir Next Condensed, Roboto Condensed, Nimbus Sans Narrow, Liberation Sans Narrow, Arial Narrow, DejaVu Sans Condensed), always with `font-stretch: condensed` and tabular figures.
**Body Font:** the system UI sans (Segoe UI Variable Text, Segoe UI, -apple-system, Adwaita Sans, Cantarell, Noto Sans, Ubuntu, Liberation Sans).
**Label/Mono Font:** ui-monospace stack (Cascadia Mono, SF Mono, DejaVu Sans Mono), only for code.

**Character:** calendar numerals against plain office type. The condensed face is the voice of the page; the UI sans stays neutral and quiet. No web fonts: the file is offline.

### Hierarchy
- **Display** (700, 40px, 1.05, condensed): the status headline beside its state mark. 32px under 520px.
- **Headline** (700, 34px, 1.1, condensed): first-run screen titles (28px on phone) and the week-row date numerals (34px, 26px on phone).
- **Title** (700, 26px, 1.15, condensed): next punch, device-pass days, worked timer, countdown figure. The settings sheet title sits at 24px; the wordmark at 19px.
- **Numeral small** (700, 18px, condensed): week stats and per-day worked hours (15px on phone).
- **Section** (700, 15px, UI sans): settings section titles.
- **Body** (400, 14px, 1.45, UI sans): everything else, one size.
- **Label** (600, 13px, UI sans, ink-2): page section heads ("This week", "Activity"), field labels, the date above the status, legends, feed times.
- **Code** (12px, 1.7, mono): the setup log. License key, OTP and machine id inputs use mono at 15px (16px on phone).

### Named Rules
**The Numerals Rule.** Figures a user reads at a glance (times, counts, dates, durations, the status headline) are condensed heavy with tabular figures. Words are UI sans.

**The Mono Is Code Rule.** Monospace appears only for machine strings: setup log, license key, OTP, machine id.

## Layout

A single column of sections under the band, centered with a fluid side margin that keeps content near 820px (`max(24px, (100% - 820px)/2)`), padded 20px top and 28px bottom. Sections after the hero are separated by the section gap (22px). Order: banners, hero, three equal actions (10px gap), two columns divided by a hairline (24px gutter: next punch, device pass), the week as five calendar columns with hairline separators, then the activity feed (capped at 206px, scrolls).

The window is 860x760 by default with a 560x640 minimum; the phone remote is 390px wide.

- **Narrow window (max-width 700px):** side padding 18px, section gap 20px, column gutters 16px; two columns kept.
- **Phone (max-width 520px):** padding 16px, section gap 18px, the automation label hides to its switch, two columns stack with a hairline between, week numerals shrink, inputs go to 16px so iOS Safari does not zoom, time-off form wraps to two columns.
- **Remote (`html.remote`):** set when served to the phone. Window controls hide, and the band and every overlay pad by `env(safe-area-inset-top)`.

**The Rule-Not-Box Rule.** Divide dashboard sections with hairlines and spacing. Fills are reserved for strips that need attention (banners, OTP).

## Elevation & Depth

The page is flat. Only things that float above the page carry the single shadow token (light: `0 1px 2px rgba(20,24,40,.08), 0 12px 32px rgba(20,24,40,.16)`; dark: `0 1px 2px rgba(0,0,0,.4), 0 16px 40px rgba(0,0,0,.5)`): the settings sheet and the toast. The settings scrim is a flat `rgba(16,20,36,.45)` with no blur.

**The No-Blur Rule.** No `backdrop-filter` on any always-visible surface. WebKitGTK repaints blur on the CPU every frame.

## Shapes

Gentle, uniform corners: 8px on buttons, banners, toast, setup log and window controls; 6px on fields and small row buttons; 12px on the settings sheet. The state mark is a cap-height bar with a 2px corner, today's date is ringed by a 23px round, the automation switch is an 8px track. Strokes are 1px hairlines; icons are inline SVG line drawings (1.3 to 1.8 stroke, round caps).

**The Solid-Dashed Rule.** Done is solid, pending is dashed. The day rail is a solid bar up to now over a dashed track to clock-out; the reconnecting state mark is a dashed amber outline; a clocked-out mark is an empty outline.

## Components

### Band titlebar
- 44px ultramarine strip: calendar-check glyph and condensed wordmark (also the drag region), automation switch with label, settings glyph, then OS-neutral window controls (minimize line, maximize square, close cross as 12px line icons, 34x30 hit areas, divided by a translucent hairline). Hover fills band-2; close hover turns #c42b1c, the shared desktop close convention. Focus ring is white on the band.
- No traffic lights, no platform-specific chrome. Window controls hide in `html.remote`.

### Banners
- Full-width strips under the band, 8px corners, 600 weight, 20px line icon, optional primary action at 32px. Info and update: blue-soft. Rate-limited: amber-soft with amber icon. Paused: grey-soft with ink-2 icon. Off-day: blue-soft with red icon. Failure: solid red with white text, `role="alert"`, stays until a later punch succeeds. The failure banner is the loudest thing on the page by design.

### Hero state mark
- An 8px cap-height bar before the display headline. Live: solid ultramarine, breathing in opacity (the only infinite animation on the resting dashboard). Out: empty ink-2 outline. Reconnecting: dashed amber outline, timer dims. Overdue: solid amber, sub-line in amber naming the recovery, and the Clock out button switches to the solid primary fill (the only filled dashboard action). Expired: solid red, headline red, rail at half-opacity red.
- Beneath: the since-line, the worked timer, and the day rail (solid bar to now, dashed to clock-out, with a 12px end tick).

### Outline action buttons
- Three equal 44px buttons in a grid: 1px rule-2 stroke on paper, 600 label, 18px ultramarine line icon. Hover board, press blue-soft. Done: ink-3 text and icon, rule stroke. Working: ultramarine stroke and text with a 3px sweeping bar along the bottom; siblings drop to .45 opacity and ignore input.
- Filled primary (40px, ultramarine, white text) is for save, submit, and sign-in-again; ghost is the paper version with an inset rule-2 stroke.

### Device pass cells
- A 12px strip masked into 14 calendar cells (3px gaps), filled ultramarine left to right for days remaining. Running low: amber fill, amber figure. Expired: red-soft cells, red figure, and a full-width "Sign in again (OTP)" primary button.

### Week calendar row
- Five weekday columns under a hairline, separated by hairlines: weekday label, a 34px condensed date numeral, worked hours, in/out times or a note. Today: ultramarine 2.5px ring and label. Off-days (leave, holiday): red numeral and note. WFH note stays ink-2. Future or empty days dim to ink-3. Stats run beneath as condensed figures with plain labels.

### Feed
- Hairline-ruled rows (7px vertical padding): 52px tabular time, an 8px mark (solid ultramarine for clock-in, solid ink-2 for clock-out, outlined ink-3 otherwise), message. Empty state reads as a plain sentence in ink-3.

### Settings sheet
- A 480px paper sheet with 12px corners and the shadow token, dropped from under the band over a flat scrim. Sticky header with a 24px condensed title and a close glyph. Sections are hairline-separated (18px padding, 15px bold titles). Escape closes.

### Inputs
- 40px fields (44px in first-run), 6px corners, rule-2 stroke on paper. Focus: ultramarine stroke plus a 3px blue-soft halo. Labels are 13px 600 ink-2 above the field. Errors are 13px 600 red text below.

### First-run screens
- License gate, dependency setup, and the setup wizard are full paper pages under the band (440px column, 48px top padding). 44px ultramarine line icon, 34px condensed title, ink-2 lead. Setup shows a ring spinner and a mono log well. The wizard step indicator is three 3px top rules, ultramarine when current. The automation switch and settings glyph hide during first run.

### Toast
- Bottom-centered, ink on paper inverted, 8px corners, shadow token; rises 12px and fades in over .2s. Errors are solid red (red-fill-dark in dark mode).

### Motion
- Transitions are short and ease-out: .15s for button and fill changes, .18s for the switch knob, .2s for toast and saved tags, .4s for the worked rail.
- Infinite animations (live beat 2.4s, working sweep 1.4s, setup spinner .9s) are CSS only.

**The Idle Paint Rule.** Every infinite animation is CSS and pauses under `html.unfocused` (set on window blur); the live beat is an opacity-only pulse on the 8px mark. `prefers-reduced-motion` turns all animation and transition off.

**The Changed-DOM Rule.** The 1 s render tick writes only DOM that changed: text, HTML, and attributes are compared before writing.

## Do's and Don'ts

### Do:
- **Do** keep ultramarine to the band, live state, today, focus, and the primary save.
- **Do** carry state by form as well as hue: solid for done, dashed for pending, empty outline for out.
- **Do** set every at-a-glance figure in the condensed numeral stack with tabular figures.
- **Do** divide sections with hairline rules and spacing; reserve fills for banners and the OTP strip.
- **Do** use inline SVG line icons and OS-neutral window controls.
- **Do** write any new infinite animation in CSS so `html.unfocused` pauses it, and route new 1 s render writes through the compare-before-write helpers.

### Don't:
- **Don't** return to the old mint glass cards: no translucent tinted cards, no card grid, no gradient timer.
- **Don't** use emoji anywhere in the UI.
- **Don't** draw fake macOS traffic lights in the titlebar.
- **Don't** put `backdrop-filter` on any always-visible surface.
- **Don't** use red for anything but off-days and failures, or amber for anything but pending trouble.
- **Don't** load web fonts, CDNs, or any external file.
- **Don't** use monospace outside code strings.

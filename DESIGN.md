---
name: Tax Reconciliation
description: Invoices, bank payments and books cross-checked on a bold ruled ledger.
colors:
  ledger-ink: "#0a0a0f"
  ink-soft: "#1f2028"
  graphite-muted: "#5f6673"
  audit-blue: "#2d4bff"
  audit-blue-deep: "#1930d9"
  ledger-paper: "#eef1f7"
  sheet-white: "#ffffff"
  rule-grey: "#d4d8e0"
  night-ledger: "#0a0a10"
  night-sheet: "#15151e"
  night-card: "#1b1b26"
  night-ink-soft: "#e4e4e9"
  night-muted: "#9ca3af"
  night-blue: "#5b74ff"
  night-blue-deep: "#3a56ff"
  night-rule: "#2a2a38"
  chart-orange: "#eb6834"
  chart-quiet: "#c3c8d4"
typography:
  display:
    fontFamily: "Space Grotesk, sans-serif"
    fontSize: "clamp(3rem, 9vw, 7rem)"
    fontWeight: 700
    lineHeight: 0.95
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Space Grotesk, sans-serif"
    fontSize: "clamp(2.2rem, 5vw, 3.5rem)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Space Grotesk, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 700
    letterSpacing: "-0.01em"
  figure:
    fontFamily: "Space Grotesk, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
  body:
    fontFamily: "Inter, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Space Grotesk, sans-serif"
    fontSize: "0.72rem"
    fontWeight: 600
    letterSpacing: "1px"
  data-mono:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.95rem"
    fontWeight: 400
rounded:
  none: "0px"
spacing:
  xs: "0.4rem"
  sm: "0.8rem"
  md: "1.2rem"
  lg: "2rem"
  xl: "3rem"
components:
  button-primary:
    backgroundColor: "{colors.audit-blue}"
    textColor: "{colors.sheet-white}"
    rounded: "{rounded.none}"
    padding: "1rem 1.8rem"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.audit-blue-deep}"
  button-outline:
    backgroundColor: "{colors.sheet-white}"
    textColor: "{colors.ledger-ink}"
    rounded: "{rounded.none}"
    padding: "1rem 1.8rem"
  button-toolbar:
    backgroundColor: "{colors.sheet-white}"
    textColor: "{colors.ledger-ink}"
    rounded: "{rounded.none}"
    padding: "0.6rem 1rem"
  button-toolbar-hover:
    backgroundColor: "{colors.audit-blue}"
    textColor: "{colors.sheet-white}"
  input-field:
    backgroundColor: "{colors.ledger-paper}"
    textColor: "{colors.ledger-ink}"
    rounded: "{rounded.none}"
    padding: "0.55rem 0.7rem"
    typography: "{typography.data-mono}"
  card-sheet:
    backgroundColor: "{colors.sheet-white}"
    textColor: "{colors.ledger-ink}"
    rounded: "{rounded.none}"
    padding: "1rem 1.1rem"
  table-head:
    backgroundColor: "{colors.ledger-ink}"
    textColor: "{colors.ledger-paper}"
    padding: "0.55rem 0.7rem"
  verdict-bar:
    backgroundColor: "{colors.ledger-ink}"
    textColor: "{colors.ledger-paper}"
    padding: "0.7rem 1rem"
---

# Design System: Tax Reconciliation

## Overview

**Creative North Star: "The Audit Ledger"**

The interface is a CA's ruled working paper with the volume turned up. A faint blue graph-paper grid runs behind everything. Each record sits on its own white sheet, edged in 2px of black ink, and a hard offset shadow pins the sheet to the desk. Nothing is soft, rounded or blurred: findings have edges because they are evidence, and evidence should look like it can be put on the table.

It is **confident but exact**. The type is loud (uppercase Space Grotesk, tight tracking) and the shadows are graphic, but the system stays disciplined: one accent colour, square corners everywhere, tabular numerals, one consistent border weight. Boldness carries hierarchy and proof. It never stands in for content. Dashboard density stays practical: KPI tiles, charts and tables sit close together, so a CA can scan a whole run without hunting.

There are two themes, light and dark. Dark swaps the paper for a near-black ledger and brightens the blue, but keeps the same ink-edged sheets and hard shadows.

**Key Characteristics:**
- 2px solid ink borders on every container, input and button
- Hard offset shadows with zero blur (4/6/8px), which collapse when pressed
- Square corners only (0px radius)
- One accent: Audit Blue, reserved for primary action, emphasis and the leading data series
- Uppercase Space Grotesk for headings, labels and buttons; Inter for reading text; JetBrains Mono for numeric entry and bank narrations
- A 60px blue graph-paper grid as the page ground

## Colors

Ink on ruled paper, with a single electric blue doing all the pointing.

### Primary
- **Audit Blue** (`audit-blue`): primary buttons, the accented word in headlines, feature and proof numerals, highlighted values in the example card (the wrong rate, the wrong tax), and the leading series in every chart. Hover deepens it to **Audit Blue Deep** (`audit-blue-deep`).

### Neutral
- **Ledger Ink** (`ledger-ink`): all borders, offset shadows, primary text, table header fill, the verdict bar and the footer ground. It acts as the structural colour as much as a text colour.
- **Ink Soft** (`ink-soft`): long-form body copy (hero description, feature card text).
- **Graphite Muted** (`graphite-muted`): captions, input labels, notes and KPI labels. Secondary text only, never a value. Tuned to clear 4.5:1 on Ledger Paper (5.1:1), not just on white.
- **Ledger Paper** (`ledger-paper`): page ground under the grid, input fills, and the inset "source" panels inside the example card.
- **Sheet White** (`sheet-white`): cards, tables, the top bar and chart cards. Chart cards stay Sheet White in **both** themes so the plots read like printed exhibits.
- **Rule Grey** (`rule-grey`): 1px row dividers inside tables. The only line in the system that isn't ink.

### Dark theme
Night tokens replace their light counterparts one for one: **Night Ledger** (page), **Night Sheet** (top bar), **Night Card** (cards), **Night Ink Soft**, **Night Muted**, **Night Blue** / **Night Blue Deep**, **Night Rule**. In dark mode the ink role flips to white, so borders and shadows become white edges on near-black.

### Chart palette
Charts use Audit Blue first, then a CVD-validated categorical order (`SERIES` in `app.py`): blue, **Chart Orange** (`chart-orange`), aqua `#1baf7a`, yellow `#eda100`, magenta `#e87ba4`, green `#008300`, violet `#6250d6`, red `#e34948`. Two-series comparisons (output tax vs ITC, precision vs recall) are blue against orange. "Normal" points in the anomaly scatter use **Chart Quiet** (`chart-quiet`), so flagged points carry the blue alone. Reference lines (net liability) are drawn in Ledger Ink.

**The One Voice Rule.** Audit Blue is the only accent in the UI chrome. The chart categorical palette exists only inside plots and never spills into buttons, badges or text.

**The Fixed Ink Rule.** The verdict bar and the footer are always Ledger Ink with white text, in both themes (`--fixed-ink`, `--fixed-paper`, and `--fixed-link` #5b74ff for links on ink). They never follow the theme's `--ink`, which turns white in dark mode.

**The Ink Is Structure Rule.** Every edge is Ledger Ink at 2px. Rule Grey is allowed only for row dividers inside a table that already has an ink frame.

## Typography

**Display Font:** Space Grotesk (with sans-serif)
**Body Font:** Inter (with -apple-system, Segoe UI, sans-serif)
**Label/Mono Font:** JetBrains Mono (with monospace), for numeric inputs and bank narration strings only

**Character:** Space Grotesk's squared, slightly mechanical caps give headings the feel of a stamped ledger header. Inter keeps explanatory text quiet and readable underneath.

### Hierarchy
- **Display** (700, clamp(3rem, 9vw, 7rem), 0.95): the hero title only, uppercase, second line in Audit Blue.
- **Headline** (700, clamp(2.2rem, 5vw, 3.5rem), 1): homepage section titles, uppercase, with the last word in Audit Blue.
- **Title** (700, 1.3–1.6rem): card titles, the dashboard brand ("Ledger & Reconciliation") and in-tab subheadings, uppercase.
- **Figure** (700, 1.75rem, tabular numerals): KPI values and the big amounts in example source panels.
- **Body** (400, 15px, 1.55): descriptions, notes and table cells (tables at 0.9rem). Hero copy is capped at 640px.
- **Label** (600, 0.72rem, 1–2px tracking, uppercase): KPI labels, input labels, table headers, tab and button text (buttons at 0.82–0.95rem, 700).

**The Tabular Numbers Rule.** Every rupee amount, count and percentage uses tabular numerals (`font-variant-numeric: tabular-nums`) so columns line up like a ledger.

**The Uppercase Is Structure Rule.** Uppercase belongs to headings, labels, tabs and buttons. Sentences, notes, table data and the verdict text stay in sentence case.

## Layout

Content sits in a centred 1300px column with 2rem side padding (1rem below 900px). The homepage stacks hero → "What we do" → "Live proof" → the dashboard, which starts at a full-width ink-ruled top bar (`#dashboard`) holding the brand, run parameters (invoices, error rate, seed, Run) and exports (Excel, CSV, theme toggle).

The dashboard below uses folder tabs, then auto-fitting KPI tiles (min 170px, 1rem gap), then two-up chart grids (1.2rem gap) and full-width tables. Long tables scroll inside a 560px-tall ink-framed box. At ≤900px every multi-column grid (features, proof, charts, example sources) collapses to one column.

Spacing rhythm runs 0.4 / 0.8 / 1.2 / 2 / 3rem. Groups inside a sheet are tight (0.3–0.6rem); sections are separated by 2–3rem.

## Elevation & Depth

Depth is flat-graphic, not atmospheric. Surfaces don't float on blurred shadows. They are cut-out sheets with a solid ink block offset down-right, like paper stacked on a desk. The offset is the elevation scale: 4px for working surfaces (KPI tiles, charts, scroll tables), 6px for feature and proof cards and hero buttons, 8px for the loader overlay and hover states.

### Shadow Vocabulary
- **Sheet** (`box-shadow: 4px 4px 0 var(--ink)`): KPI tiles, chart cards, scrolling tables.
- **Raised sheet** (`box-shadow: 6px 6px 0 var(--ink)`): feature cards, proof cards, hero buttons, the Send Question button.
- **Lifted** (`box-shadow: 8px 8px 0 var(--ink)` / `9px 9px`): hover state for buttons and cards, paired with `translate(-2px,-2px)` or `(-3px,-3px)`.
- **Pressed** (`box-shadow: 2px 2px 0 var(--ink)` + `translate(2px,2px)`): the active state of hero buttons.
- **Exhibit** (`box-shadow: 6px 6px 0 var(--blue)`): the example card only. The blue shadow marks the one piece of evidence the page wants read first. The loader box uses an 8px blue variant.

**The Physical Press Rule.** Interactive sheets lift up-left on hover and press down-right on click, so the shadow always grows or shrinks with the motion. Transitions run 0.12s ease on transform and box-shadow only.

**The Exhibit Rule.** A blue offset shadow belongs to exactly one featured piece of evidence per view. Everything else casts ink.

**The Settle Rule.** Motion (GSAP + ScrollTrigger) reveals sheets as if they are set down on the desk. Each sheet starts 6px up-left with its shadow 6px longer, then settles to its resting offset (0.5s, power3.out, staggered 0.06s). Sheets reveal once, as they enter the viewport. The hero title rises out of its ruled lines once on load; the verdict bar wipes in left to right after its card settles. Numbers never animate (no count-ups). Everything stays visible without JavaScript, and with reduced motion nothing moves.

## Shapes

Square corners throughout (0px). Every container, input, select, textarea and button carries the same 2px ink border. Active tabs are folder tabs: a 2px ink outline with no bottom edge, overlapping the strip's 2px bottom rule by -2px. Loader dots are small squares that pulse. The only circular forms are the donut chart and scatter markers.

## Components

### Buttons
Blunt, uppercase and physical, but sized for a working toolbar.
- **Shape:** square corners, 2px ink border.
- **Primary (Audit Blue):** white Space Grotesk 700 uppercase with 1px tracking. Hero size is 1rem × 1.8rem with a 6px ink shadow; toolbar size (Run, Search) is 0.6rem × 1rem with no shadow.
- **Outline:** Sheet White fill with ink text and the same border and shadow (hero "See accuracy").
- **Toolbar (Excel, CSV, Clear):** Sheet White, no shadow. Hover fills Audit Blue with white text.
- **Hover / Active:** hero buttons lift (-2px, shadow 8px) and press (+2px, shadow 2px). Toolbar buttons only change fill.
- **Theme toggle:** a 40px ink square with a moon / sun icon that turns blue on hover, with an `aria-label` naming the theme it switches to.
- **Icons:** inline SVG only (no emoji or Unicode glyphs), 16px, 2.2px stroke, square caps and mitred joins, coloured by `currentColor`.

### Cards / Containers
- **Corner Style:** square.
- **Background:** Sheet White (Night Card in dark).
- **Shadow Strategy:** the Sheet / Raised sheet offsets above.
- **Border:** 2px Ledger Ink.
- **Internal Padding:** 1rem–2rem (KPI tile 1rem × 1.1rem, feature card 2rem × 1.6rem).

### Inputs / Fields
- **Style:** 2px ink border, square, Ledger Paper fill. Number inputs use JetBrains Mono centred with spinners removed. Search and select use Inter.
- **Labels:** stacked above the input in uppercase Label style, Graphite Muted.
- **Focus:** every input, select and textarea switches to an Audit Blue border plus a 4px blue offset shadow. Buttons, links and tabs get a 2px Audit Blue outline at 3px offset (`:focus-visible`).

### Navigation
- **Tabs:** uppercase Space Grotesk 600 (0.9rem) on a strip with a 2px ink bottom rule (drawn as an inset shadow, so the strip can scroll sideways on narrow screens without wrapping). Hover turns the text Audit Blue. The active tab becomes a white folder tab whose bottom edge covers the rule, and carries `aria-current`.
- **Footer:** fixed Ledger Ink ground in both themes, with white uppercase links that turn `--fixed-link` blue on hover, plus a ghosted "TAX RECON" wordmark at 5% white behind them.

### Tables
- **Header:** Ledger Ink fill, paper-coloured uppercase Label text.
- **Rows:** 1px Rule Grey dividers, tabular numerals, and a 4% blue wash on hover.

### Example card (signature)
The "what the tool catches" exhibit: three inset Ledger Paper source panels (Invoice, Bank payment, Ledger entry) side by side, each headed by a blue uppercase label with the amount in Figure type. Only the value that is wrong is coloured Audit Blue (the tax charged, not the correct GST rate), with the expected value right below it. It ends in a full-width ink **verdict bar** that states the finding in plain sentence case, then a blue Exhibit shadow. This is the visual home of "every flag explains itself".

### KPI tile
A white sheet with a 4px ink shadow, an uppercase muted label and a Figure-size value. Values are formatted in Indian style (₹ L / Cr).

### Flagged table
Each flag explains itself in columns: Problem, Invoice / payment, Party, Date ("03 Apr 2025", never wraps), Expected, **Found** (Audit Blue, the value that disagrees), **₹ at stake** (right-aligned, bold Space Grotesk) and Why it was flagged. Rows are sorted by ₹ at stake, largest first.

### Ledger columns
The homepage's "What we do" is one ruled sheet split into three ledger columns by 2px ink rules (stacked rows on mobile), not three floating cards. No section numbers, and no hover lift on things that aren't clickable.

### Loader
A blurred paper veil (5px backdrop blur) behind a single white sheet with an 8px blue shadow, three pulsing blue squares, and "Running reconciliation · Checking invoices · bank · ledger".

## Do's and Don'ts

### Do:
- **Do** give every new container a 2px Ledger Ink border, square corners and an offset shadow from the vocabulary (4/6/8px, zero blur).
- **Do** keep Audit Blue as the single UI accent, and use it to mark the one value or action that matters in each group.
- **Do** set every amount, count and percentage in tabular numerals, and format rupees Indian-style (₹ L / Cr).
- **Do** keep chart cards Sheet White in both themes and draw plots from the `SERIES` order in `app.py`, blue first.
- **Do** pair lift-on-hover with press-on-click for any button or card that casts a shadow.

### Don't:
- **Don't** round corners or blur shadows. A soft drop shadow breaks the cut-sheet world.
- **Don't** bring back the retired brown, paper and Georgia-serif palette anywhere, including charts, favicon or exports.
- **Don't** use chart categorical colours (orange, aqua, yellow …) for UI chrome, badges or text.
- **Don't** set sentences, notes or table data in uppercase.
- **Don't** ship focus states as browser defaults. Fields take the blue border plus 4px blue offset; everything else takes the 2px blue outline.
- **Don't** use emoji or Unicode glyphs as icons, or animate numbers.

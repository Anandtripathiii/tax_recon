---
target: tax-recon/templates/index.html
total_score: 22
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
target_identity: "file:C:\\Users\\Asus\\Documents\\Anand Work\\Anand Code\\tax-recon\\tax-recon\\templates\\index.html"
target_fingerprint: "sha256:0591e416e2a839b12ccea0bc8bebc1ef98f0daba25e4964a96bf8ddcce60dda0"
target_path: "C:\\Users\\Asus\\Documents\\Anand Work\\Anand Code\\tax-recon\\tax-recon\\templates\\index.html"
timestamp: 2026-10-10T07-27-10Z
slug: tax-recon-templates-index-html
---
Method: dual-agent (A: design review · B: detector and browser evidence)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | The loader only appears on Run. Accuracy's first load and Search give no feedback. `elapsed` is computed but never shown. |
| 2 | Match System / Real World | 3 | ₹ L/Cr and the April–March year are right. Raw code names leak through; flag text says "Rs"; tables use ISO dates; axes say "800k". |
| 3 | User Control and Freedom | 2 | Run silently drops the active q/kind filters. "Show example" has no href, so the keyboard can't reach it. |
| 4 | Consistency and Standards | 2 | Four product names. Inline-styled h2s. Labels and raw codes are mixed. |
| 5 | Error Prevention | 2 | The server clamps edited URLs without saying so. /download is unclamped. Seed has no bounds. |
| 6 | Recognition Rather Than Recall | 3 | Seed is unexplained. The Record column duplicates Invoice. |
| 7 | Flexibility and Efficiency | 2 | No sort, no ₹-impact ordering, no drill-down, no shortcuts, no reviewed state. |
| 8 | Aesthetic and Minimalist Design | 3 | Disciplined system. The homepage boilerplate and the 4-column comparison add bulk. |
| 9 | Error Recovery | 2 | Good empty-filter message. No compute-failure state. ML precision has no guidance. |
| 10 | Help and Documentation | 1 | Only net liability is defined. |
| **Total** | | **22/40** | **Acceptable** |

## Design Specificity Verdict
The dashboard is partly specific to this product; the homepage could belong to almost any product (big hero, then 01/02/03 cards, then two stat cards). The example card is the real signature, but it appears once, below the fold.

Detector: 26 findings.
- low-contrast ×9: muted text on #eef1f7 at 4.27:1 is real; the footer link at 3.35:1 is real; the watermark is a false positive.
- design-system-font-size ×13: partly real.
- skipped-heading ×1: real (also, two h1s).
- hero-eyebrow-chip ×1: real.
- overused-font ×2: false positive (these are the documented fonts).
- codex-grid-background ×1: false positive (the grid is the documented motif).

Missed by the detector: in dark theme the verdict bar and the footer are white on white (1:1). Focus states are absent.

No overlay: no tool that can inject into a live page was available.

## Priority Issues
- [P0] Dark theme: the verdict bar and footer are white on white (lines 215, 261, 274, 279). The Query form emails YOUR_EMAIL_HERE@example.com (line 568). Fix: pin both to ink background with white text in both themes; replace or remove Query. Command: /impeccable harden
- [P1] Only one flag explains itself. Flagged table: "Rs" text, no expected/found/difference, alphabetical sort, wrapping ISO dates, redundant Record column. Fix: Expected | Found | Difference (₹) | Sources columns, sort by ₹, expandable exhibit rows. Command: /impeccable clarify
- [P1] "Live proof" is hardcoded (lines 334-341) and `elapsed` is unused. The section is misaligned because .section lacks width:100% (line 74). The fuzzy-vs-exact result is buried. Fix: bind to ev/elapsed, show before → after accuracy, put the exhibit on the homepage. Command: /impeccable layout, then /impeccable bolder
- [P1] Phone overflow: the .hero-title 3rem minimum is wider than 390px; tabs wrap; the donut legend is clipped. Fix: lower the clamp minimum, scrolling tabs, grid topbar. Command: /impeccable adapt
- [P2] Unexplained terms and ML output (ITC, z-score, F1, seed; raw code names; "k" axes; 18.4% ML precision with no framing). Command: /impeccable clarify

## Persona Red Flags
- Alex: no sort; Run wipes the filters; search only on submit; no shortcuts, no reviewed state, no deep link.
- Sam: no focus-visible styles; glyph-only buttons with only a title; the Show example link has no href; no aria-current or aria-live; charts have no text alternative; unlabelled search and select; footer link at 3.35:1.
- CA: negative net GST with no synthetic-data note; ITC at risk undefined; no expected vs found; ISO dates; "owes extra tax" framing.
- Judge: about 800px of marketing before the tool; static "live" proof; best exhibit below the fold; misaligned section; placeholder email.

## Minor Observations
Theme flash; two h1s; redundant "330 of 330 (first 500)"; tax legend collision; clipped donut legend dominated by Matched 90.3%; empty "Also flagged for" column; hover lift on non-interactive cards; 3,033 vs 3000 invoices unexplained.

## Questions to Consider
- Why open on marketing cards instead of a live exhibit?
- Should the dashboard be the first screen?
- What does a CA do with a flag after seeing it?
- Should the 18%-precision ML output be a review queue rather than a flag type?

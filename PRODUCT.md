# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences, served by one surface:

- **Competition judges (Fintechstico PS2).** They evaluate the submission in a short demo window: does the approach work, how accurate is it, and is it credible as a real tool.
- **Chartered accountants (CAs) doing GST reconciliation.** The product should look and behave like a tool a CA would actually use to cross-check a client's invoices, bank payments and books before GST filing. Judges see the demo, but it has to read as a working professional tool rather than a hackathon prototype.

## Product Purpose

Tax Reconciliation matches every invoice to its bank payment and ledger entry, then surfaces what's wrong: incorrect GST, duplicate invoices, missing payments, missing ledger entries, date shifts, payments with no invoice, and amounts that look statistically unusual. It also computes monthly GST liability (output tax minus input tax credit).

Success means a viewer can see, within a few minutes, that the tool catches real error types accurately and explains each finding clearly enough to act on.

## Positioning

- **Three-way matching, not two-way.** Invoice ↔ bank ↔ ledger, with exact matching on IDs plus fuzzy matching on party name, amount and date. Fuzzy matching is what recovers payments that carry no invoice number.
- **Proven accuracy, not claimed accuracy.** The demo data comes with a hidden answer table, so precision/recall is measured live on every run and compared against an exact-match-only baseline.
- **Rules plus ML.** Deterministic checks (GST recompute, duplicates, missing records) sit alongside an Isolation Forest that scores how unusual each invoice looks, catching patterns no rule describes.

## Operating Context

- Inputs are three record sets: sales/purchase invoices, bank statement transactions, and ledger (books) entries.
- Indian GST context: amounts in ₹ shown in Indian style (Lakh / Crore), GST rate slabs, input tax credit, monthly liability.
- Typical use is to run a reconciliation, review flagged records by problem type, search/filter them, inspect an example invoice side by side across all three sources, check accuracy, and export results (CSV of flagged records, Excel workbook).
- Viewers can tune run size (500–5,000 invoices), error rate (2–25%) and seed.

## Capabilities and Constraints

- **Data is synthetic only.** `generator.py` creates invoices, bank and ledger records and plants known errors. Real file upload is not in scope, so don't design upload flows or imply that users' own data is supported.
- Stack: Flask + Jinja template (`tax-recon/templates/index.html`), pandas, scikit-learn, rapidfuzz, Plotly; deployed on Render via gunicorn (free plan). Local run via `run.bat` / `python app.py` on port 5000.
- Current sections: homepage, Summary, flagged records (filter by problem type and search), Monthly figures / GST liability, Unusual records (top 25 by ML score), Accuracy (full matching vs exact-only baseline), a question form, and downloads.
- Error-type terminology (keep consistent): Amount mismatch, Duplicate invoice, Wrong GST, Missing payment, Missing ledger entry, Date shift, Payment with no invoice, Unusual amount (ML).

## Brand Commitments

- Name in use: "Tax Reconciliation" (homepage headline currently "Tax errors, caught.").
- Plain, practical language aimed at accountants. Explain financial terms in one line where needed (e.g. net liability definition).

## Evidence on Hand

- **Verified, OK to show:** accuracy numbers (precision/recall computed live against the planted answer table); the comparison showing fuzzy matching beats exact-only; the public repo at github.com/Anandtripathiii/tax_recon.
- **Verified 2026-10-10:** "Reconciled in < 2 seconds" for 3,000 invoices. Measured locally (Python 3.14, 5 runs): reconcile 0.64–0.83 s at 3,000 invoices, 0.72–1.0 s including data generation and scoring; about 1.0 s at the 5,000 maximum. This is local hardware, not the Render free tier, so re-measure there before claiming hosted speed.
- **Absent, never fabricate:** real customers, testimonials, CA endorsements, firm logos, usage counts, pricing, or security/compliance certifications.

## Product Principles

1. **Every flag explains itself.** A finding should show what was expected, what was found, and which sources disagree, so a CA can act without digging.
2. **Show proof, not promises.** Lead with measured accuracy and side-by-side evidence. Unmeasured numbers don't belong in the product.
3. **Professional tool first, demo second.** Judges should see something a CA could use tomorrow. Avoid hackathon gimmicks that undercut credibility.
4. **Honest about synthetic data.** The planted-error answer key is a strength. Present it openly instead of implying real client data.

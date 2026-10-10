"""Flask dashboard for tax reconciliation.

Runs with `python app.py` locally or `gunicorn app:app` in production.
"""
import io
import json
import os
import pathlib
import threading
import time
import webbrowser

import pandas as pd
import plotly
import plotly.express as px
import plotly.graph_objects as go
from flask import Flask, Response, abort, jsonify, render_template, request, send_file

from engine import LEDGER_LATE_DAYS, MATCH_SCORE, PAY_LATE_DAYS, SLABS, TAX_TOLERANCE, evaluate, run_all, to_excel
from generator import make_data
import ask as asker
import auth
from flask_login import current_user, login_required
import ledger as L
from ledger import LABELS, evidence, rs

asker.load_env()

# Audit Ledger chart palette: brand blue first, then a CVD-validated categorical order.
# Charts always sit on a white card (both themes), so only the light steps are needed.
INK, BLUE, ORANGE, QUIET = "#0a0a0f", "#2d4bff", "#eb6834", "#c3c8d4"
SERIES = [BLUE, ORANGE, "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TEMPLATE = {"layout": dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#ffffff",
    font=dict(family="Inter, -apple-system, 'Segoe UI', sans-serif", color=INK, size=13),
    title=dict(font=dict(family="'Space Grotesk', sans-serif", size=15, color=INK)),
    xaxis=dict(gridcolor="rgba(10,10,15,0.08)", linecolor=INK, zerolinecolor="rgba(10,10,15,0.25)"),
    yaxis=dict(gridcolor="rgba(10,10,15,0.08)", linecolor=INK, zerolinecolor="rgba(10,10,15,0.25)"),
    hoverlabel=dict(bgcolor=INK, bordercolor=INK, font=dict(family="Inter, sans-serif", color="#ffffff")),
    colorway=SERIES, margin=dict(l=50, r=20, t=50, b=50), height=380)}


def fig(f):
    f.update_layout(**TEMPLATE["layout"])
    return json.loads(f.to_json())


_cache = {}
_lock = threading.Lock()
_compute_lock = threading.Lock()


def compute(n, rate, seed, with_baseline=False):
    """Core compute. The baseline (exact-match-only) is only needed on the Accuracy
    tab, so by default we skip it and save ~0.5 s per first visit. When the user
    does open Accuracy, we fill it in using the already-cached data."""
    key = (int(n), round(float(rate), 4), int(seed))
    with _lock:
        entry = _cache.get(key)
    if entry is None:
        # One run at a time: a second caller (e.g. the startup warmup) waits and reuses the
        # result instead of competing for CPU, which also keeps the measured time honest.
        with _compute_lock:
            with _lock:
                entry = _cache.get(key)
            if entry is None:
                t0 = time.time()
                d = make_data(n, rate, seed)
                res = run_all(d["invoices"], d["bank"], d["ledger"])
                ev = evaluate(d["truth"], res)
                elapsed = time.time() - t0
                entry = {"d": d, "res": res, "ev": ev, "ev_base": None, "elapsed": elapsed}
                with _lock:
                    _cache.clear()
                    _cache[key] = entry
    if with_baseline and entry["ev_base"] is None:
        d = entry["d"]
        base = run_all(d["invoices"], d["bank"], d["ledger"], fuzzy=False)
        entry["ev_base"] = evaluate(d["truth"], base)
    return (entry["res"], entry["ev"], entry["ev_base"], entry["elapsed"], entry["d"]["truth"])


def _warmup():
    """Precompute the default run at startup so the first visitor sees results instantly."""
    try:
        # A small throwaway run first pays one-time library start-up costs (worker pools,
        # imports), so the default run's measured time reflects the reconciliation itself.
        d = make_data(500, 0.10, 1)
        evaluate(d["truth"], run_all(d["invoices"], d["bank"], d["ledger"]))
        compute(3000, 0.10, 42, with_baseline=False)
    except Exception:
        pass


threading.Thread(target=_warmup, daemon=True).start()


def _amount(v):
    """Parse an amount filter: plain rupees, or with L / Cr (e.g. 1.5L, 2cr). Blank means no limit."""
    v = (v or "").strip().lower().replace(",", "").replace("₹", "")
    if not v:
        return None
    mult = 1
    if v.endswith("cr"):
        mult, v = 1e7, v[:-2]
    elif v.endswith("l"):
        mult, v = 1e5, v[:-1]
    try:
        return float(v) * mult
    except ValueError:
        return None


def flag_filters(a):
    return {"q": (a.get("q") or "").strip(), "kind": a.get("kind", "All"), "party": (a.get("party") or "").strip(),
            "min_amt": _amount(a.get("min")), "max_amt": _amount(a.get("max")),
            "sort": a.get("sort", "stake"), "order": a.get("order", "desc")}


def unusual_filters(a):
    return {"q": (a.get("q") or "").strip(), "party": (a.get("party") or "").strip(),
            "min_amt": _amount(a.get("min")), "max_amt": _amount(a.get("max")),
            "only_marked": a.get("show", "marked") == "marked",
            "sort": a.get("sort", "score"), "order": a.get("order", "desc")}


def run_args(a):
    n = max(500, min(5000, a.get("n", 3000, type=int)))
    rate = max(0.02, min(0.25, a.get("rate", 10, type=int) / 100))
    seed = a.get("seed", 42, type=int)
    return n, rate, seed


def live_proof(res, ev, elapsed):
    """Homepage proof figures, taken from the current run instead of typed-in text."""
    g = ev[ev.error_type == "wrong_gst"]
    ml = ev[ev.error_type == "anomalous_amount"]
    return {"invoices": f"{len(res['inv']):,}", "seconds": f"{elapsed:.1f}",
            "gst_precision": f"{g.precision.iloc[0] * 100:.0f}%" if len(g) else "—",
            "gst_recall": f"{g.recall.iloc[0] * 100:.0f}%" if len(g) else "—",
            "ml_precision": f"{ml.precision.iloc[0] * 100:.0f}%" if len(ml) else "—"}


MATERIALITY = 98.0   # a check passes when at least this share of records is clean


def verification(res, ev):
    """Verify the whole reconciliation from the run's own data. Every figure is computed here."""
    inv, bank, flags = res["inv"], res["bank"], res["flags"]
    ok = ~inv.dup
    n_ok, n_all = int(ok.sum()), len(inv)
    checks = []

    def add(key, title, clean, total, detail):
        score = 100.0 * clean / total if total else 100.0
        checks.append({"key": key, "title": title, "score": score, "clean": clean, "total": total,
                       "passed": score >= MATERIALITY, "detail": detail})

    paid = int((ok & inv.txn_id.notna()).sum())
    add("matched", "All invoices matched to payments", paid, n_ok,
        f"{paid:,} of {n_ok:,} invoices have a bank payment. "
        f"The other {n_ok - paid:,} are flagged as Missing payment.")

    has_led = ok & inv.entry_id.notna()
    ties = has_led & ((inv.led_amount - inv.total).abs() <= 1)
    gap = (inv.led_amount - inv.total)[has_led].sum()
    add("ledger", "Ledger totals tie out", int(ties.sum()), int(has_led.sum()),
        f"{int(ties.sum()):,} of {int(has_led.sum()):,} ledger entries equal their invoice (±₹1). "
        f"Ledger {rs(inv.led_amount[has_led].sum())} vs invoices {rs(inv.total[has_led].sum())}, "
        f"difference {rs(abs(gap))}.")

    # Recomputed here, independently of the engine: taxable value x GST rate.
    recomputed = (inv.taxable_value * inv.gst_rate / 100).round(2)
    right = ok & inv.gst_rate.isin(SLABS) & ((inv.tax_amount - recomputed).abs() <= TAX_TOLERANCE)
    wrong = ok & ~right
    engine_agrees = set(inv.row_id[wrong]) == set(flags.key[flags.error_type == "wrong_gst"])
    add("gst", "GST recomputed correctly", int(right.sum()), n_ok,
        f"{int(right.sum()):,} of {n_ok:,} invoices charge the right GST. "
        f"Tax gap on the other {int(wrong.sum()):,}: {rs((inv.tax_amount - recomputed)[wrong].abs().sum())}. "
        + ("The engine flagged exactly these." if engine_agrees else "The engine's flags differ from this recount."))

    dups = int(inv.dup.sum())
    add("dups", "No duplicate records", n_all - dups, n_all,
        f"{dups:,} duplicate copies among {n_all:,} invoices, each flagged as Duplicate invoice.")

    explained = int(flags.detail.fillna("").str.strip().ne("").sum())
    add("explained", "Every flag has an explanation", explained, len(flags),
        f"{explained:,} of {len(flags):,} flags carry a written reason.")

    rules = ev[ev.error_type != "anomalous_amount"]
    correct, flagged = int(rules.correct.sum()), int(rules.flagged.sum())
    add("answers", "Flags confirmed by the answer key", correct, flagged,
        f"{correct:,} of {flagged:,} rule-based flags are real planted errors. "
        "The ML review queue is left out; see Unusual records.")

    overall = sum(c["score"] for c in checks) / len(checks)
    passed = sum(c["passed"] for c in checks)
    return {"checks": checks, "score": overall, "passed": passed, "count": len(checks),
            "all_pass": passed == len(checks), "materiality": MATERIALITY}


def pick_example(res, truth):
    """Pick one wrong_gst invoice with matching bank and ledger to show side-by-side."""
    inv = res["inv"]
    bank = res["bank"]
    led = res["ledger"]
    wrong = truth[truth.error_type == "wrong_gst"].key.tolist()
    for rid in wrong:
        row = inv[inv.row_id == rid]
        if row.empty:
            continue
        r = row.iloc[0]
        if pd.isna(r.txn_id) or pd.isna(r.entry_id):
            continue
        b = bank[bank.txn_id == r.txn_id].iloc[0]
        l = led[led.entry_id == r.entry_id].iloc[0]
        return {
            "invoice_id": r.invoice_id, "party": r.party, "date": r.date.strftime("%d %b %Y"),
            "taxable": rs(r.taxable_value), "gst_rate": int(r.gst_rate),
            "charged_tax": rs(r.tax_amount), "expected_tax": rs(r.expected_tax),
            "diff": rs(r.tax_amount - r.expected_tax), "total": rs(r.total),
            "bank_date": pd.to_datetime(b.date).strftime("%d %b %Y"),
            "bank_amount": rs(b.amount), "narration": b.narration,
            "ledger_date": pd.to_datetime(l.date).strftime("%d %b %Y"),
            "ledger_amount": rs(l.amount), "ledger_party": l.party,
        }
    return None


app = Flask(__name__)
app.json.sort_keys = False  # keep record fields in reading order (Invoice, Party, GSTIN, Date...)
auth.init_app(app)
PLOTLY_JS = str(next(pathlib.Path(plotly.__path__[0]).rglob("plotly.min.js")))


@app.context_processor
def _template_helpers():
    """url_with(**changes): the current page URL with some query args changed (for sort links);
    qs(): the current query string (for exports of the filtered view)."""
    from urllib.parse import urlencode

    def url_with(**changes):
        args = request.args.to_dict()
        args.update({k: v for k, v in changes.items() if v is not None})
        return "/?" + urlencode(args) + "#dashboard"

    def qs():
        return urlencode(request.args.to_dict())

    def asset(name):
        f = pathlib.Path(app.static_folder) / name
        return f"/static/{name}?v={int(f.stat().st_mtime) if f.exists() else 0}"

    return {"url_with": url_with, "qs": qs, "asset": asset}


@app.route("/plotly.min.js")
def _plotly():
    return send_file(PLOTLY_JS, mimetype="application/javascript")


@app.route("/favicon.ico")
def _favicon():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect width="64" height="64" fill="#0a0a0f"/>'
           '<path d="M14 10 h28 l8 8 v36 h-36 z" fill="#ffffff"/>'
           '<path d="M42 10 v8 h8" fill="none" stroke="#0a0a0f" stroke-width="2.5"/>'
           '<line x1="20" y1="28" x2="44" y2="28" stroke="#2d4bff" stroke-width="3"/>'
           '<line x1="20" y1="36" x2="44" y2="36" stroke="#2d4bff" stroke-width="3"/>'
           '<line x1="20" y1="44" x2="34" y2="44" stroke="#2d4bff" stroke-width="3"/>'
           '</svg>')
    return Response(svg, mimetype="image/svg+xml")


@app.route("/")
def index():
    n = max(500, min(5000, request.args.get("n", 3000, type=int)))
    rate = max(0.02, min(0.25, request.args.get("rate", 10, type=int) / 100))
    seed = request.args.get("seed", 42, type=int)
    active = request.args.get("tab", "summary")

    if not current_user.is_authenticated:
        res, ev, _, elapsed, _ = compute(n, rate, seed)
        return render_template("index.html", locked=True, active=active, n=n, rate=int(rate * 100), seed=seed,
                               proof=live_proof(res, ev, elapsed), demo_email=auth.DEMO_EMAIL, demo_password=auth.DEMO_PASSWORD)
    res, ev, ev_base, elapsed, truth = compute(n, rate, seed, with_baseline=(active == "accuracy"))
    proof = live_proof(res, ev, elapsed)
    if active == "query":
        return render_template("index.html", active="query", n=n, rate=int(rate * 100), seed=seed,
                               proof=proof, kpis=[], tax_kpis=[], flagged=[], monthly=[], anomaly_tbl=[],
                               acc_tbl=[], cmp_rows=[], kinds=["All"], kind="All", q="",
                               donut=None, bars=None, gst=None, hist=None, scat=None, accuracy=None,
                               fuzzy_count=0, example=None, total_filtered=0,
                               suggest=asker.suggestions(res), ai_on=asker.ai_enabled(), locked=False)
    inv, flags, lia = res["inv"], res["flags"], res["liability"]
    status = inv.status.value_counts()
    orphans = len(res["orphans"])

    kpis = [("Invoices", f"{len(inv):,}"), ("Matched", f"{status.get('Matched', 0):,}"),
            ("Discrepancies", f"{status.get('Discrepancy', 0):,}"),
            ("Unmatched", f"{status.get('Unmatched', 0):,}"),
            ("Duplicates", f"{status.get('Duplicate', 0):,}"),
            ("Orphan payments", f"{orphans:,}")]

    # Pie chart with outside labels so slices don't overlap
    donut_fig = px.pie(status.reset_index(), names="status", values="count", hole=.55,
                      color_discrete_sequence=SERIES, title="Invoices by status")
    donut_fig.update_traces(textposition="outside", textinfo="label+percent",
                           pull=[0.02] * len(status), rotation=180,  # small slices sit at the bottom, clear of the title
                           marker=dict(line=dict(color="#ffffff", width=2)))
    donut_fig.update_layout(showlegend=False, margin=dict(l=40, r=40, t=100, b=40),
                            title=dict(x=0.02, y=0.97, yanchor="top"))
    donut = fig(donut_fig)

    by = flags.error_type.map(LABELS).value_counts().reset_index()
    if by.empty:
        by = pd.DataFrame({"error_type": ["(none)"], "count": [0]})
    bars = fig(px.bar(by, x="count", y="error_type", orientation="h",
                      color_discrete_sequence=[BLUE], title="Problems found, by type",
                      labels={"count": "Records", "error_type": ""}
                      ).update_layout(yaxis=dict(categoryorder="total ascending")))

    def tbl(df, cols=None, rename=None):
        if cols:
            df = df[cols]
        if rename:
            df = df.rename(columns=rename)
        if df.empty:
            return [list(df.columns)]
        return [list(df.columns)] + df.astype(object).where(df.notna(), "").values.tolist()

    ff = flag_filters(request.args)
    kind, q = ff["kind"], ff["q"]
    all_flags = L.flag_rows(res)
    t = L.filter_flags(all_flags, **ff)
    total_filtered = len(t)
    flag_list = [{"id": r.invoice_id, "problem": r.problem, "party": r.party,
                  "date": r.date.strftime("%d %b %Y") if pd.notna(r.date) else "", "amount": rs(r.total),
                  "expected": r.expected, "found": r.found, "stake": rs(r.stake) if pd.notna(r.stake) else "",
                  "why": r.detail} for r in t.head(500).itertuples()]
    parties = sorted(p for p in all_flags.party.unique() if p != "Unknown (bank only)")

    m = lia["monthly"]
    gst_fig = go.Figure()
    lakh = lambda v: (v / 1e5).round(2)
    gst_fig.add_bar(x=m.month, y=lakh(m.output_tax), name="Output tax (sales)", marker_color=BLUE)
    gst_fig.add_bar(x=m.month, y=lakh(m.itc), name="Input tax credit (purchases)", marker_color=ORANGE)
    gst_fig.add_scatter(x=m.month, y=lakh(m.net_clean), name="Net liability",
                        line=dict(color=INK, width=2), marker=dict(size=8))
    gst_fig.update_layout(barmode="group", title="Monthly GST from clean records",
                          yaxis_title="₹ Lakh", legend=dict(orientation="h", y=-0.28, x=0),
                          margin=dict(l=60, r=20, t=50, b=90), height=420)
    gst = fig(gst_fig)
    monthly = tbl(m.round(0).assign(
        output_tax=m.output_tax.apply(rs), itc=m.itc.apply(rs),
        net_clean=m.net_clean.apply(rs), net_as_filed=m.net_as_filed.apply(rs)),
        rename={"month": "Month", "output_tax": "Output tax", "itc": "ITC",
                "net_clean": "Net (clean)", "net_as_filed": "Net (as filed)"})
    tax_b = L.tax_breakdown(res)
    tax_text = L.tax_report_text(tax_b)
    wrong = inv[(inv.issues.str.contains("wrong_gst")) & (inv.status != "Duplicate")]
    tax_kpis = [("Net GST as filed", rs(m.net_as_filed.sum())),
                ("Net GST, clean only", rs(m.net_clean.sum())),
                ("ITC at risk", rs(lia["itc_at_risk"])),
                ("Tax gap on wrong-GST", rs((wrong.tax_amount - wrong.expected_tax).sum()))]

    hist = fig(px.histogram(inv, x="anomaly_score", nbins=40,
                            color_discrete_sequence=[BLUE],
                            title="How unusual each invoice looks",
                            labels={"anomaly_score": "Unusualness score (0 = typical, 1 = most unusual)"}
                            ).update_layout(yaxis_title="Invoices"))
    scat = fig(px.scatter(inv.assign(group=inv.anomaly.map({True: "Marked unusual", False: "Typical"})),
                          x="log_amount", y="party_z", color="group",
                          color_discrete_map={"Typical": QUIET, "Marked unusual": BLUE},
                          hover_data=["invoice_id", "party"],
                          title="Amount vs. this party's usual amount",
                          labels={"log_amount": "Invoice size (log scale)",
                                  "party_z": "Distance from party's average", "group": ""}
                          ).update_layout(legend=dict(orientation="h", y=-0.25, x=0)))
    uf = unusual_filters(request.args)
    u_all = L.unusual_rows(res)
    u = L.filter_unusual(u_all, **uf)
    unusual_total = len(u)
    unusual_list = [{"id": r.invoice_id, "party": r.party, "date": r.date.strftime("%d %b %Y"), "amount": rs(r.total),
                     "score": f"{r.anomaly_score:.3f}", "why": r.why, "also": r.also, "marked": bool(r.anomaly)}
                    for r in u.head(300).itertuples()]
    marked_count = int(u_all.anomaly.sum())

    e = ev.assign(error_type=ev.error_type.map(LABELS))
    acc_fig = go.Figure()
    acc_fig.add_bar(x=e.error_type, y=(e.precision * 100).round(1),
                    name="Precision (%)", marker_color=BLUE)
    acc_fig.add_bar(x=e.error_type, y=(e.recall * 100).round(1),
                    name="Recall (%)", marker_color=ORANGE)
    acc_fig.update_layout(barmode="group", title="Precision and recall per error type",
                          yaxis_title="%", legend=dict(orientation="h", y=-0.3),
                          xaxis=dict(tickangle=-25))
    accuracy = fig(acc_fig)
    pct = lambda x: f"{x * 100:.1f}%"
    acc_tbl = tbl(e.assign(precision=e.precision.apply(pct), recall=e.recall.apply(pct),
                           f1=e.f1.apply(pct)),
                  ["error_type", "planted", "flagged", "correct", "precision", "recall", "f1"],
                  {"error_type": "Error type", "planted": "Planted", "flagged": "Flagged",
                   "correct": "Correct", "precision": "Precision", "recall": "Recall", "f1": "F1"})
    cmp_rows = []
    if ev_base is not None:
        cmp = ev[["error_type", "precision", "recall"]].merge(
            ev_base[["error_type", "precision", "recall"]], on="error_type", suffixes=("", "_base"))
        for r in cmp.itertuples():
            dp, dr = (r.precision - r.precision_base) * 100, (r.recall - r.recall_base) * 100
            cmp_rows.append({"label": LABELS.get(r.error_type, r.error_type),
                             "p0": pct(r.precision_base), "p1": pct(r.precision), "dp": dp,
                             "r0": pct(r.recall_base), "r1": pct(r.recall), "dr": dr,
                             "changed": abs(dp) >= 5 or abs(dr) >= 5})
        cmp_rows.sort(key=lambda x: -max(abs(x["dp"]), abs(x["dr"])))
    kinds = ["All"] + sorted(set(flags.error_type.map(LABELS).dropna()))
    fuzzy_count = int((inv.match == "fuzzy").sum())
    example = pick_example(res, truth)
    verify = verification(res, ev) if active == "verify" else None

    return render_template(
        "index.html", n=n, rate=int(rate * 100), seed=seed,
        kpis=kpis, donut=donut, bars=bars, flag_list=flag_list, total_filtered=total_filtered,
        kinds=kinds, kind=kind, q=q, ff=ff, parties=parties, uf=uf, unusual_list=unusual_list,
        unusual_total=unusual_total, marked_count=marked_count, tax_b=tax_b, tax_text=tax_text, rupees=L.rupees,
        tax_kpis=tax_kpis, gst=gst, monthly=monthly, hist=hist, scat=scat,
        accuracy=accuracy, acc_tbl=acc_tbl, cmp_rows=cmp_rows, fuzzy_count=fuzzy_count,
        proof=proof, example=example, verify=verify, active=active, locked=False)


@app.route("/download/<kind>")
@login_required
def download(kind):
    n = max(500, min(5000, request.args.get("n", 3000, type=int)))
    rate = max(0.02, min(0.25, request.args.get("rate", 10, type=int) / 100))
    seed = request.args.get("seed", 42, type=int)
    res, _, _, _, _ = compute(n, rate, seed, with_baseline=False)
    if kind == "excel":
        return send_file(io.BytesIO(to_excel(res)), as_attachment=True,
                         download_name="reconciliation_report.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if kind == "flagged":
        buf = io.StringIO()
        res["flags"].to_csv(buf, index=False)
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=flagged_records.csv"})
    abort(404)


def _send_table(sheets, fmt, name):
    """sheets: list of (sheet name, DataFrame). CSV uses the first sheet, with a BOM so Excel reads ₹ correctly."""
    if fmt == "csv":
        return Response(sheets[0][1].to_csv(index=False).encode("utf-8-sig"), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={name}.csv"})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for title, df in sheets:
            df.to_excel(xw, sheet_name=title[:31], index=False)
            ws = xw.sheets[title[:31]]
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{name}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/export/<view>.<fmt>")
@login_required
def export(view, fmt):
    """Export exactly what the tab shows: the same filters and sort, every matching row (not just the first 500)."""
    if fmt not in ("csv", "xlsx"):
        abort(404)
    n, rate, seed = run_args(request.args)
    res, ev, _, _, _ = compute(n, rate, seed)
    if view == "flagged":
        t = L.filter_flags(L.flag_rows(res), **flag_filters(request.args))
        return _send_table([("Flagged records", L.flags_export(t))], fmt, "flagged_records")
    if view == "unusual":
        u = L.filter_unusual(L.unusual_rows(res), **unusual_filters(request.args))
        return _send_table([("Unusual records", L.unusual_export(u))], fmt, "unusual_records")
    if view == "tax":
        b = L.tax_breakdown(res)
        rows = []
        for label, key in (("As filed (all invoices)", "as_filed"), ("Clean (matched only)", "clean")):
            t = b[key]
            rows += [(label, "Taxable sales", round(t["taxable_sales"], 2)), (label, "Output tax", round(t["output_tax"], 2)),
                     (label, "Taxable purchases", round(t["taxable_purchases"], 2)), (label, "Input tax credit", round(t["itc"], 2)),
                     (label, "Net GST payable", round(t["net"], 2)), (label, "Invoices", t["invoices"])]
        rows += [("Adjustments", "ITC at risk", round(b["itc_at_risk"], 2)),
                 ("Adjustments", "Excess tax charged (wrong GST)", round(b["excess_tax_charged"], 2)),
                 ("Adjustments", "Tax short-charged (wrong GST)", round(b["short_tax_charged"], 2))]
        summary = pd.DataFrame(rows, columns=["Basis", "Item", "₹"])
        slabs = pd.DataFrame(b["slabs"]).rename(columns={"rate": "GST rate", "sales_taxable": "Taxable sales (₹)",
                                                          "output_tax": "Output tax (₹)", "purchase_taxable": "Taxable purchases (₹)",
                                                          "itc": "ITC (₹)", "invoices": "Invoices"})
        months = pd.DataFrame(b["months"]).rename(columns={"month": "Month", "output_tax": "Output tax (₹)", "itc": "ITC (₹)",
                                                            "net_clean": "Net, clean (₹)", "net_as_filed": "Net, as filed (₹)"})
        return _send_table([("Summary", summary), ("By rate", slabs.round(2)), ("By month", months.round(2))], fmt, "gst_summary")
    abort(404)


@app.route("/record/<rid>")
@login_required
def record(rid):
    n, rate, seed = run_args(request.args)
    res, ev, _, _, _ = compute(n, rate, seed)
    d = L.record_detail(res, rid)
    if d is None:
        return jsonify({"error": f"No invoice or payment {rid} in this run."}), 404
    return jsonify(d)


@app.route("/ask", methods=["POST"])
@login_required
def ask_route():
    body = request.get_json(silent=True) or {}
    a = {k: body.get(k) for k in ("n", "rate", "seed")}
    n = max(500, min(5000, int(a["n"] or 3000)))
    rate = max(0.02, min(0.25, int(a["rate"] or 10) / 100))
    seed = int(a["seed"] or 42)
    res, ev, _, _, _ = compute(n, rate, seed)
    ctx = {"res": res, "ev": ev, "run": {"invoices_requested": n, "error_rate": f"{int(rate * 100)}%", "seed": seed}}
    return jsonify(asker.answer(body.get("question", ""), ctx))


@app.route("/how-it-works")
def how_it_works():
    from generator import ERROR_MIX
    mix = ", ".join(f"{LABELS[k]} {int(v * 100)}%" for k, v in ERROR_MIX.items())
    return render_template("pages/how_it_works.html", n=3000, rate=10, slabs=" / ".join(str(x) for x in sorted(SLABS)),
                           mix=mix, match_pct=int(MATCH_SCORE * 100), tol=TAX_TOLERANCE, pay_days=PAY_LATE_DAYS,
                           led_days=LEDGER_LATE_DAYS)


@app.route("/accuracy-method")
def accuracy_method():
    n, rate, seed = 3000, 0.10, 42
    res, ev, ev_base, _, _ = compute(n, rate, seed, with_baseline=True)
    pct = lambda x: f"{x * 100:.1f}%"
    rows = [{"label": LABELS.get(r.error_type, r.error_type), "planted": r.planted, "flagged": r.flagged,
             "correct": r.correct, "precision": pct(r.precision), "recall": pct(r.recall), "f1": pct(r.f1)}
            for r in ev.itertuples()]
    base = ev_base.set_index("error_type")
    cmp = [{"label": LABELS.get(r.error_type, r.error_type), "p0": pct(base.loc[r.error_type, "precision"]),
            "p1": pct(r.precision)} for r in ev.itertuples() if r.error_type in base.index]
    cmp.sort(key=lambda x: float(x["p0"][:-1]) - float(x["p1"][:-1]))
    return render_template("pages/accuracy_method.html", rows=rows, cmp=cmp, n=n, rate=int(rate * 100), seed=seed)


SAMPLE_FILES = [
    ("invoices", "Invoices", "invoices", "Sales and purchase invoices, including the planted errors and duplicates."),
    ("bank", "Bank statement", "bank", "Every bank transaction, money in and out, with the narration text the matcher reads."),
    ("ledger", "Ledger", "ledger", "Ledger entries with the invoice reference, amount and tax booked."),
    ("answer_key", "Answer key", "truth", "The errors the generator planted: which record, and which error type. The engine never reads this."),
]


@app.route("/sample-data")
def sample_data():
    n, rate, seed = run_args(request.args)
    data = _cache_data(n, rate, seed)
    files = [{"key": k, "name": name, "about": about, "rows": len(data[src]), "cols": ", ".join(data[src].columns)}
             for k, name, src, about in SAMPLE_FILES]
    return render_template("pages/sample_data.html", files=files, n=n, rate=int(rate * 100), seed=seed)


def _cache_data(n, rate, seed):
    compute(n, rate, seed)
    key = (int(n), round(float(rate), 4), int(seed))
    with _lock:
        return _cache[key]["d"]


@app.route("/sample/<name>.csv")
def sample_file(name):
    src = {k: s for k, _, s, _ in SAMPLE_FILES}.get(name)
    if src is None:
        abort(404)
    n, rate, seed = run_args(request.args)
    df = _cache_data(n, rate, seed)[src]
    return Response(df.to_csv(index=False).encode("utf-8-sig"), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}_n{n}_r{int(rate * 100)}_s{seed}.csv"})


@app.route("/about")
def about():
    return render_template("pages/about.html")


@app.route("/contact")
def contact():
    return render_template("pages/contact.html")


def _open_browser():
    threading.Timer(1.2, lambda: webbrowser.open_new("http://127.0.0.1:5000/")).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    if port == 5000:
        _open_browser()
    app.run(host="0.0.0.0", port=port, debug=False)

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
from flask import Flask, Response, abort, render_template, request, send_file

from engine import evaluate, run_all, to_excel
from generator import make_data

PAPER = ["#8B4513", "#C9A66B", "#6B8E23", "#A0522D", "#B8860B", "#704214", "#5F7A3D", "#8B7355"]
LABELS = {"amount_mismatch": "Amount mismatch", "duplicate": "Duplicate invoice", "wrong_gst": "Wrong GST",
          "missing_payment": "Missing payment", "missing_ledger": "Missing ledger entry",
          "date_shift": "Date shift", "orphan_payment": "Payment with no invoice",
          "anomalous_amount": "Unusual amount (ML)"}
TEMPLATE = {"layout": dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(245,239,224,0.4)",
    font=dict(family="Georgia, serif", color="#2B2118", size=13),
    title=dict(font=dict(family="Georgia, serif", size=15, color="#2B2118")),
    xaxis=dict(gridcolor="rgba(139,69,19,0.12)", linecolor="#8B4513"),
    yaxis=dict(gridcolor="rgba(139,69,19,0.12)", linecolor="#8B4513"),
    colorway=PAPER, margin=dict(l=50, r=20, t=50, b=50), height=380)}


def fig(f):
    f.update_layout(**TEMPLATE["layout"])
    return json.loads(f.to_json())


def rs(x):
    """Format a rupee amount in Indian style: Lakh / Crore."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return ""
    if x < 0:
        return "-" + rs(-x)
    if x >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


_cache = {}
_lock = threading.Lock()


def compute(n, rate, seed, with_baseline=False):
    """Core compute. The baseline (exact-match-only) is only needed on the Accuracy
    tab, so by default we skip it and save ~0.5 s per first visit. When the user
    does open Accuracy, we fill it in using the already-cached data."""
    key = (int(n), round(float(rate), 4), int(seed))
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
        compute(3000, 0.10, 42, with_baseline=False)
    except Exception:
        pass


threading.Thread(target=_warmup, daemon=True).start()


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
PLOTLY_JS = str(next(pathlib.Path(plotly.__path__[0]).rglob("plotly.min.js")))


@app.route("/plotly.min.js")
def _plotly():
    return send_file(PLOTLY_JS, mimetype="application/javascript")


@app.route("/favicon.ico")
def _favicon():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect width="64" height="64" fill="#F5EFE0"/>'
           '<path d="M14 12 h32 l6 8 v32 a4 4 0 0 1 -4 4 h-30 a4 4 0 0 1 -4 -4 z" fill="#FFFAEB" stroke="#8B4513" stroke-width="2.5"/>'
           '<path d="M46 12 v8 h6" fill="none" stroke="#8B4513" stroke-width="2.5" stroke-linejoin="round"/>'
           '<line x1="20" y1="28" x2="44" y2="28" stroke="#8B4513" stroke-width="2"/>'
           '<line x1="20" y1="36" x2="44" y2="36" stroke="#8B4513" stroke-width="2"/>'
           '<line x1="20" y1="44" x2="36" y2="44" stroke="#8B4513" stroke-width="2"/>'
           '</svg>')
    return Response(svg, mimetype="image/svg+xml")


@app.route("/")
def index():
    n = max(500, min(5000, request.args.get("n", 3000, type=int)))
    rate = max(0.02, min(0.25, request.args.get("rate", 10, type=int) / 100))
    seed = request.args.get("seed", 42, type=int)
    active = request.args.get("tab", "summary")

    if active == "query":
        return render_template("index.html", active="query", n=n, rate=int(rate * 100), seed=seed,
                               kpis=[], tax_kpis=[], flagged=[], monthly=[], anomaly_tbl=[],
                               acc_tbl=[], cmp_tbl=[], kinds=["All"], kind="All", q="",
                               donut=None, bars=None, gst=None, hist=None, scat=None, accuracy=None,
                               fuzzy_count=0, elapsed=0, example=None, total_filtered=0)

    res, ev, ev_base, elapsed, truth = compute(n, rate, seed, with_baseline=(active == "accuracy"))
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
                      color_discrete_sequence=PAPER, title="Invoices by status")
    donut_fig.update_traces(textposition="outside", textinfo="label+percent",
                           pull=[0.02] * len(status))
    donut = fig(donut_fig)

    by = flags.error_type.map(LABELS).value_counts().reset_index()
    if by.empty:
        by = pd.DataFrame({"error_type": ["(none)"], "count": [0]})
    bars = fig(px.bar(by, x="count", y="error_type", orientation="h",
                      color_discrete_sequence=PAPER, title="Problems found, by type",
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

    kind = request.args.get("kind", "All")
    q = (request.args.get("q", "") or "").strip()
    t = flags.assign(problem=flags.error_type.map(LABELS))
    t = t.merge(inv[["row_id", "invoice_id", "party", "date", "total"]],
                left_on="key", right_on="row_id", how="left")
    if kind != "All":
        t = t[t.problem == kind]
    if q:
        hay = t[["party", "invoice_id", "detail", "key"]].astype(str)
        mask = hay.apply(lambda c: c.str.contains(q, case=False, na=False)).any(axis=1)
        t = t[mask]
    total_filtered = len(t)
    t = t.sort_values("problem").head(500).copy()
    t["date"] = pd.to_datetime(t["date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    t["total"] = t["total"].apply(rs)
    flagged = tbl(t, ["problem", "invoice_id", "key", "party", "date", "total", "detail"],
                  {"problem": "Problem", "invoice_id": "Invoice", "key": "Record", "party": "Party",
                   "date": "Date", "total": "Total", "detail": "Why it was flagged"})

    m = lia["monthly"]
    gst_fig = go.Figure()
    gst_fig.add_bar(x=m.month, y=m.output_tax, name="Output tax (sales)", marker_color=PAPER[0])
    gst_fig.add_bar(x=m.month, y=m.itc, name="Input tax credit (purchases)", marker_color=PAPER[1])
    gst_fig.add_scatter(x=m.month, y=m.net_clean, name="Net liability",
                        line=dict(color="#2B2118", width=2))
    gst_fig.update_layout(barmode="group", title="Monthly GST from clean records",
                          yaxis_title="Rupees", legend=dict(orientation="h", y=-0.2))
    gst = fig(gst_fig)
    monthly = tbl(m.round(0).assign(
        output_tax=m.output_tax.apply(rs), itc=m.itc.apply(rs),
        net_clean=m.net_clean.apply(rs), net_as_filed=m.net_as_filed.apply(rs)),
        rename={"month": "Month", "output_tax": "Output tax", "itc": "ITC",
                "net_clean": "Net (clean)", "net_as_filed": "Net (as filed)"})
    wrong = inv[(inv.issues.str.contains("wrong_gst")) & (inv.status != "Duplicate")]
    tax_kpis = [("Net GST as filed", rs(m.net_as_filed.sum())),
                ("Net GST, clean only", rs(m.net_clean.sum())),
                ("ITC at risk", rs(lia["itc_at_risk"])),
                ("Tax gap on wrong-GST", rs((wrong.tax_amount - wrong.expected_tax).sum()))]

    hist = fig(px.histogram(inv, x="anomaly_score", nbins=40,
                            color_discrete_sequence=[PAPER[0]],
                            title="Anomaly score across all invoices"))
    scat = fig(px.scatter(inv, x="log_amount", y="party_z", color="anomaly",
                          color_discrete_sequence=["#C7B899", "#8B4513"],
                          hover_data=["invoice_id", "party"],
                          title="Amount vs. difference from the party's usual",
                          labels={"log_amount": "log amount", "party_z": "distance from party average"}))
    top = inv.sort_values("anomaly_score", ascending=False).head(25).copy()
    top["date"] = top["date"].dt.strftime("%Y-%m-%d")
    top["total"] = top["total"].apply(rs)
    top["party_z"] = top["party_z"].round(2)
    top["anomaly_score"] = top["anomaly_score"].round(3)
    anomaly_tbl = tbl(top, ["invoice_id", "party", "date", "total", "party_z", "anomaly_score", "issues"],
                      {"invoice_id": "Invoice", "party": "Party", "date": "Date", "total": "Total",
                       "party_z": "Party z-score", "anomaly_score": "Score", "issues": "Also flagged for"})

    e = ev.assign(error_type=ev.error_type.map(LABELS))
    acc_fig = go.Figure()
    acc_fig.add_bar(x=e.error_type, y=(e.precision * 100).round(1),
                    name="Precision (%)", marker_color=PAPER[0])
    acc_fig.add_bar(x=e.error_type, y=(e.recall * 100).round(1),
                    name="Recall (%)", marker_color=PAPER[1])
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
    if ev_base is not None:
        cmp = ev[["error_type", "precision", "recall"]].merge(
            ev_base[["error_type", "precision", "recall"]], on="error_type",
            suffixes=(" (full)", " (exact only)"))
    else:
        cmp = ev[["error_type", "precision", "recall"]].rename(
            columns={"precision": "precision (full)", "recall": "recall (full)"})
        cmp["precision (exact only)"] = cmp["recall (exact only)"] = 0.0
    cmp["error_type"] = cmp.error_type.map(LABELS)
    cmp_tbl = tbl(cmp.assign(**{c: cmp[c].apply(pct) for c in cmp.columns if c != "error_type"}),
                  rename={"error_type": "Error type"})
    kinds = ["All"] + sorted(set(flags.error_type.map(LABELS).dropna()))
    fuzzy_count = int((inv.match == "fuzzy").sum())
    example = pick_example(res, truth)

    return render_template(
        "index.html", n=n, rate=int(rate * 100), seed=seed,
        kpis=kpis, donut=donut, bars=bars, flagged=flagged, total_filtered=total_filtered,
        kinds=kinds, kind=kind, q=q,
        tax_kpis=tax_kpis, gst=gst, monthly=monthly, hist=hist, scat=scat, anomaly_tbl=anomaly_tbl,
        accuracy=accuracy, acc_tbl=acc_tbl, cmp_tbl=cmp_tbl, fuzzy_count=fuzzy_count,
        elapsed=round(elapsed, 2), example=example, active=active)


@app.route("/download/<kind>")
def download(kind):
    n = request.args.get("n", 3000, type=int)
    rate = request.args.get("rate", 10, type=int) / 100
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


def _open_browser():
    threading.Timer(1.2, lambda: webbrowser.open_new("http://127.0.0.1:5000/")).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    if port == 5000:
        _open_browser()
    app.run(host="0.0.0.0", port=port, debug=False)

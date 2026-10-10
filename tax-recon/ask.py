"""Ask the Ledger: questions about the loaded reconciliation run, answered only from its data.

With ANTHROPIC_API_KEY set (in the environment or a .env file next to this module), Claude answers free-form
questions by calling read-only tools over the run. Without a key, the suggested questions are still answered
directly from the same tools, and anything else gets an honest "needs the AI assistant" reply.
"""
import json
import os
import pathlib
import re

import pandas as pd

import ledger as L

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")
ID_RE = re.compile(r"\b(INV-\d{3,5}(?:-R)?|T\d{6})\b", re.I)


def load_env():
    """Read KEY=VALUE lines from .env (next to this file, then the repo root) without overriding real env vars."""
    here = pathlib.Path(__file__).resolve().parent
    for path in (here / ".env", here.parent / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ai_enabled():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


# ---------------------------------------------------------------- tools (read-only views over one run)

def _rows(df, cols):
    return [{c: (v if not (isinstance(v, float) and v != v) else None) for c, v in zip(cols, r)} for r in df[cols].itertuples(index=False)]


def t_overview(ctx):
    res, ev = ctx["res"], ctx["ev"]
    inv, flags = res["inv"], L.flag_rows(res)
    st = inv.status.value_counts().to_dict()
    by = flags.groupby("problem").agg(count=("key", "size"), stake=("stake", "sum")).reset_index()
    b = L.tax_breakdown(res)
    return {
        "data": "Synthetic demo data with planted errors (not a real client's books).",
        "run": ctx["run"], "period": b["period"],
        "invoices": len(inv), "status_counts": st, "orphan_payments": len(res["orphans"]),
        "flags_total": len(flags),
        "flags_by_problem": [{"problem": r.problem, "count": int(r.count), "rupees_at_stake": L.rs(r.stake)} for r in by.itertuples()],
        "net_gst_as_filed": L.rupees(b["as_filed"]["net"]), "net_gst_clean": L.rupees(b["clean"]["net"]),
        "output_tax_as_filed": L.rupees(b["as_filed"]["output_tax"]), "itc_as_filed": L.rupees(b["as_filed"]["itc"]),
        "itc_at_risk": L.rupees(b["itc_at_risk"]),
        "excess_tax_charged_on_wrong_gst": L.rupees(b["excess_tax_charged"]),
    }


def t_list_flags(ctx, problem="any", party="", search="", sort="stake", limit=15):
    t = L.filter_flags(L.flag_rows(ctx["res"]), q=search, kind="All" if problem in ("", "any") else problem,
                       party=party, sort=sort)
    total = len(t)
    t = t.head(max(1, min(int(limit or 15), 50))).copy()
    t["date_s"] = t.date.dt.strftime("%d %b %Y").fillna("")
    t["stake_s"] = t.stake.apply(L.rs)
    t["amount_s"] = t.total.apply(L.rs)
    return {"matching_flags": total, "shown": len(t), "sorted_by": sort,
            "rows": _rows(t, ["invoice_id", "problem", "party", "date_s", "amount_s", "expected", "found", "stake_s", "detail"])}


def t_get_record(ctx, record_id):
    d = L.record_detail(ctx["res"], record_id)
    if d is None:
        return {"error": f"No invoice or bank payment with id {record_id!r} in this run."}
    d.pop("hl", None)
    return d


def t_party_summary(ctx, sort="flags", limit=10):
    g = L.party_summary(ctx["res"], sort=sort, limit=max(1, min(int(limit or 10), 30)))
    return {"sorted_by": sort, "parties": [{"party": r.party, "flags": int(r.flags), "rupees_at_stake": L.rs(r.stake),
                                            "problems": r.types} for r in g.itertuples()]}


def t_tax_breakdown(ctx):
    b = L.tax_breakdown(ctx["res"])
    f = lambda t: {k: (L.rupees(v) if k != "invoices" else v) for k, v in t.items()}
    return {"period": b["period"], "as_filed": f(b["as_filed"]), "clean_only": f(b["clean"]),
            "itc_at_risk": L.rupees(b["itc_at_risk"]), "excess_tax_charged": L.rupees(b["excess_tax_charged"]),
            "short_tax_charged": L.rupees(b["short_tax_charged"]), "wrong_gst_invoices": b["wrong_gst_invoices"],
            "by_rate": [{k: (L.rupees(v) if k not in ("rate", "invoices") else v) for k, v in s.items()} for s in b["slabs"]],
            "by_month": [{k: (L.rupees(v) if k != "month" else v) for k, v in m.items()} for m in b["months"]]}


def t_accuracy(ctx):
    ev = ctx["ev"]
    return {"note": "Measured against the answer key of errors the generator planted.",
            "by_error_type": [{"error_type": L.LABELS.get(r.error_type, r.error_type), "planted": int(r.planted),
                               "flagged": int(r.flagged), "correct": int(r.correct),
                               "precision": f"{r.precision * 100:.1f}%", "recall": f"{r.recall * 100:.1f}%"}
                              for r in ev.itertuples()]}


def t_unusual(ctx, limit=10):
    u = L.filter_unusual(L.unusual_rows(ctx["res"])).head(max(1, min(int(limit or 10), 30)))
    return {"marked_unusual_total": int(ctx["res"]["inv"].anomaly.sum()),
            "note": "The ML score is a review queue, not proof of an error.",
            "rows": [{"invoice_id": r.invoice_id, "party": r.party, "amount": L.rs(r.total),
                      "score": round(float(r.anomaly_score), 3), "why": r.why, "also_flagged_for": r.also}
                     for r in u.itertuples()]}


PROBLEMS = ["any"] + [v for k, v in L.LABELS.items() if k != "anomalous_amount"]
TOOLS = [
    {"name": "overview", "description": "Headline numbers for the loaded run: invoice counts by status, number of flags and rupees at stake per problem type, net GST as filed and clean, ITC at risk. Call this first for broad questions.",
     "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    {"name": "list_flags", "description": "Flagged records with expected vs found values, rupees at stake and the reason. Filter by problem type, party name substring or free-text search; sort by stake (default), amount or date.",
     "input_schema": {"type": "object", "properties": {
         "problem": {"type": "string", "enum": PROBLEMS},
         "party": {"type": "string", "description": "Party (vendor/customer) name substring, or empty."},
         "search": {"type": "string", "description": "Free text matched against invoice id, party, GSTIN and reason, or empty."},
         "sort": {"type": "string", "enum": ["stake", "amount", "date"]},
         "limit": {"type": "integer", "description": "1-50"}},
         "required": ["problem", "party", "search", "sort", "limit"], "additionalProperties": False}},
    {"name": "get_record", "description": "One invoice (e.g. INV-1201, INV-2208-R) or bank payment (e.g. T000106): the invoice, the matched bank payment and ledger entry side by side, every flag on it with the reason and a suggested action, and its ML score.",
     "input_schema": {"type": "object", "properties": {"record_id": {"type": "string"}},
                      "required": ["record_id"], "additionalProperties": False}},
    {"name": "party_summary", "description": "Parties ranked by number of flags or by rupees at stake, with the problem types for each.",
     "input_schema": {"type": "object", "properties": {"sort": {"type": "string", "enum": ["flags", "stake"]},
                                                       "limit": {"type": "integer", "description": "1-30"}},
                      "required": ["sort", "limit"], "additionalProperties": False}},
    {"name": "tax_breakdown", "description": "GST totals for the period: taxable sales, output tax, purchases, ITC and net payable, as filed and clean-only; ITC at risk; excess and short tax on wrong-GST invoices; by rate slab and by month.",
     "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    {"name": "accuracy", "description": "Precision and recall of each error check against the planted answer key.",
     "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    {"name": "unusual_invoices", "description": "Invoices the ML model marked unusual, highest score first, with what looks unusual.",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "1-30"}},
                      "required": ["limit"], "additionalProperties": False}},
]
for _t in TOOLS:
    _t["strict"] = True
RUN = {"overview": t_overview, "list_flags": t_list_flags, "get_record": t_get_record, "party_summary": t_party_summary,
       "tax_breakdown": t_tax_breakdown, "accuracy": t_accuracy, "unusual_invoices": t_unusual}
TOOL_LABELS = {"overview": "Run overview", "list_flags": "Flagged records", "get_record": "Record detail",
               "party_summary": "Party summary", "tax_breakdown": "Tax breakdown", "accuracy": "Accuracy report",
               "unusual_invoices": "Unusual invoices"}

SYSTEM = """You are Ask the Ledger, an assistant inside a GST reconciliation tool used by chartered accountants in India.
The loaded data is one reconciliation run: invoices matched to bank payments and ledger entries, with flags for wrong GST, \
amount mismatches, missing payments, missing ledger entries, date shifts, duplicates and payments with no invoice. \
It is synthetic demo data with planted errors, not a real client's books.

Answer only from what the tools return. Every number, invoice id, party name and amount in your answer must come from a \
tool result in this conversation; never estimate or invent figures. If the tools cannot answer the question (for example \
it needs data this run does not contain, such as GSTR-2B, HSN codes or other periods), say plainly that the loaded data \
does not cover it, and say what it can answer instead. For anything general about GST law, say you can only speak to this \
data and the CA should confirm the rule.

Write for a CA: short, specific, invoice ids and rupee amounts as the tools give them (Indian format, L = lakh, Cr = crore). \
Lead with the answer. Use short bullet lists ("- ") for several items and **bold** for key figures; no tables or headings. \
When it helps, end with one line on what to do next."""


def _call(name, args, ctx):
    fn = RUN.get(name)
    if fn is None:
        return {"error": f"Unknown tool {name}"}
    try:
        return fn(ctx, **(args or {}))
    except TypeError as e:
        return {"error": f"Bad arguments for {name}: {e}"}


def ask_ai(question, ctx):
    import anthropic  # imported here so the app runs without the package when AI is off

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": question}]
    used = []
    for _ in range(8):
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=8000, system=SYSTEM, tools=TOOLS, messages=messages,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            return {"answer": "I can't help with that request. Try asking about the loaded invoices, flags or tax totals.",
                    "mode": "ai", "used": used}
        if resp.stop_reason != "tool_use":
            text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
            return {"answer": text or "I couldn't form an answer from the data. Try rephrasing the question.",
                    "mode": "ai", "used": used}
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            out = _call(b.name, b.input, ctx)
            used.append(TOOL_LABELS.get(b.name, b.name))
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, default=str),
                            "is_error": isinstance(out, dict) and "error" in out})
        messages.append({"role": "user", "content": results})
    return {"answer": "That needed more lookups than allowed for one question. Try a narrower question.",
            "mode": "ai", "used": used}


# ---------------------------------------------------------------- answers without the AI (suggested questions)

def _bullets(rows, fmt):
    return "\n".join("- " + fmt(r) for r in rows)


def ask_local(question, ctx):
    q = question.lower()
    m = ID_RE.search(question)
    if m:
        d = t_get_record(ctx, m.group(1).upper())
        if "error" in d:
            return {"answer": d["error"], "mode": "data", "used": ["Record detail"]}
        if not d["flags"]:
            return {"answer": f"**{d['id']}** has no flags in this run: it matched its bank payment and ledger entry"
                              f" (status: {d.get('status', 'matched')}).", "mode": "data", "used": ["Record detail"]}
        lines = [f"**{d['id']}** was flagged {len(d['flags'])} time{'s' if len(d['flags']) > 1 else ''}:"]
        for f in d["flags"]:
            lines.append(f"- **{f['problem']}**: {f['why']}. Expected {f['expected']}, found {f['found']}"
                         + (f", **{f['stake']}** at stake." if f['stake'] else "."))
        lines.append(f"Next: {d['flags'][0]['action']}")
        return {"answer": "\n".join(lines), "mode": "data", "used": ["Record detail"]}
    if "wrong gst" in q or ("gst" in q and "wrong" in q) or "gst error" in q:
        r = t_list_flags(ctx, problem="Wrong GST", limit=10)
        return {"answer": f"**{r['matching_flags']} invoices** charge the wrong GST. Largest tax differences first:\n"
                          + _bullets(r["rows"], lambda x: f"**{x['invoice_id']}** ({x['party']}): expected {x['expected']}, charged {x['found']}, **{x['stake_s']}** difference")
                          + ("\nSee Flagged records, filtered to Wrong GST, for the full list." if r["matching_flags"] > 10 else ""),
                "mode": "data", "used": ["Flagged records"]}
    if "liability" in q or "net gst" in q or "tax payable" in q or "total tax" in q:
        b = t_tax_breakdown(ctx)
        a, c = b["as_filed"], b["clean_only"]
        return {"answer": f"For {b['period']}:\n"
                          f"- As filed: output tax **{a['output_tax']}**, ITC **{a['itc']}**, net GST **{a['net']}**\n"
                          f"- Clean invoices only: output tax {c['output_tax']}, ITC {c['itc']}, net GST **{c['net']}**\n"
                          f"- ITC at risk on unmatched purchases: **{b['itc_at_risk']}**\n"
                          "A negative net means credit carried forward. Tax and liability has the month and rate breakdown.",
                "mode": "data", "used": ["Tax breakdown"]}
    if any(w in q for w in ("vendor", "party", "parties", "supplier", "customer")) and any(w in q for w in ("most", "mismatch", "flag", "top")):
        r = t_party_summary(ctx, sort="flags", limit=8)
        return {"answer": "Parties with the most flags:\n" + _bullets(r["parties"], lambda x: f"**{x['party']}**: {x['flags']} flags, {x['rupees_at_stake']} at stake ({x['problems']})"),
                "mode": "data", "used": ["Party summary"]}
    if "fix" in q or "before filing" in q or "priorit" in q:
        o = t_overview(ctx)
        order = sorted(o["flags_by_problem"], key=lambda x: -x["count"])
        t = L.flag_rows(ctx["res"])
        lines = [f"Before filing, clear the {o['flags_total']} flags in this order of rupees at stake:"]
        stake = t.groupby("error_type").stake.sum().sort_values(ascending=False)
        for code, amt in stake.items():
            n = int((t.error_type == code).sum())
            lines.append(f"- **{L.LABELS[code]}** ({n}, {L.rs(amt) if amt == amt and amt else 'no rupee amount'}): {L.ACTIONS[code]}")
        lines.append(f"ITC at risk until purchases match: **{o['itc_at_risk']}**.")
        return {"answer": "\n".join(lines), "mode": "data", "used": ["Run overview", "Flagged records"]}
    if "unusual" in q or "anomal" in q:
        r = t_unusual(ctx, limit=8)
        return {"answer": f"{r['marked_unusual_total']} invoices are marked unusual (a review queue, not proof). Highest scores:\n"
                          + _bullets(r["rows"], lambda x: f"**{x['invoice_id']}** ({x['party']}, {x['amount']}): {x['why']}"),
                "mode": "data", "used": ["Unusual invoices"]}
    if "accura" in q or "precision" in q or "recall" in q:
        r = t_accuracy(ctx)
        return {"answer": "Against the planted answer key:\n" + _bullets(r["by_error_type"], lambda x: f"**{x['error_type']}**: precision {x['precision']}, recall {x['recall']} ({x['correct']} of {x['planted']} caught)"),
                "mode": "data", "used": ["Accuracy report"]}
    return {"answer": "That question needs the AI assistant, which is off because no ANTHROPIC_API_KEY is set "
                      "(add it to a .env file and restart). Without it I can answer the suggested questions, or "
                      "explain any record if you include its id, e.g. \"Why was INV-1201 flagged?\".",
            "mode": "off", "used": []}


def answer(question, ctx):
    question = (question or "").strip()[:1000]
    if not question:
        return {"answer": "Ask a question about the loaded data.", "mode": "data", "used": []}
    if ai_enabled():
        try:
            import anthropic
        except ImportError:
            out = ask_local(question, ctx)
            out["note"] = "The anthropic package is not installed (pip install -r requirements.txt); this answer comes straight from the data."
            return out
        try:
            return ask_ai(question, ctx)
        except anthropic.AuthenticationError:
            out = ask_local(question, ctx)
            out["note"] = "The API key in .env was rejected; this answer comes straight from the data."
            return out
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as e:
            out = ask_local(question, ctx)
            out["note"] = f"The AI assistant could not be reached ({type(e).__name__}); this answer comes straight from the data."
            return out
    return ask_local(question, ctx)


def suggestions(res):
    t = L.flag_rows(res)
    inv_flags = t[t.kind == "invoice"].sort_values("stake", ascending=False)
    example = inv_flags.invoice_id.iloc[0] if len(inv_flags) else "INV-1201"
    return ["Which invoices have wrong GST?", f"Why was {example} flagged?", "Total tax liability this period?",
            "Which vendors have the most mismatches?", "What should I fix before filing?"]

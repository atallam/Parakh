"""Stock detail, in decision order: verdict first, reference last (plan 12 §5.2; AC-F15.10)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402
from ui import components as UI  # noqa: E402
from ui import thesis_form  # noqa: E402
from ui.page import setup  # noqa: E402

from parakh.render import format as fmt  # noqa: E402
from parakh.services import app_api  # noqa: E402

masked = setup("Stock detail", icon="🔎")
options = app_api.universe_options()
wanted = st.query_params.get("symbol")
default = options.index(wanted) if wanted in options else 0
symbol = st.selectbox("Stock", options, index=default if options else None)
if not symbol:
    st.info("No stocks yet. Run the monthly analysis first.")
    st.stop()
d = app_api.stock_detail(symbol)
if not d.found:
    UI.show(
        UI.error_panel(
            f"No report for {symbol} yet", d.message or "Run `parakh run --mode monthly`."
        )
    )
    st.stop()
v = d.view
pos = v.get("position")

# 1. header
st.markdown(f"### {d.name} · {d.symbol} · {str(d.cap).title()} cap")
q = d.qualitative or {}
latest_read = None
if q.get("status") == "ok":
    items = q.get("thesis_assessments") or []
    worst = next(
        (a["verdict"] for a in items if a["verdict"] in ("BREAKS", "STRESSED")),
        items[0]["verdict"] if items else "NEUTRAL",
    )
    latest_read = UI.concall_pill(str(q.get("call_period", "")), worst)
UI.show(
    UI.verdict_chip(
        d.verdict_now,
        action=v["verdict"].get("action") if d.owned else None,
        prev=d.prev_verdict,
        size="lg",
    )
    + " &nbsp; "
    + UI.thesis_pill(v["thesis"].get("status"))
    + (" &nbsp; " + latest_read if latest_read else "")
    + f' &nbsp; <span class="pk-muted">confidence {v["confidence"]}</span>'
)
if pos:
    UI.show(
        UI.owned_badge(
            weight_pct=pos.get("weight_pct"),
            pnl_pct=pos.get("pnl_pct"),
            masked=True,
            cost_pending=bool(pos.get("cost_pending")),
        )
    )
if v.get("limited_history"):
    st.caption(f"⚠ {v['limited_history']}")

# 2. why
st.markdown("##### Why")
UI.show(UI.evidence_list([x["text"] for x in v["verdict"].get("drivers") or []] or [v["tldr"]]))

# 3. action box
ab = v["action_box"]
st.markdown("##### Action box")
c1, c2, c3, c4 = st.columns(4)
ez = ab.get("entry_zone")
c1.metric("Entry zone", "—" if not ez else f"{fmt.inr(ez[0])} – {fmt.inr(ez[1])}")
c2.metric("Stop", fmt.inr(ab.get("stop")))
fv = ab.get("fair_value")
c3.metric("Fair value", "—" if not fv else f"{fmt.inr(fv['low'])} – {fmt.inr(fv['high'])}")
c4.metric("Suggested action", ab.get("action") or "—")
if ab.get("position_note"):
    st.caption(ab["position_note"])

# 4. scores
st.markdown("##### Scores")
UI.show(
    UI.score_ring(v["scores"]["value"]["score"], label="Value", delta=v["scores"]["value"]["delta"])
    + UI.score_ring(
        v["scores"]["momentum"]["score"], label="Momentum", delta=v["scores"]["momentum"]["delta"]
    )
)

# 5. price context
ch = d.chart or {}
close = ch.get("close") or []
if close:
    st.markdown("##### Price context")
    last = [c for c in close if c is not None]
    fvm = ab.get("fair_value") or {}
    UI.show(
        UI.range_bar(
            low=min(last),
            high=max(last),
            cmp=last[-1],
            fair_low=fvm.get("low"),
            fair_high=fvm.get("high"),
        )
    )
    UI.show(
        UI.sparkline(
            close[-260:],
            dma50=(ch.get("dma50") or [])[-260:],
            dma200=(ch.get("dma200") or [])[-260:],
            width=520,
            height=90,
        )
    )

# 6. thesis
st.markdown("##### Thesis")
front = d.thesis.get("front") or {}
if not front.get("locked"):
    st.info("No thesis yet.")
    if st.button("Add a thesis", key="add-thesis"):
        thesis_form.dialog(d.symbol or "")
else:
    st.caption(f"Original ({front.get('written_on')}): {front['statement']}")
    by_id = {a["item_id"]: a for a in (q.get("thesis_assessments") or [])}
    cells = []
    for n, text in enumerate(front["key_metrics"], 1):
        a = by_id.get(f"KM{n}")
        cells.append(
            {
                "id": f"KM{n}",
                "text": text,
                "status": (a or {}).get("verdict", d.thesis.get("status")),
                "evidence": f"“{a['quote']}”" if a and a.get("quote") else "",
            }
        )
    UI.show(UI.component_grid(cells))
    for n, b in enumerate(front["breakers"], 1):
        a = by_id.get(f"BR{n}")
        kind = "metric rule" if b["check"] == "metric" else "flagged by the concall agent"
        st.markdown(
            f"- **BR{n}** {b['text']} _({kind}{': ' + b['rule'] if b['rule'] else ''})_"
            + (f" → **{a['verdict']}**" if a else "")
        )
    if st.button("Edit thesis", key="edit-thesis"):
        thesis_form.dialog(d.symbol or "")
if q.get("status") == "ok":
    with st.expander(f"Concall read · {q.get('call_period')}"):
        st.write(q.get("summary", ""))
        for g in q.get("guidance", []):
            st.markdown(f"- **{g['statement']}** ({g.get('due') or 'no date'}) — “{g['quote']}”")
        st.caption(
            f"Tone vs last call: {q.get('tone_change', 'NOT_COMPARABLE').replace('_', ' ').title()} {q.get('tone_reason', '')}"
        )
elif q.get("status") == "pending":
    st.caption(q.get("reason", "qualitative pending"))
da = d.devils_advocate
if da and da.get("status") == "ok":
    with st.expander("Devil's advocate: the case against this verdict"):
        for p in da["counter_points"]:
            ev = (
                f"{p['evidence_metric']} = {p['evidence_value']}"
                if p.get("evidence_metric")
                else p.get("document_id", "")
            )
            st.markdown(f"- {p['claim']} _({ev})_")

# 7. checks
st.markdown("##### Checks")
for c in v["checks"]:
    UI.show(UI.check_row(c["name"], c["state"], c["detail"]))
if not v["checks"]:
    st.caption("No checks recorded.")

# 8. events and 9. timeline
st.markdown("##### Upcoming events")
ev = d.events or {}
if ev.get("status") == "unavailable":
    st.caption(ev.get("reason", "Event calendar not available."))
else:
    st.write(ev)
st.markdown("##### Timeline")
UI.show(UI.timeline([{"when": t["period"], "text": t["text"]} for t in d.timeline[::-1]]))

# 10. links
st.divider()
st.caption(f"Full report: {d.report_path} · period {d.period}")

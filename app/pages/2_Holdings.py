"""Holdings: positions, thesis status and the lot editor (plan 12 §5; AC-F15.3, F15.9, F15.13)."""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from ui import components as UI  # noqa: E402
from ui import thesis_form  # noqa: E402
from ui.page import setup  # noqa: E402

from parakh.render import format as fmt  # noqa: E402
from parakh.services import app_api  # noqa: E402
from parakh.services.holdings_editor import LotInput, add_lot  # noqa: E402


def _word(kind: str, value: str) -> str:
    style = UI.status_style(kind, value)
    return style.word if style else value


masked = setup("Holdings", icon="💼")
pos = app_api.holdings(detail=not masked)
if not pos.found or not pos.rows:
    st.info(pos.message or "No holdings loaded yet. Import a CAS statement or add a lot below.")
else:
    missing = [r for r in pos.rows if r.thesis_status == "NOT_SET"]
    if missing:
        UI.show(
            UI.banner(f"{len(missing)} holding(s) without a thesis.", "Pick one below to add it.")
        )
    table = []
    for r in pos.rows:
        row = {
            "Stock": r.symbol,
            "Cap": r.cap.title(),
            "Verdict": _word("verdict", r.verdict),
            "Weight": fmt.pct(r.weight_pct, signed=False),
            "P&L": "cost pending" if r.cost_pending else fmt.pct(r.pnl_pct),
            "LTCG in": "—" if not r.days_to_long_term else f"{r.days_to_long_term} d",
            "Thesis": _word("thesis", r.thesis_status),
        }
        if not masked:
            row.update(
                {
                    "Qty": "—" if r.quantity is None else f"{r.quantity:g}",
                    "Avg cost": fmt.inr(r.avg_cost_inr, decimals=2),
                    "Value": fmt.inr(r.market_value_inr, compact=True),
                    "P&L (₹)": fmt.inr(r.pnl_inr, compact=True),
                }
            )
        table.append(row)
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption(f"Weights are shares of {pos.weight_basis}." if pos.weight_basis else "")

    pick = st.selectbox("Thesis for", [r.symbol for r in pos.rows], key="thesis-pick")
    if st.button("Open thesis form", key="thesis-open"):
        thesis_form.dialog(pick)

st.markdown("#### Add a lot")
writer = app_api.lot_writer()
if writer is None:
    st.info(
        "Lots are stored in Supabase. Set SUPABASE_URL and the service key to enable the editor; until then use `parakh holdings`."
    )
with st.form("lot-form", clear_on_submit=False):
    c1, c2, c3, c4 = st.columns(4)
    isin = c1.text_input("ISIN", placeholder="INE040A01034")
    qty = c2.number_input("Quantity", min_value=0.0, step=1.0)
    price = c3.number_input("Price per share (₹)", min_value=0.0, step=0.05, format="%.2f")
    day = c4.date_input("Trade date", value=dt.date.today())
    go = st.form_submit_button("Add lot", type="primary", disabled=writer is None)
if go:
    try:
        lot = add_lot(writer, LotInput(isin=isin, qty=qty, price_inr=price, trade_date=day))  # type: ignore[arg-type]
        st.success(f"Lot added for {lot.isin}. Add a thesis next.")
    except ValidationError as exc:
        for err in exc.errors():
            st.error(f"{'.'.join(map(str, err['loc'])) or 'lot'}: {err['msg']}")

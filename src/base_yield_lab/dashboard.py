"""
dashboard.py — Streamlit dashboard for Base Yield Lab.

Run from the project root:
    streamlit run src/base_yield_lab/dashboard.py
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Base Yield Lab",
    page_icon="⚡",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOT_LOG = PROJECT_ROOT / "bot.log"
HISTORY_FILE = PROJECT_ROOT / "bot_history.json"


def load_history() -> dict:
    """Read bot_history.json. Return an empty dict if missing."""
    if not HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(HISTORY_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def parse_log(n_lines: int = 500) -> list[dict]:
    """Read the last log lines and parse timestamp, level, and message."""
    if not BOT_LOG.exists():
        return []

    lines = BOT_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
    lines = lines[-n_lines:]

    pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] [\w.]+: (.+)$"
    )

    events = []
    for line in lines:
        match = pattern.match(line)
        if match:
            timestamp_str, level, message = match.groups()
            events.append({"timestamp": timestamp_str, "level": level, "message": message})

    return events


def extract_apy_history(events: list[dict]) -> pd.DataFrame:
    """Build an APY time series from bot log lines."""
    apy_pattern = re.compile(
        r"Aave: ([\d.]+)% APY.*?Compound: ([\d.]+)% APY"
    )

    rows = []
    for event in events:
        match = apy_pattern.search(event["message"])
        if match:
            rows.append(
                {
                    "Timestamp": event["timestamp"],
                    "Aave (%)": float(match.group(1)),
                    "Compound (%)": float(match.group(2)),
                }
            )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df.set_index("Timestamp")


def get_last_state(events: list[dict]) -> dict:
    """Extract the latest known runtime state from the log."""
    state = {
        "aave_apy": None,
        "compound_apy": None,
        "aave_usdc": None,
        "compound_usdc": None,
        "wallet_usdc": None,
        "wallet_eth": None,
        "gas_gwei": None,
        "gas_usd": None,
        "last_decision": None,
        "last_cycle": None,
        "mode": None,
    }

    apy_pattern = re.compile(
        r"Aave: ([\d.]+)% APY, ([\d.]+) USDC \| Compound: ([\d.]+)% APY, ([\d.]+) USDC"
    )
    wallet_pattern = re.compile(
        r"Wallet: ([\d.]+) USDC, ([\d.]+) ETH \| Gas: ([\d.]+) gwei \(\$([\d.]+)\)"
    )
    mode_pattern = re.compile(r"Bot starting in mode: (.+)")
    decision_pattern = re.compile(r"^(DECISION|ALERT|FIREWALL|EXECUTION): (.+)$")

    for event in reversed(events):
        msg = event["message"]

        if state["aave_apy"] is None:
            match = apy_pattern.search(msg)
            if match:
                state["aave_apy"] = float(match.group(1))
                state["aave_usdc"] = float(match.group(2))
                state["compound_apy"] = float(match.group(3))
                state["compound_usdc"] = float(match.group(4))
                state["last_cycle"] = event["timestamp"]

        if state["wallet_usdc"] is None:
            match = wallet_pattern.search(msg)
            if match:
                state["wallet_usdc"] = float(match.group(1))
                state["wallet_eth"] = float(match.group(2))
                state["gas_gwei"] = float(match.group(3))
                state["gas_usd"] = float(match.group(4))

        if state["mode"] is None:
            match = mode_pattern.search(msg)
            if match:
                state["mode"] = match.group(1).strip()

        if state["last_decision"] is None:
            match = decision_pattern.search(msg)
            if match:
                state["last_decision"] = f"{match.group(1)}: {match.group(2)}"

        if all(v is not None for v in state.values()):
            break

    return state


events = parse_log(500)
history = load_history()
state = get_last_state(events)
apy_df = extract_apy_history(events)

col_title, col_controls = st.columns([4, 1])

with col_title:
    mode = state["mode"] or "Waiting for the first cycle..."
    st.title(f"Base Yield Lab — {mode}")
    if state["last_cycle"]:
        st.caption(f"Last recorded cycle: {state['last_cycle']}")
    else:
        st.caption("No data yet. Run `python src/base_yield_lab/main.py` to start the bot.")

with col_controls:
    auto_refresh = st.toggle("Auto-refresh (10s)", value=False)
    if st.button("Refresh now", use_container_width=True):
        st.rerun()

st.divider()

col1, col2, col3, col4 = st.columns(4)

with col1:
    value = f"{state['aave_apy']:.2f}%" if state["aave_apy"] is not None else "N/A"
    st.metric(
        label="Aave V3 APY",
        value=value,
        help="Current annual USDC supply rate on Aave V3 on Base",
    )

with col2:
    value = f"{state['compound_apy']:.2f}%" if state["compound_apy"] is not None else "N/A"
    delta = None
    if state["aave_apy"] is not None and state["compound_apy"] is not None:
        diff = state["compound_apy"] - state["aave_apy"]
        delta = f"{diff:+.2f}% vs Aave"

    st.metric(
        label="Compound III APY",
        value=value,
        delta=delta,
        help="Current annual USDC supply rate on Compound III on Base",
    )

with col3:
    if state["aave_apy"] is not None and state["compound_apy"] is not None:
        if state["aave_apy"] >= state["compound_apy"]:
            best_name = "Aave V3"
            best_apy = state["aave_apy"]
        else:
            best_name = "Compound III"
            best_apy = state["compound_apy"]
        st.metric(
            label="Best Protocol Right Now",
            value=best_name,
            delta=f"{best_apy:.2f}% APY",
        )
    else:
        st.metric(label="Best Protocol Right Now", value="N/A")

with col4:
    total = 0.0
    for key in ("aave_usdc", "compound_usdc", "wallet_usdc"):
        if state[key] is not None:
            total += state[key]

    value = f"$ {total:.2f} USDC" if total > 0 else "N/A"
    st.metric(
        label="Total Capital",
        value=value,
        help="Sum of wallet USDC, Aave deposits, and Compound deposits",
    )

col5, col6, col7, col8 = st.columns(4)

with col5:
    value = f"$ {state['wallet_usdc']:.2f}" if state["wallet_usdc"] is not None else "N/A"
    st.metric(
        label="Wallet USDC",
        value=value,
        help="Idle USDC in the bot wallet that is not yet deposited",
    )

with col6:
    value = f"{state['wallet_eth']:.6f} ETH" if state["wallet_eth"] is not None else "N/A"
    eth_warn = None
    eth_color = "normal"
    if state["wallet_eth"] is not None and state["wallet_eth"] < 0.0001:
        eth_warn = "CRITICAL: top up ETH"
        eth_color = "inverse"

    st.metric(
        label="ETH For Gas",
        value=value,
        delta=eth_warn,
        delta_color=eth_color,
        help="ETH available for gas. Below 0.0001 ETH the bot should stop operating",
    )

with col7:
    value = f"{state['gas_gwei']:.4f} gwei" if state["gas_gwei"] is not None else "N/A"
    sub = f"(~$ {state['gas_usd']:.4f} per operation)" if state["gas_usd"] is not None else ""
    st.metric(
        label="Current Gas Price",
        value=value,
        help=f"Current Base gas price. Estimated cost of a full move: {sub}",
    )

with col8:
    moves = history.get("total_moves_24h", "N/A")
    gas_spent = history.get("total_gas_spent_24h_usd")
    delta_gas = f"$ {gas_spent:.4f} spent on gas" if gas_spent else None
    st.metric(
        label="Moves (24h)",
        value=str(moves),
        delta=delta_gas,
        help="How many times the bot moved funds in the last 24 hours and how much gas it spent",
    )

st.divider()
st.subheader("Current Positions")
col_aave, col_compound, col_wallet = st.columns(3)

with col_aave:
    with st.container(border=True):
        aave_dep = state["aave_usdc"] or 0.0
        aave_apy = state["aave_apy"] or 0.0
        st.markdown("**Aave V3**")
        st.metric("Deposited", f"$ {aave_dep:.2f} USDC")
        annual_yield = aave_dep * aave_apy / 100
        st.caption(f"Estimated annual yield: $ {annual_yield:.2f}")
        st.caption(f"APY: {aave_apy:.4f}%")

with col_compound:
    with st.container(border=True):
        comp_dep = state["compound_usdc"] or 0.0
        comp_apy = state["compound_apy"] or 0.0
        st.markdown("**Compound III**")
        st.metric("Deposited", f"$ {comp_dep:.2f} USDC")
        annual_yield = comp_dep * comp_apy / 100
        st.caption(f"Estimated annual yield: $ {annual_yield:.2f}")
        st.caption(f"APY: {comp_apy:.4f}%")

with col_wallet:
    with st.container(border=True):
        wallet_usdc = state["wallet_usdc"] or 0.0
        st.markdown("**Wallet (idle)**")
        st.metric("Available", f"$ {wallet_usdc:.2f} USDC")
        st.caption("No yield. Capital here should usually be deployed.")
        last_move = history.get("last_move_action", "None")
        st.caption(f"Last move: {last_move}")

st.divider()
st.subheader("APY History")

if not apy_df.empty:
    st.line_chart(
        apy_df,
        color=["#FF6B6B", "#4ECDC4"],
    )
    n_cycles = len(apy_df)
    st.caption(
        f"{n_cycles} recorded cycles. "
        f"Each point represents one {300 // 60}-minute bot cycle."
    )
else:
    st.info(
        "No historical data yet. "
        "The chart will appear automatically after the bot completes a few cycles."
    )

st.divider()
st.subheader("Recent Event Log")

if events:
    recent = list(reversed(events[-30:]))

    for event in recent:
        level = event["level"]
        msg = event["message"]
        ts = event["timestamp"]
        line = f"`{ts}` - {msg}"

        if level == "ERROR" or "FIREWALL BLOCKED" in msg:
            st.error(line)
        elif level == "WARNING" or "ALERT" in msg:
            st.warning(line)
        elif "DECISION: MOVE" in msg or "EXECUTION: SUCCESS" in msg:
            st.success(line)
        elif "DECISION: HOLD" in msg:
            st.text(f"{ts}  {msg}")
        elif "START OF CYCLE" in msg:
            st.markdown(f"---\n`{ts}` - **{msg}**")
        else:
            st.text(f"{ts}  {msg}")
else:
    st.info("bot.log not found. Run the bot to see events here.")

st.divider()

with st.expander("Raw data (bot_history.json)"):
    if history:
        display = dict(history)
        ts_raw = display.get("last_move_timestamp")
        if ts_raw:
            display["last_move_timestamp_readable"] = datetime.fromtimestamp(ts_raw).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        st.json(display)
    else:
        st.info("bot_history.json not found yet.")

with st.expander("Historical APY table (raw DataFrame)"):
    if not apy_df.empty:
        st.dataframe(apy_df, use_container_width=True)
    else:
        st.info("No data yet.")

if auto_refresh:
    placeholder = st.empty()
    for i in range(10, 0, -1):
        placeholder.caption(f"Refreshing in {i}s...")
        time.sleep(1)
    placeholder.empty()
    st.rerun()

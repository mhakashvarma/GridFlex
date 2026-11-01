import sqlite3, numpy as np, pandas as pd, streamlit as st, plotly.graph_objects as go

st.set_page_config("GridFlex", "⚡", layout="wide")
st.markdown("""<style>
.stApp{background:linear-gradient(160deg,#07122b,#0b1f44);color:#e6f1ff}
[data-testid=stSidebar]{background:#061024}
.card{background:#0f2a52;border:1px solid #1d4a7a;border-radius:14px;padding:14px 16px;margin-bottom:10px}
.card h4{margin:0;color:#7fd8c8;font-size:.8rem;font-weight:500}
.card p{margin:2px 0 0;font-size:1.5rem;font-weight:700;color:#fff}
.ok{color:#2ee6a6}.warn{color:#ffc857}.bad{color:#ff6b6b}
h1,h2,h3{color:#e6f1ff}
</style>""", unsafe_allow_html=True)

H = np.arange(24)
TEAL, GREEN, AMBER, RED, BLUE = "#14b8a6", "#2ee6a6", "#ffc857", "#ff6b6b", "#4da3ff"

def card(col, label, val, unit=""):
    col.markdown(f"<div class='card'><h4>{label}</h4><p>{val}<small> {unit}</small></p></div>", unsafe_allow_html=True)

def style(fig, h=340):
    fig.update_layout(template="plotly_dark", height=h, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=-0.2))
    return fig

# ---------------- Sidebar: fleet + event controls ----------------
st.sidebar.markdown("## ⚡ GRIDFLEX")
st.sidebar.caption("Intelligent Power Management for a Sustainable Future")
PAGES = ["Overview Dashboard", "Grid Monitoring", "EV & V2G Management", "Solar & Battery Management",
         "Demand Response", "Peak Event Simulator", "DISCOM & Revenue Management",
         "Prosumer Rewards", "Reports & Analytics"]
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
st.sidebar.markdown("---")
st.sidebar.markdown("**Fleet configuration**")
n_ev = st.sidebar.slider("Connected EVs", 50, 1000, 400, 50)
v2g_pct = st.sidebar.slider("Bidirectional (V2G) %", 0, 100, 40)
bess_kwh = st.sidebar.slider("Stationary BESS (kWh)", 500, 10000, 4000, 500)
solar_kwp = st.sidebar.slider("Rooftop solar (kWp)", 500, 6000, 2500, 250)
flex_kw = st.sidebar.slider("Flexible load (kW)", 200, 3000, 900, 100)
n_pro = st.sidebar.slider("Prosumers", 100, 5000, 1200, 100)
st.sidebar.markdown("**Peak event**")
ev_start, ev_end = st.sidebar.slider("Event window (hour)", 0, 23, (18, 21))
severity = st.sidebar.slider("Extra demand during event %", 0, 40, 15)
target_pct = st.sidebar.slider("Shave target (% below event peak)", 5, 30, 15)

# ---------------- Simulation engine ----------------
def simulate():
    base = 1800 + 700 * np.exp(-((H - 19) ** 2) / 6) + 350 * np.exp(-((H - 10) ** 2) / 10)
    demand = base * np.where((H >= ev_start) & (H <= ev_end), 1 + severity / 100, 1)
    solar = solar_kwp * np.clip(np.sin((H - 6) / 12 * np.pi), 0, None) * 0.8
    before = np.maximum(demand - solar, 0)
    cap = before.max() * (1 - target_pct / 100)
    n_v2g = int(n_ev * v2g_pct / 100)
    bess_e, bess_p = bess_kwh * 0.8, bess_kwh / 2
    v2g_e, v2g_p = n_v2g * 40 * 0.25, n_v2g * 7 * 0.5
    flex = np.zeros(24); bess = np.zeros(24); v2g = np.zeros(24)
    for h in H:
        need = before[h] - cap
        if need <= 0: continue
        f = min(need, flex_kw * 0.6); need -= f
        b = min(need, bess_p, bess_e); bess_e -= b; need -= b
        v = min(need, v2g_p, v2g_e); v2g_e -= v
        flex[h], bess[h], v2g[h] = f, b, v
    after = before - flex - bess - v2g
    rebound = (bess.sum() + v2g.sum()) / 5          # recharge 1-5 AM
    after[1:6] += rebound
    after[ev_start:ev_end + 1] += 0                  # flex load is shed, not shifted
    df = pd.DataFrame(dict(hour=H, demand=demand, solar=solar, before=before, after=after,
                           flex=flex, bess=bess, v2g=v2g))
    return df, n_v2g

df, n_v2g = simulate()
red_kw = df.before.max() - df.after.max()
disp_kwh = df[["flex", "bess", "v2g"]].values.sum()
contract_rate, event_rate, share = 900, 6.0, 0.4           # Rs/kW-month, Rs/kWh, prosumer share
discom_rev = red_kw * contract_rate + disp_kwh * event_rate
prosumer_pool = discom_rev * share

db = sqlite3.connect("gridflex.db", check_same_thread=False)
db.execute("create table if not exists runs(ts text, red_kw real, kwh real, rev real)")
if st.session_state.get("last") != (red_kw, disp_kwh):
    db.execute("insert into runs values(datetime('now'),?,?,?)", (red_kw, disp_kwh, discom_rev))
    db.commit(); st.session_state["last"] = (red_kw, disp_kwh)

def status(pk):
    r = pk / df.before.mean()
    return ("Normal", "ok") if r < 1.2 else ("High demand", "warn") if r < 1.35 else \
           ("Peak demand", "bad") if r < 1.5 else ("Congestion alert", "bad")

st.title("GRIDFLEX")
st.caption(f"{page}")

# ---------------- Pages ----------------
if page == "Overview Dashboard":
    c = st.columns(5)
    card(c[0], "Connected EVs", n_ev); card(c[1], "Bidirectional EVs", n_v2g)
    card(c[2], "Battery capacity", f"{bess_kwh + n_v2g * 40:,.0f}", "kWh")
    card(c[3], "Solar now", f"{df.solar[12]:,.0f}", "kW"); card(c[4], "Prosumers", f"{n_pro:,}")
    c = st.columns(5)
    card(c[0], "Demand (peak hr)", f"{df.demand.max():,.0f}", "kW")
    card(c[1], "Flexible capacity", f"{flex_kw * 0.6 + bess_kwh / 2 + n_v2g * 3.5:,.0f}", "kW")
    card(c[2], "Grid import (peak, after)", f"{df.after.max():,.0f}", "kW")
    card(c[3], "Peak reduction", f"{red_kw:,.0f}", "kW")
    s, cls = status(df.after.max()); before_s, _ = status(df.before.max())
    card(c[4], "Grid status", f"<span class='{cls}'>{s}</span>")
    st.caption(f"Without GridFlex the grid would be in: {before_s}")
    hr = st.slider("Hour of day for live energy flow", 0, 23, ev_start)
    L, g = df.iloc[hr], max(df.after[hr], 0)
    names = ["Grid", "Solar", "Battery", "EV V2G", "Buildings & flexible loads"]
    vals = [g, min(L.solar, L.demand), L.bess, L.v2g, 0]
    fig = go.Figure(go.Sankey(
        node=dict(label=names, color=[BLUE, AMBER, TEAL, GREEN, "#6b7fa8"], pad=20),
        link=dict(source=[0, 1, 2, 3], target=[4] * 4, value=[max(v, .01) for v in vals[:4]],
                  color=["rgba(77,163,255,.4)", "rgba(255,200,87,.4)", "rgba(20,184,166,.4)", "rgba(46,230,166,.4)"])))
    st.plotly_chart(style(fig, 320), use_container_width=True)
    mix = go.Figure(go.Bar(x=["Grid", "Solar", "EV discharge", "BESS discharge"],
                           y=[df.after.sum(), df.solar.sum(), df.v2g.sum(), df.bess.sum()],
                           marker_color=[BLUE, AMBER, GREEN, TEAL]))
    mix.update_layout(title="Daily energy mix (kWh)")
    st.plotly_chart(style(mix, 280), use_container_width=True)
    st.info(f"Resources: {n_ev} EVs • 1 BESS fleet ({bess_kwh} kWh) • {solar_kwp} kWp solar • {flex_kw} kW flexible load")

elif page == "Grid Monitoring":
    c = st.columns(4)
    card(c[0], "Current demand", f"{df.demand[19]:,.0f}", "kW"); card(c[1], "Peak after GridFlex", f"{df.after.max():,.0f}", "kW")
    card(c[2], "Renewable share", f"{df.solar.sum() / df.demand.sum() * 100:.1f}", "%")
    card(c[3], "Congestion", status(df.before.max())[0])
    f = go.Figure([go.Scatter(x=H, y=df.demand, name="Demand", line=dict(color=BLUE)),
                   go.Scatter(x=H, y=df.solar, name="Solar", fill="tozeroy", line=dict(color=AMBER))])
    f.update_layout(title="Demand & renewable generation (24h)"); st.plotly_chart(style(f), use_container_width=True)
    f = go.Figure([go.Scatter(x=H, y=df.before, name="Before GridFlex", line=dict(color=RED)),
                   go.Scatter(x=H, y=df.after, name="After GridFlex", line=dict(color=GREEN))])
    f.update_layout(title="Grid import before vs after"); st.plotly_chart(style(f), use_container_width=True)
    pk = go.Figure(go.Bar(x=["Before", "After"], y=[df.before.max(), df.after.max()], marker_color=[RED, GREEN]))
    pk.update_layout(title="Peak demand comparison (kW)"); st.plotly_chart(style(pk, 260), use_container_width=True)
    st.warning(f"WARNING: High electricity demand detected between {ev_start}:00 and {ev_end + 1}:00. "
               "Recommended: activate demand response, BESS discharge and V2G dispatch.")

elif page == "EV & V2G Management":
    rng = np.random.default_rng(1)
    n = min(n_ev, 60)
    ev = pd.DataFrame(dict(charger=[f"CP-{i:03d}" for i in range(n)],
                           mode=np.where(np.arange(n) < n * v2g_pct / 100, "V2G (bidirectional)", "G2V only"),
                           soc=rng.integers(25, 100, n), ocpp=rng.choice(["Available", "Charging", "Discharging", "Preparing"], n)))
    c = st.columns(3); card(c[0], "V2G EVs", n_v2g); card(c[1], "Dispatchable EV power", f"{df.v2g.max():,.0f}", "kW")
    card(c[2], "EV energy discharged", f"{df.v2g.sum():,.0f}", "kWh")
    f = go.Figure(go.Bar(x=H, y=df.v2g, marker_color=GREEN)); f.update_layout(title="V2G discharge by hour (kW)")
    st.plotly_chart(style(f), use_container_width=True)
    st.markdown("**Mock OCPP telemetry** (simulated, first 60 chargers)")
    st.dataframe(ev, use_container_width=True, height=300)

elif page == "Solar & Battery Management":
    soc = 0.9 * bess_kwh - np.cumsum(df.bess) + np.where(np.isin(H, range(1, 6)), (df.bess.sum() / 5), 0).cumsum()
    f = go.Figure([go.Scatter(x=H, y=df.solar, name="Solar (kW)", fill="tozeroy", line=dict(color=AMBER)),
                   go.Bar(x=H, y=df.bess, name="BESS discharge (kW)", marker_color=TEAL)])
    f.update_layout(title="Solar output and battery dispatch"); st.plotly_chart(style(f), use_container_width=True)
    f = go.Figure(go.Scatter(x=H, y=np.clip(soc, 0, bess_kwh) / bess_kwh * 100, line=dict(color=TEAL), fill="tozeroy"))
    f.update_layout(title="BESS state of charge (%)"); st.plotly_chart(style(f, 280), use_container_width=True)

elif page == "Demand Response":
    c = st.columns(3); card(c[0], "Flexible capacity", f"{flex_kw:,}", "kW")
    card(c[1], "Load curtailed", f"{df.flex.sum():,.0f}", "kWh"); card(c[2], "Max shed", f"{df.flex.max():,.0f}", "kW")
    f = go.Figure([go.Bar(x=H, y=df.flex, name="Flex load shed", marker_color=BLUE),
                   go.Bar(x=H, y=df.bess, name="BESS", marker_color=TEAL), go.Bar(x=H, y=df.v2g, name="V2G", marker_color=GREEN)])
    f.update_layout(barmode="stack", title="Dispatch priority: flex load → BESS → V2G")
    st.plotly_chart(style(f), use_container_width=True)

elif page == "Peak Event Simulator":
    st.write("Adjust the event window, severity and target in the sidebar; every page updates live.")
    if st.button("▶ Run peak event", type="primary"):
        bar = st.progress(0)
        for i in range(100): bar.progress(i + 1)
        st.success(f"Event {ev_start}:00–{ev_end + 1}:00 dispatched.")
    c = st.columns(4); card(c[0], "Peak before", f"{df.before.max():,.0f}", "kW"); card(c[1], "Peak after", f"{df.after.max():,.0f}", "kW")
    card(c[2], "Reduction", f"{red_kw:,.0f}", "kW"); card(c[3], "Energy dispatched", f"{disp_kwh:,.0f}", "kWh")
    f = go.Figure([go.Scatter(x=H, y=df.before, name="Before", line=dict(color=RED)),
                   go.Scatter(x=H, y=df.after, name="After", line=dict(color=GREEN), fill="tonexty")])
    f.add_vrect(x0=ev_start, x1=ev_end, fillcolor=AMBER, opacity=.12, line_width=0)
    st.plotly_chart(style(f), use_container_width=True)

elif page == "DISCOM & Revenue Management":
    st.caption("Model: bilateral flexibility contract. DISCOMs pay; prosumers pay nothing.")
    c = st.columns(3); card(c[0], "Capacity payment", f"₹{red_kw * contract_rate:,.0f}", "/month")
    card(c[1], "Event energy payment", f"₹{disp_kwh * event_rate:,.0f}"); card(c[2], "GridFlex gross revenue", f"₹{discom_rev:,.0f}")
    c = st.columns(2); card(c[0], "Shared with prosumers (40%)", f"₹{prosumer_pool:,.0f}")
    card(c[1], "GridFlex net (60%)", f"₹{discom_rev - prosumer_pool:,.0f}")
    f = go.Figure(go.Bar(x=["Flex contracts (now)", "EV flexibility*", "Energy market*", "Ancillary services*"],
                         y=[discom_rev, discom_rev * .3, discom_rev * .4, discom_rev * .25], marker_color=[GREEN, TEAL, TEAL, TEAL]))
    f.update_layout(title="Revenue roadmap (illustrative)"); st.plotly_chart(style(f, 300), use_container_width=True)
    st.caption("*Future streams, subject to regulation and market access.")

elif page == "Prosumer Rewards":
    rng = np.random.default_rng(7); n = min(n_pro, 25)
    w = rng.dirichlet(np.ones(n)); pr = pd.DataFrame(dict(
        prosumer=[f"P-{i:04d}" for i in range(n)], asset=rng.choice(["EV+V2G", "Solar+BESS", "Flex load"], n),
        verified_kWh=(w * disp_kwh).round(1), bill_discount_INR=(w * prosumer_pool).round(0))).sort_values("bill_discount_INR", ascending=False)
    c = st.columns(3); card(c[0], "Participants", f"{n_pro:,}"); card(c[1], "Reward pool", f"₹{prosumer_pool:,.0f}")
    card(c[2], "Avg per prosumer", f"₹{prosumer_pool / n_pro:,.0f}")
    st.dataframe(pr, use_container_width=True)

elif page == "Reports & Analytics":
    runs = pd.read_sql("select * from runs order by ts desc limit 20", db)
    st.dataframe(runs, use_container_width=True)
    st.download_button("Download hourly results (CSV)", df.round(1).to_csv(index=False), "gridflex_results.csv")
    st.dataframe(df.round(1), use_container_width=True, height=300)

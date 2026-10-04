import os
import sqlite3

import pandas as pd
import streamlit as st
from asset_geography import european_status
from fundamentals import render_fundamentals

from pathlib import Path

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data.db")


LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "screener-financier-pro-logo.png")

st.set_page_config(page_title="Screener Financier Pro (Fondamental & Technique)", page_icon=LOGO_PATH, layout="wide")
st.logo(LOGO_PATH, size="large")
with st.container(horizontal=True, vertical_alignment="center"):
    st.image(LOGO_PATH, width=80)
    st.title("Screener Global : Fondamentaux & Technique")

st.warning("⚠️ **Avertissement :** Ce screener ne constitue en aucun cas un conseil en investissement. !!! NOT FINANCIAL ADVICE !!!")


@st.cache_data(max_entries=1)
def load_stocks(database_mtime_ns):
    del database_mtime_ns
    with sqlite3.connect(Path(DB_NAME).as_uri() + "?mode=ro", uri=True) as conn:
        try:
            return pd.read_sql("SELECT * FROM stocks", conn)
        except Exception:
            return pd.DataFrame()


st.sidebar.header("🔎 Filtres de Sélection")
search_query = st.sidebar.text_input("Rechercher un actif (Ticker ou Nom)", "").strip().upper()
min_upside = st.sidebar.slider("Potentiel de hausse min (%)", -20.0, 100.0, 40.0)
max_pe = st.sidebar.slider("P/E Ratio max", 0.0, 100.0, 30.0)
min_market_cap = st.sidebar.number_input("Capitalisation minimale (Mds)", min_value=0.0, value=0.1, step=0.1)
st.sidebar.markdown("---")
st.sidebar.subheader("📉 Filtres Techniques")
max_rsi = st.sidebar.slider("RSI Max (14 jours)", 0.0, 100.0, 50.0)
sma50_min, sma50_max = st.sidebar.slider(
    "Écart à la SMA50 (%)", -100.0, 100.0, (-20.0, 20.0),
    help="Écart entre le cours et sa moyenne sur 50 séances. Négatif : sous la SMA50 ; positif : au-dessus.",
)
st.sidebar.markdown("---")
st.sidebar.subheader("🧠 Sentiment & Révisions")
recommendation_labels = {
    "strong_buy": "Strong buy", "buy": "Buy", "hold": "Hold",
    "sell": "Sell", "strong_sell": "Strong sell",
}
selected_recommendations = st.sidebar.multiselect(
    "Recommandations des analystes", list(recommendation_labels),
    default=["strong_buy", "buy"], format_func=recommendation_labels.get,
    help="Sélectionnez un ou plusieurs avis. Sélection vide : tous les avis, y compris ceux non disponibles.",
)
min_eps_growth = st.sidebar.slider("Croissance EPS Prévue Min (%)", -50.0, 100.0, -0.5)

if not os.path.exists(DB_NAME):
    st.warning("⚠️ Fichier market_data.db absent. Il doit être ajouté au dossier de la version en ligne.")
    st.stop()

df = load_stocks(os.stat(DB_NAME).st_mtime_ns)
if df.empty:
    st.warning("⚠️ Table 'stocks' vide ou illisible. Veuillez fournir un fichier market_data.db valide.")
    st.stop()

if "last_updated" in df.columns:
    st.caption(f"🕒 Données synchronisées : **{df['last_updated'].iloc[0]}**")
if "market_cap_billion" not in df.columns:
    df["market_cap_billion"] = 0.0
    st.sidebar.warning("La capitalisation n’est pas renseignée dans le fichier de données fourni.")

scored_universe = df.copy()
scored_universe["Europe"] = [
    european_status(row.get("country"), row.get("ticker", ""))
    for row in scored_universe.to_dict("records")
]
europe_filter = st.sidebar.multiselect(
    "Zone géographique", sorted(scored_universe["Europe"].unique()),
    help="Sélection vide : toutes les zones. Le pays ne garantit pas l'éligibilité au PEA.",
)
for col in ("upside", "roe", "eps_growth_forecast", "rsi", "sma_50_dist"):
    if col in scored_universe.columns:
        scored_universe[col] = scored_universe[col].fillna(0)
scored_universe["Score upside (30)"] = scored_universe["upside"].rank(pct=True) * 30
scored_universe["Score ROE (25)"] = scored_universe["roe"].rank(pct=True) * 25
scored_universe["Score EPS (25)"] = scored_universe["eps_growth_forecast"].rank(pct=True) * 25

def score_rsi_func(val):
    if 40 <= val <= 65:
        return 1.0
    if 30 <= val < 40 or 65 < val <= 75:
        return 0.6
    return 0.2

scored_universe["Score RSI (10)"] = scored_universe["rsi"].apply(score_rsi_func) * 10
scored_universe["Score SMA (10)"] = scored_universe["sma_50_dist"].apply(lambda value: 1.0 if 0 <= value <= 20 else 0.5 if value < 0 else 0.7) * 10
score_columns = ["Score upside (30)", "Score ROE (25)", "Score EPS (25)", "Score RSI (10)", "Score SMA (10)"]
scored_universe["Score Global"] = scored_universe[score_columns].sum(axis=1).round(1)

filtered_df = scored_universe[
    (scored_universe["upside"] >= min_upside)
    & (scored_universe["pe_ratio"] <= max_pe)
    & (scored_universe["market_cap_billion"] >= min_market_cap)
    & (scored_universe["rsi"] <= max_rsi)
    & (scored_universe["eps_growth_forecast"] >= min_eps_growth)
].copy()
if selected_recommendations:
    filtered_df = filtered_df[filtered_df["recommendation"].isin(selected_recommendations)].copy()
filtered_df = filtered_df[filtered_df["sma_50_dist"].between(sma50_min, sma50_max)].copy()
if search_query:
    filtered_df = filtered_df[
        filtered_df["ticker"].str.contains(search_query, case=False, na=False)
        | filtered_df["name"].str.upper().str.contains(search_query, na=False)
    ]
filtered_df = filtered_df.sort_values("Score Global", ascending=False)
if europe_filter:
    filtered_df = filtered_df[filtered_df["Europe"].isin(europe_filter)]

screener_tab, fundamentals_tab = st.tabs(["Screener", "Fondamentaux"], on_change="rerun", key="main_tabs")

with screener_tab:
    col1, col2 = st.columns(2)
    col1.metric("Actifs totaux", len(df))
    col2.metric("Actifs sélectionnés", len(filtered_df))

    if filtered_df.empty:
        st.info("Aucun actif ne correspond à vos filtres actuels.")
    else:
        df_scored = filtered_df.reset_index(drop=True).copy()

        def color_recommendation(val):
            if val in ("strong_buy", "buy"):
                return "color: #2ecc71; font-weight: bold;"
            if val in ("strong_sell", "sell"):
                return "color: #e74c3c; font-weight: bold;"
            return "color: #f1c40f; font-weight: bold;"

        def color_sma_50(val):
            if 0 <= val <= 20:
                return "color: #2ecc71; font-weight: bold;"
            if val > 20:
                return "color: #f39c12; font-weight: bold;"
            return "color: #e74c3c; font-weight: bold;"

        def color_rsi(val):
            if 40 <= val <= 65:
                return "color: #2ecc71; font-weight: bold;"
            if 30 <= val < 40 or 65 < val <= 75:
                return "color: #f39c12; font-weight: bold;"
            return "color: #e74c3c; font-weight: bold;"

        display_df = df_scored.drop(
            columns=["sentiment_score", *score_columns[:-1]], errors="ignore"
        ).reset_index(drop=True)
        display_df.insert(1, "Europe", display_df.pop("Europe"))
        display_df = display_df.drop(columns=["last_updated", "country", "Score SMA (10)", "Europe"], errors="ignore")
        styled_df = display_df.style.background_gradient(subset=["Score Global"], cmap="Greens").background_gradient(subset=["upside"], cmap="RdYlGn").background_gradient(subset=["roe"], cmap="Blues").background_gradient(subset=["eps_growth_forecast"], cmap="Purples").map(color_recommendation, subset=["recommendation"]).map(color_sma_50, subset=["sma_50_dist"]).map(color_rsi, subset=["rsi"]).format({"Score Global": "{:.1f} / 100", "price": "{:.2f} $", "target_price": "{:.2f} $", "upside": "{:+.2f}%", "analysts": "{:.0f}", "market_cap_billion": "{:.2f} Md", "pe_ratio": "{:.2f}", "roe": "{:.2f}%", "eps_growth_forecast": "{:+.2f}%", "rsi": "{:.1f}", "sma_50_dist": "{:+.2f}%"})
        selection = st.dataframe(
            styled_df, width="stretch", height=500,
            on_select="rerun", selection_mode="single-row", key="asset_table",
        )
        if screener_tab.open and selection.selection.rows:
            st.session_state["fundamental_asset"] = display_df.iloc[selection.selection.rows[0]]["ticker"]
        st.caption("Sélectionnez une ligne, puis ouvrez l’onglet Fondamentaux pour consulter la fiche de l’actif.")


with fundamentals_tab:
    if fundamentals_tab.open:
        render_fundame

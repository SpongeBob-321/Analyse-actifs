from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=900, max_entries=20)
def load_stock_overview(ticker):
    def fetch(key, getter):
        try:
            return key, getter(yf.Ticker(ticker)), None
        except Exception:
            return key, {} if key == "info" else pd.DataFrame(), key

    requests = {
        "info": lambda stock: stock.info,
        "history": lambda stock: stock.history(period="1y", auto_adjust=True, timeout=15),
        "recommendations": lambda stock: stock.recommendations_summary,
    }
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        results = list(pool.map(lambda item: fetch(*item), requests.items()))
        data = {key: value for key, value, _ in results}
        errors = [error for _, _, error in results if error]
    return data, errors


@st.cache_data(ttl=900, max_entries=40)
def load_income_statement(ticker, quarterly):
    try:
        stock = yf.Ticker(ticker)
        return stock.quarterly_income_stmt if quarterly else stock.income_stmt, None
    except Exception:
        return pd.DataFrame(), "income"


def load_fundamentals(ticker, quarterly):
    with ThreadPoolExecutor(max_workers=2) as pool:
        overview = pool.submit(load_stock_overview, ticker)
        income = pool.submit(load_income_statement, ticker, quarterly)
        data, errors = overview.result()
        data["income"], income_error = income.result()
    data["updated"] = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M %Z")
    data["errors"] = errors + ([income_error] if income_error else [])
    return data


def number(value, suffix="", digits=2):
    if value is None or pd.isna(value):
        return "N/D"
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",") + suffix


def colored_metric(label, value, color):
    with st.container(border=True):
        st.markdown(label)
        st.markdown(f"### :{color}[{value}]")


def render_fundamentals(universe):
    tickers = universe["ticker"].drop_duplicates().tolist()
    names = universe.drop_duplicates("ticker").set_index("ticker")["name"].to_dict()
    if st.session_state.get("fundamental_asset") not in tickers:
        st.session_state["fundamental_asset"] = tickers[0]
    selected = st.session_state["fundamental_asset"]
    if st.session_state.get("fundamental_asset_selector") != selected:
        st.session_state["fundamental_asset_selector"] = selected

    def select_asset():
        st.session_state["fundamental_asset"] = st.session_state["fundamental_asset_selector"]

    ticker = st.selectbox(
        "Actif", tickers, index=None, key="fundamental_asset_selector",
        format_func=lambda t: f"{t} — {names.get(t, t)}", on_change=select_asset,
    )
    period_col, refresh_col = st.columns([3, 1])
    quarterly = period_col.radio("Compte de résultat", ["Annuel", "Trimestriel"], horizontal=True, key="fundamental_income_period") == "Trimestriel"
    if refresh_col.button("Actualiser la fiche"):
        load_stock_overview.clear(ticker)
        load_income_statement.clear(ticker, quarterly)
    with st.spinner("Chargement des fondamentaux…"):
        data = load_fundamentals(ticker, quarterly)
    info = data["info"]
    if data["errors"]:
        st.warning("Certaines données Yahoo Finance sont indisponibles. Les sections disponibles restent affichées.")
    currency = info.get("currency") or ""
    financial_currency = info.get("financialCurrency") or currency
    history = data["history"]
    st.subheader(f"{ticker} — {info.get('shortName') or names.get(ticker, ticker)}")
    price_col, *financial_cols = st.columns(5)
    price_col.metric("Cours", number(info.get("currentPrice", info.get("regularMarketPrice")), f" {currency}"), icon=":material/paid:", border=True)
    metrics = (("Capitalisation", info.get("marketCap"), f" {currency}"), ("P/E", info.get("trailingPE"), ""), ("BPA", info.get("trailingEps"), f" {currency}"), ("ROE", info.get("returnOnEquity"), "%"))
    for col, (label, value, suffix) in zip(financial_cols, metrics):
        col.metric(label, number(value * 100 if label == "ROE" and value is not None else value, suffix), border=True)
    st.caption(" · ".join(str(info[k]) for k in ("sector", "country") if info.get(k)))

    income = data["income"]
    st.subheader("Compte de résultat")
    if income.empty:
        st.info("Compte de résultat non disponible pour cet actif.")
    else:
        dates = sorted(income.columns)
        table = pd.DataFrame(index=pd.DatetimeIndex(dates))
        for label, field in (("CA", "Total Revenue"), ("Résultat net", "Net Income")):
            table[label] = pd.to_numeric(income.loc[field].reindex(dates), errors="coerce").to_numpy() if field in income.index else float("nan")
        table["Marge nette %"] = table["Résultat net"].div(table["CA"].where(table["CA"] != 0)).mul(100)
        table["Période"] = table.index.strftime("%Y-%m-%d" if quarterly else "%Y")
        amounts = table.melt(id_vars=["Période"], value_vars=["CA", "Résultat net"], var_name="Indicateur", value_name="Montant")
        bars = alt.Chart(amounts.dropna()).mark_bar().encode(
            x=alt.X("Période:N", sort=table["Période"].tolist(), title="Clôture de période"),
            xOffset="Indicateur:N", y=alt.Y("Montant:Q", title=financial_currency or "Montant"),
            color=alt.Color("Indicateur:N", scale=alt.Scale(domain=["CA", "Résultat net"], range=["#478bff", "#41c7d4"])),
            tooltip=["Période:N", "Indicateur:N", alt.Tooltip("Montant:Q", format=",.2f")],
        )
        line = alt.Chart(table).mark_line(color="#f5a623", point=True).encode(
            x=alt.X("Période:N", sort=table["Période"].tolist()),
            y=alt.Y("Marge nette %:Q", title="Marge nette (%)", axis=alt.Axis(orient="right")),
            tooltip=["Période:N", alt.Tooltip("Marge nette %:Q", format=".2f")],
        )
        st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent"), width="stretch", key=f"income_chart_{ticker}_{quarterly}")
        st.caption(f"Comptes en {financial_currency or 'devise non renseignée'} · courbe orange : marge nette (%) · clôtures des périodes")
        with st.expander("Plus d’informations financières"):
            st.dataframe(table.set_index("Période")[["CA", "Résultat net", "Marge nette %"]], width="stretch")

    st.subheader("Performance")
    closes = history["Close"].dropna() if not history.empty and "Close" in history else pd.Series(dtype=float)
    if closes.empty:
        st.info("Historique de cours non disponible.")
    else:
        closes = closes.sort_index()
        closes.index = pd.DatetimeIndex(closes.index).tz_localize(None).normalize()
        last_date, last_price = closes.index[-1], closes.iloc[-1]
        periods = [("1S", last_date - pd.Timedelta(days=7)), ("1M", last_date - pd.DateOffset(months=1)), ("3M", last_date - pd.DateOffset(months=3)), ("6M", last_date - pd.DateOffset(months=6)), ("YTD", pd.Timestamp(last_date.year, 1, 1) - pd.Timedelta(days=1)), ("1A", last_date - pd.DateOffset(years=1))]
        for start in (0, 3):
            for col, (label, date) in zip(st.columns(3), periods[start:start + 3]):
                previous = closes.loc[closes.index <= date]
                change = (last_price / previous.iloc[-1] - 1) * 100 if not previous.empty and previous.iloc[-1] > 0 else None
                color = "gray" if change is None or change == 0 else "green" if change > 0 else "red"
                icon = ":material/help:" if change is None else ":material/trending_up:" if change >= 0 else ":material/trending_down:"
                with col:
                    colored_metric(f"{icon} {label}", "N/D" if change is None else f"{change:+.2f} %".replace(".", ","), color)
        st.caption(f"Clôtures ajustées · dernière séance disponible : {last_date:%d/%m/%Y}")

    st.subheader("Objectifs des analystes")
    labels = {"strong_buy": "Achat fort", "buy": "Achat", "hold": "Conserver", "sell": "Vente", "strong_sell": "Vente forte"}
    recommendation = info.get("recommendationKey")
    recommendation_color = {"strong_buy": "green", "buy": "green", "hold": "blue", "sell": "orange", "strong_sell": "red"}.get(recommendation, "gray")
    st.badge(labels.get(recommendation, "N/D"), icon=":material/insights:", color=recommendation_color)
    col1, col2, col3 = st.columns(3)
    target = info.get("targetMeanPrice")
    price = info.get("currentPrice", info.get("regularMarketPrice"))
    target_color = "gray" if target is None or price is None or pd.isna(target) or pd.isna(price) or price <= 0 or target == price else "green" if target > price else "red"
    with col1:
        colored_metric("Analystes", number(info.get("numberOfAnalystOpinions"), digits=0), "blue")
    with col2:
        colored_metric("Cible moyenne", number(target, f" {currency}"), target_color)
    low, high = info.get("targetLowPrice"), info.get("targetHighPrice")
    with col3:
        colored_metric("Fourchette", f"{number(low)} – {number(high)} {currency}" if low is not None and high is not None else "N/D", "violet")
    st.caption("Cible moyenne : vert au-dessus du cours actuel, rouge en dessous.")
    recommendations = data["recommendations"]
    if not recommendations.empty:
        current = recommendations.loc[recommendations["period"] == "0m"] if "period" in recommendations else pd.DataFrame()
        if not current.empty:
            row = current.iloc[0]
            cols = st.columns(5)
            for col, (key, label) in zip(cols, [("strongBuy", "Achat fort"), ("buy", "Achat"), ("hold", "Conserver"), ("sell", "Vente"), ("strongSell", "Vente forte")]):
                color = {"strongBuy": "green", "buy": "green", "hold": "orange", "sell": "red", "strongSell": "red"}[key]
                with col:
                    colored_metric(label, number(row.get(key), digits=0), color)
    st.caption(f"Yahoo Finance · récupération : {data['updated']} · N/D : donnée non disponible ou non applicable.")

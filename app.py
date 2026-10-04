import os
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

# Nom de la base de données SQLite incluse dans votre dépôt GitHub[cite: 1, 2]
DB_NAME = "market_data.db"

st.set_page_config(
    page_title="Screener Financier Pro (Fondamental & Technique)",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Screener Global : Fondamentaux & Technique")

# --- MESSAGE D'AVERTISSEMENT ---
st.markdown(
    """
    <div style="
        background-color: #4b4e36; 
        border: 1px solid #6b704c; 
        padding: 16px; 
        border-radius: 8px; 
        margin-bottom: 20px;
        color: #f1f5f9;
        font-size: 15px;
    ">
        ⚠️ <b>Avertissement :</b> Ce screener ne constitue en aucun cas un conseil en investissement. !!! NOT FINANCIAL ADVICE !!!
    </div>
    """,
    unsafe_allow_html=True,
)

# --- FILTRES DE SÉLECTION ---
st.sidebar.header("🔎 Filtres de Sélection")

search_query = st.sidebar.text_input("Rechercher un actif (Ticker ou Nom)", "").strip().upper()

min_upside = st.sidebar.slider("Potentiel de hausse min (%)", -20.0, 100.0, 40.0)
max_pe = st.sidebar.slider("P/E Ratio max", 0.0, 100.0, 30.0)

st.sidebar.markdown("---")
st.sidebar.subheader("📉 Filtres Techniques")
max_rsi = st.sidebar.slider("RSI Max (14 jours)", 0.0, 100.0, 50.0)

st.sidebar.markdown("---")
st.sidebar.subheader("🧠 Sentiment & Révisions")
max_sentiment = st.sidebar.slider(
    "Score Sentiment Max (1.0 = Achat, 3.0 = Neutre)", 1.0, 5.0, 2.5
)
min_eps_growth = st.sidebar.slider(
    "Croissance EPS Prévue Min (%)", -50.0, 100.0, -0.5
)

# --- CHARGEMENT ---
if not os.path.exists(DB_NAME):
  st.warning(f"⚠️ Base de données `{DB_NAME}` introuvable. Veuillez uploader le fichier de données à jour sur votre dépôt GitHub[cite: 1, 2].")
else:
  conn = sqlite3.connect(DB_NAME)
  try:
    df = pd.read_sql("SELECT * FROM stocks", conn)
  except Exception:
    df = pd.DataFrame()
  conn.close()

  # --- VÉRIFICATION SI LE DATAFRAME EST VIDE ---
  if df.empty:
    st.warning("⚠️ La base de données existe mais la table 'stocks' est vide.")
  else:
    if "last_updated" in df.columns and not df["last_updated"].isna().all():
      st.caption(f"🕒 Données synchronisées le : **{df['last_updated'].iloc[0]}**")

    # --- SÉCURITÉ COLONNES ---
    if "sentiment_score" not in df.columns:
      df["sentiment_score"] = 3.0
    if "eps_growth_forecast" not in df.columns:
      df["eps_growth_forecast"] = 0.0

    # --- APPLICATION DES FILTRES ---
    filtered_df = df.copy()

    if search_query:
        filtered_df = filtered_df[
            filtered_df["ticker"].str.contains(search_query, na=False)
            | filtered_df["name"].str.upper().str.contains(search_query, na=False)
        ]

    filtered_df = filtered_df[
        (filtered_df["upside"] >= min_upside)
        & (filtered_df["pe_ratio"] <= max_pe)
        & (filtered_df["rsi"] <= max_rsi)
        & (filtered_df["sentiment_score"] <= max_sentiment)
        & (filtered_df["eps_growth_forecast"] >= min_eps_growth)
    ].sort_values(by="upside", ascending=False)

    # --- MÉTRIQUES ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Actifs Total", len(df))
    col2.metric("Actifs Filtrés", len(filtered_df))
    top_upside = (
        f"{filtered_df['upside'].max():.1f}%" if not filtered_df.empty else "N/A"
    )
    col3.metric("Meilleur Potentiel", top_upside)
    avg_rsi = (
        f"{filtered_df['rsi'].mean():.1f}" if not filtered_df.empty else "N/A"
    )
    col4.metric("RSI Moyen (Filtré)", avg_rsi)

    st.markdown("---")

    # --- ONGLETS ---
    tab1, tab2, tab3 = st.tabs(
        ["🎯 Top Opportunités", "📊 RSI vs Potentiel de Hausse", "📋 Matrice GARP"]
    )

    with tab1:
      st.subheader("🎯 Classement Global (Fondamental + Technique optimisé)")
      if not filtered_df.empty:
          
          # --- Calcul du Score Global Fondamental + Technique ---
          df_scored = filtered_df.copy()
          
          # Nettoyage des valeurs manquantes pour le calcul
          for col in ["upside", "roe", "eps_growth_forecast", "rsi", "sma_50_dist"]:
              if col in df_scored.columns:
                  df_scored[col] = df_scored[col].fillna(0)
          
          # Normalisation par percentiles (de 0 à 100 relative au dataset filtré)
          score_upside = df_scored["upside"].rank(pct=True) * 30         # 30% du poids
          score_roe = df_scored["roe"].rank(pct=True) * 25               # 25% du poids
          score_eps = df_scored["eps_growth_forecast"].rank(pct=True) * 25 # 25% du poids
          
          # Score technique RSI (optimal entre 40 et 65)
          def score_rsi_func(val):
              if 40 <= val <= 65: return 1.0
              elif 30 <= val < 40 or 65 < val <= 75: return 0.6
              else: return 0.2
          score_rsi = df_scored["rsi"].apply(score_rsi_func) * 10        # 10% du poids
          
          # Score technique SMA 50 (privilégie les cours au-dessus de la SMA 50)
          score_sma = df_scored["sma_50_dist"].apply(lambda x: 1.0 if 0 <= x <= 20 else (0.5 if x < 0 else 0.7)) * 10 # 10% du poids
          
          # Ajout de la colonne de score global sur 100
          df_scored["Score Global"] = (score_upside + score_roe + score_eps + score_rsi + score_sma).round(1)
          
          # Tri automatique par ordre décroissant du Score Global
          df_scored = df_scored.sort_values(by="Score Global", ascending=False).reset_index(drop=True)

          # Fonction pour colorer les recommandations
          def color_recommendation(val):
              if val in ["strong_buy", "buy"]:
                  return "color: #2ecc71; font-weight: bold;"
              elif val in ["strong_sell", "sell"]:
                  return "color: #e74c3c; font-weight: bold;"
              return "color: #f1c40f; font-weight: bold;"

          # Affichage avec mise en forme et dégradés
          styled_df = (
              df_scored
              .style
              .background_gradient(subset=["Score Global"], cmap="YlOrRd")    # 🔥 Teinte chaude pour le top score global
              .background_gradient(subset=["upside"], cmap="Greens")          # 🟢 Potentiel
              .background_gradient(subset=["roe"], cmap="Blues")              # 🔵 Rentabilité
              .background_gradient(subset=["eps_growth_forecast"], cmap="Purples") # 🟣 Croissance EPS
              .map(color_recommendation, subset=["recommendation"])
              .format({
                  "Score Global": "{:.1f} / 100",
                  "price": "{:.2f} $",
                  "target_price": "{:.2f} $",
                  "upside": "{:+.2f}%",
                  "analysts": "{:.0f}",
                  "pe_ratio": "{:.2f}",
                  "roe": "{:.2f}%",
                  "rsi": "{:.1f}",
                  "sma_50_dist": "{:+.2f}%",
                  "sentiment_score": "{:.2f}",
                  "eps_growth_forecast": "{:+.2f}%",
              })
          )
          
          st.dataframe(styled_df, use_container_width=True, height=500)
      else:
          st.info("Aucun actif ne correspond à vos filtres actuels.")

    with tab2:
      st.subheader("📊 Croisement RSI vs Potentiel de Hausse")
      if not filtered_df.empty:
        plot_df = filtered_df.copy()
        plot_df["bubble_size"] = plot_df["roe"].clip(lower=1).fillna(1)

        fig = px.scatter(
            plot_df,
            x="rsi",
            y="upside",
            size="bubble_size",
            color="recommendation",
            hover_name="name",
            hover_data=[
                "ticker",
                "price",
                "pe_ratio",
                "rsi",
                "sma_50_dist",
                "analysts",
                "eps_growth_forecast",
            ],
            title="Indicateur Technique (RSI) vs Potentiel Fondamental (Upside)",
            labels={
                "rsi": "RSI (14 jours)",
                "upside": "Potentiel de Hausse (%)",
                "recommendation": "Avis Analystes",
            },
            template="plotly_dark",
        )
        fig.add_vline(
            x=30, line_dash="dash", line_color="green", annotation_text="Survente"
        )
        fig.add_vline(
            x=70, line_dash="dash", line_color="red", annotation_text="Surachat"
        )
        st.plotly_chart(fig, use_container_width=True)
      else:
        st.warning("Pas assez de données pour afficher le graphique.")

    with tab3: 
        st.subheader("🎯 Matrice GARP (Croissance vs Valorisation)")
        if not filtered_df.empty:
            viz_df = filtered_df[filtered_df["pe_ratio"] < 100].copy() 
            viz_df["bubble_size"] = viz_df["upside"].clip(lower=1).fillna(1)

            fig = px.scatter(
                viz_df,
                x="eps_growth_forecast",
                y="pe_ratio",
                color="recommendation",
                size="bubble_size",
                hover_name="ticker",
                hover_data=["name", "price", "eps_growth_forecast", "pe_ratio", "upside"],
                title="Analyse GARP : Croissance EPS vs P/E Ratio",
                labels={
                    "eps_growth_forecast": "Croissance EPS Prévue (%)",
                    "pe_ratio": "P/E Ratio",
                },
                template="plotly_dark",
            )
            
            fig.add_hline(y=25, line_dash="dot", line_color="red", annotation_text="P/E Limite (25)")
            fig.add_vline(x=15, line_dash="dot", line_color="green", annotation_text="Croissance Cible (15%)")
            
            st.plotly_chart(fig, use_container_width=True)
            
            st.info("💡 **Comment lire ce graphique :** \n\n"
                    "• **Cadran Bas-Droite (Zone Verte) :** Le 'Sweet Spot'. Croissance élevée pour un prix raisonnable.\n"
                    "• **Cadran Haut-Droite :** Croissance élevée mais très cher (risque de surévaluation).\n"
                    "• **Cadran Bas-Gauche :** Valeurs 'Value' à faible croissance.\n"
                    "• **Cadran Haut-Gauche :** À éviter (croissance faible et cher).")
        else:
            st.warning("Pas assez de données pour afficher la matrice GARP.")

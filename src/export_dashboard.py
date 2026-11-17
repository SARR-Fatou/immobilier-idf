"""Prépare les données du tableau de bord web (docs/data/dashboard.json).

Applique les mêmes règles de nettoyage que le notebook, puis calcule :
  - les indicateurs par département, commune et arrondissement,
  - les paramètres du simulateur d'estimation (médiane de la commune × effet de la surface),
  - un échantillon de ventes pour la carte.

Lancement : python src/export_dashboard.py
"""
import glob
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data", "dashboard.json")
DEPARTEMENTS = {"75": "Paris", "92": "Hauts-de-Seine", "93": "Seine-Saint-Denis", "94": "Val-de-Marne"}
TRANCHES = [(0, 25, "Moins de 25 m²"), (25, 40, "25 à 40 m²"), (40, 60, "40 à 60 m²"),
            (60, 90, "60 à 90 m²"), (90, 10_000, "Plus de 90 m²")]


def charger_et_nettoyer():
    fichiers = sorted(glob.glob(os.path.join(ROOT, "data", "raw", "dvf_2024_*.csv.gz")))
    raw = pd.concat((pd.read_csv(f, dtype={"code_commune": str, "code_departement": str}, low_memory=False)
                     for f in fichiers), ignore_index=True)
    df = raw[raw["nature_mutation"] == "Vente"].copy()
    compo = df.groupby("id_mutation")["type_local"].agg(
        n_appart=lambda s: (s == "Appartement").sum(),
        n_autres=lambda s: s.isin(["Maison", "Local industriel. commercial ou assimilé"]).sum(),
    )
    ids_ok = compo.index[(compo["n_appart"] == 1) & (compo["n_autres"] == 0)]
    df = df[df["id_mutation"].isin(ids_ok) & (df["type_local"] == "Appartement")]
    df = df.dropna(subset=["valeur_fonciere", "surface_reelle_bati", "longitude", "latitude"])
    df = df[(df["surface_reelle_bati"] >= 9) & (df["nombre_pieces_principales"] >= 1)]
    df = df[df["latitude"].between(48.7, 49.0) & df["longitude"].between(2.1, 2.65)]
    df["prix_m2"] = df["valeur_fonciere"] / df["surface_reelle_bati"]
    df = df[df["prix_m2"].between(1500, 35000)]
    bas, haut = df["prix_m2"].quantile([0.01, 0.99])
    df = df[df["prix_m2"].between(bas, haut) & (df["surface_reelle_bati"] <= df["surface_reelle_bati"].quantile(0.995))]
    df["date_mutation"] = pd.to_datetime(df["date_mutation"])
    df["mois"] = df["date_mutation"].dt.month
    df["departement"] = df["code_departement"].map(DEPARTEMENTS)
    df["commune"] = df["nom_commune"].str.replace(" Arrondissement", "", regex=False)
    return df


def main():
    df = charger_et_nettoyer()
    print(f"{len(df)} ventes après nettoyage")

    # Indicateurs par commune / arrondissement (au moins 15 ventes pour être représentatif)
    communes = (df.groupby(["commune", "departement"])
                  .agg(ventes=("prix_m2", "size"), m2=("prix_m2", "median"),
                       q1=("prix_m2", lambda s: s.quantile(.25)), q3=("prix_m2", lambda s: s.quantile(.75)),
                       prix=("valeur_fonciere", "median"), surface=("surface_reelle_bati", "median"),
                       lat=("latitude", "median"), lon=("longitude", "median"))
                  .reset_index())
    communes = communes[communes["ventes"] >= 15].sort_values("commune")

    # Effet de la surface : rapport entre le prix au m² d'une vente et la médiane de sa commune
    med_commune = df.groupby("commune")["prix_m2"].transform("median")
    ratio = df["prix_m2"] / med_commune
    effet_surface = []
    for bas, haut, label in TRANCHES:
        m = df["surface_reelle_bati"].between(bas, haut, inclusive="left")
        effet_surface.append({"min": bas, "max": haut, "label": label, "coef": round(float(ratio[m].median()), 3),
                              "ventes": int(m.sum())})

    departements = (df.groupby("departement")
                      .agg(ventes=("prix_m2", "size"), m2=("prix_m2", "median"),
                           prix=("valeur_fonciere", "median"), surface=("surface_reelle_bati", "median"))
                      .reset_index().sort_values("m2", ascending=False))

    pieces = (df[df["nombre_pieces_principales"] <= 5]
              .groupby(["departement", "nombre_pieces_principales"])["prix_m2"].median().round().unstack(0))
    mensuel = df.groupby("mois").agg(ventes=("prix_m2", "size"), m2=("prix_m2", "median")).reset_index()

    hist_bins = np.arange(2000, 19001, 500)
    hist = {dep: np.histogram(df.loc[df["departement"] == dep, "prix_m2"], bins=hist_bins)[0].tolist()
            for dep in DEPARTEMENTS.values()}

    echantillon = df.sample(min(len(df), 6000), random_state=42)

    with open(os.path.join(ROOT, "figures", "resultats.json"), encoding="utf-8") as f:
        resultats = json.load(f)

    data = {
        "ventes": int(len(df)),
        "periode": "2024",
        "departements": [{k: (round(v) if isinstance(v, float) else v) for k, v in r.items()}
                         for r in departements.to_dict("records")],
        "communes": [{"nom": r["commune"], "dep": r["departement"], "ventes": int(r["ventes"]),
                      "m2": round(r["m2"]), "q1": round(r["q1"]), "q3": round(r["q3"]),
                      "prix": round(r["prix"]), "surface": round(r["surface"]),
                      "lat": round(r["lat"], 4), "lon": round(r["lon"], 4)} for _, r in communes.iterrows()],
        "effet_surface": effet_surface,
        "pieces": {"labels": [int(i) for i in pieces.index],
                   "series": {dep: [None if pd.isna(v) else int(v) for v in pieces[dep]] for dep in pieces.columns}},
        "mensuel": [{"mois": int(r.mois), "ventes": int(r.ventes), "m2": round(r.m2)} for r in mensuel.itertuples()],
        "histogramme": {"bins": hist_bins[:-1].tolist(), "series": hist},
        "points": [[round(r.latitude, 4), round(r.longitude, 4), int(r.prix_m2)] for r in echantillon.itertuples()],
        "modeles": resultats["modeles"],
        "meilleur_modele": resultats["meilleur_modele"],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"écrit : {OUT} ({os.path.getsize(OUT) // 1024} Ko), {len(data['communes'])} communes")


if __name__ == "__main__":
    main()

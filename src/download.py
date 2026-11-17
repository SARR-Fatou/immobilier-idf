"""Télécharge les données DVF 2024 (Demandes de Valeurs Foncières) pour Paris et la petite couronne.

Source : https://files.data.gouv.fr/geo-dvf/ (DGFiP, version géolocalisée par Etalab).
Lancement : python src/download.py
"""
import os
import urllib.request

YEAR = 2024
DEPARTEMENTS = ["75", "92", "93", "94"]
URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{dep}.csv.gz"
RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    for dep in DEPARTEMENTS:
        dest = os.path.join(RAW_DIR, f"dvf_{YEAR}_{dep}.csv.gz")
        if os.path.exists(dest):
            print(f"déjà présent : {dest}")
            continue
        print(f"téléchargement : département {dep}")
        urllib.request.urlretrieve(URL.format(year=YEAR, dep=dep), dest)


if __name__ == "__main__":
    main()

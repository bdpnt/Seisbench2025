import numpy as np
import os
import glob
import matplotlib.pyplot as plt

# -------------------------------
# --- Paramètres ---
# -------------------------------
rep_NLL = "loc"
sortie = "phases"
aecrire = "RESULT/catalogue_raspberry.txt"

# -------------------------------
# --- Nettoyage des fichiers .hdr ---
# -------------------------------
for file in glob.glob(os.path.join(rep_NLL, "*.hdr")):
    os.remove(file)
    print(f"🗑️ Fichier supprimé : {file}")

# -------------------------------
# --- Lecture fichier ligne par ligne ---
# -------------------------------
courant = os.getcwd()
os.chdir(rep_NLL)

fname = sortie + ".sum.grid0.loc.hypo_71"
valid_lines = []

with open(fname, "r") as f:
    # on saute les 2 premières lignes comme avec skiprows
    for _ in range(2):
        next(f)

    for line in f:
        parts = line.strip().split()
        # Vérifie si la ligne contient un "E" (genre "1.23E+03") ou un nombre de colonnes ≠ 16
        if any("E" in p.upper() for p in parts) or len(parts) < 16:
            print(f"⚠️ Ligne ignorée (mauvais format) : {line.strip()}")
            continue
        valid_lines.append(parts[:16])

# Conversion en numpy array
data = np.array(valid_lines)

# Extraction colonnes
Date = data[:, 0]
heuremin = data[:, 1].astype(float)
ssss = data[:, 2].astype(float)
lat = data[:, 3].astype(float)
latmin = data[:, 4].astype(float)
lon = data[:, 5].astype(float)
lonmin = data[:, 6].astype(float)
prof = data[:, 7].astype(float)
mag = data[:, 8].astype(float)
no = np.nan_to_num(data[:, 9].astype(float))
dm = np.nan_to_num(data[:, 10].astype(float))
gap = np.nan_to_num(data[:, 11].astype(float))
m = np.nan_to_num(data[:, 12].astype(float))
rms = np.nan_to_num(data[:, 13].astype(float))
erh = np.nan_to_num(data[:, 14].astype(float))
erv = np.nan_to_num(data[:, 15].astype(float))

os.chdir(courant)

# -------------------------------
# --- Sauvegarde catalogue ---
# -------------------------------
with open(aecrire, "w") as fid:
    for i in range(len(Date)):
        datestr1 = Date[i]
        heuremin1 = str(int(heuremin[i])).zfill(4)

        if len(heuremin1) <= 2:
            heure1, min1 = 0, int(heuremin1)
        else:
            heure1, min1 = int(heuremin1[:-2]), int(heuremin1[-2:])

        if len(datestr1) == 5:
            datestr1 = "0" + datestr1
        if len(datestr1) == 4:
            datestr1 = "00" + datestr1

        fid.write(
            f"{int(datestr1[0:2])} {int(datestr1[2:4])} {int(datestr1[4:6])} "
            f"{heure1} {min1} {ssss[i]} {lat[i] + latmin[i] / 60} {lon[i] + lonmin[i] / 60} "
            f"{prof[i]} {rms[i]} {no[i]} {erh[i]} {erv[i]} {gap[i]}\n"
        )

print("✅ Catalogue écrit")
print("📊 Stats RMS:", np.mean(rms), "(moyenne),", np.median(rms), "(médiane)")
print("📊 Stats ERH:", np.mean(erh))
print("📊 Stats ERV:", np.mean(erv))

# -------------------------------
# --- Carte des localisations ---
# -------------------------------
plt.figure(figsize=(8, 6))
sc = plt.scatter(
    lon + lonmin / 60,
    lat + latmin / 60,
    c=prof,
    s=(10 - erv + 0.1) * 20,
    cmap="viridis",
    alpha=0.7,
    edgecolor="k",
    vmin=0,
    vmax=15,
)

cbar = plt.colorbar(sc, label="Profondeur (km)")
cbar.set_ticks(np.linspace(0, 15, 6))

stations_file = "stations/GTSRCE.txt"
stations_lat, stations_lon, stations_name = [], [], []
with open(stations_file, "r") as f:
    for line in f:
        if not line.strip() or not line.startswith("GTSRCE"):
            continue
        parts = line.split()
        stations_name.append(parts[1])
        stations_lat.append(float(parts[3]))
        stations_lon.append(float(parts[4]))

plt.scatter(stations_lon, stations_lat, marker="^", color="red",
            s=80, edgecolor="black", label="Stations")

for name, x, y in zip(stations_name, stations_lon, stations_lat):
    plt.text(x + 0.01, y + 0.01, name, fontsize=9, color="red")

plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title("Séismes et stations\nCouleur = profondeur (0–15 km), taille = incertitude ERZ")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

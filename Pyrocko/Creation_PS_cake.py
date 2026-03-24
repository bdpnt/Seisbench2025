#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Calcul des temps d'arrivée P et S avec Cake (modèle Pyrénées) sur une grille profondeur/distance.
Equivalent du script MATLAB original, compatible Pyrocko >=0.15.
"""

import subprocess
import numpy as np
from scipy.io import savemat
import time

# --------------------------
# Paramètres
# --------------------------
save_resultat = True

# Grilles profondeur (km) et distance (km)
depth_vector = np.arange(0, 3.1, 0.5)
distance_vector = np.arange(0, 5, 0.05)

# Matrices résultat
TP = np.full((len(depth_vector), len(distance_vector)), np.nan)
TS = np.full((len(depth_vector), len(distance_vector)), np.nan)

# Cake model et phases
MODEL_FILE = "model_pyreenees.nd"
PHASES = "p,s,P,S"

# --------------------------
# Boucle sur profondeur / distance
# --------------------------
for idepth, depth in enumerate(depth_vector):
    print(f"Processing depth {depth:.3f} km ({idepth+1}/{len(depth_vector)})")
    for idist, distance in enumerate(distance_vector):
        start_time = time.time()

        # Commande Cake
        cmd = [
            "cake", "arrivals",
            "--sdepth", str(depth),
            "--distances", str(distance),
            "--model", MODEL_FILE,
            "--phase", PHASES
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.splitlines()
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Cake failed at depth={depth}, distance={distance}")
            continue

        # Initialisation des arrivées
        ARRP = 1e10
        ARRS = 1e10

        # Parsing des lignes
        for line in lines:
            line = line.strip()
            if len(line) < 50:
                continue

            phase_char = line[41].lower()
            try:
                arrival_time = float(line[14:21])
            except ValueError:
                continue

            if phase_char == 'p':
                ARRP = min(ARRP, arrival_time)
            elif phase_char == 's':
                ARRS = min(ARRS, arrival_time)

        TP[idepth, idist] = ARRP
        TS[idepth, idist] = ARRS

        end_time = time.time()
        print(f"Distance {distance:.3f} km done in {end_time - start_time:.2f}s, TP={ARRP:.3f}, TS={ARRS:.3f}")

# --------------------------
# Grille plus large pour sauvegarde finale
# --------------------------
depth_vector_save = np.arange(0, 51, 1)
distance_vector_save = np.arange(0, 101, 1)

# --------------------------
# Analyse des différences maximales selon décalage distance
# --------------------------
print("\nDifférences maximales TS selon décalage distance:")

max_lag = 100  # nombre de pas de distance à comparer (ex: 10 pas)
for lag in range(1, max_lag + 1):
    max_diff = 0.0
    for idepth in range(len(depth_vector)):
        # Comparer TS[idepth, idist] avec TS[idepth, idist+lag] si possible
        for idist in range(len(distance_vector) - lag):
            diff = abs(TS[idepth, idist + lag] - TS[idepth, idist])
            if diff > max_diff:
                max_diff = diff
    print(f"Décalage distance {lag*0.05} km -> différence max TS = {max_diff:.3f} s")

# --------------------------
# Sauvegarde en .mat
# --------------------------
if save_resultat:
    savemat("TPS_pyrenees.mat", {
        "TP": TP,
        "TS": TS,
        "depth_vector": depth_vector,
        "distance_vector": distance_vector
    })
    print("Fichier TPS_pyrenees.mat écrit avec succès")


import matplotlib.pyplot as plt
import numpy as np

# Créer les grilles pour depth et distance
D, Z = np.meshgrid(distance_vector, depth_vector)  # D = distance, Z = depth

# --------------------------
# Graphique TP
# --------------------------
plt.figure(figsize=(10, 6))
plt.pcolormesh(D, Z, TP, shading='auto', cmap='viridis')
plt.colorbar(label='TP (s)')
plt.xlabel('Distance (km)')
plt.ylabel('Profondeur (km)')
plt.title('Temps d\'arrivée P (TP)')
plt.tight_layout()
plt.show()

# --------------------------
# Graphique TS
# --------------------------
plt.figure(figsize=(10, 6))
plt.pcolormesh(D, Z, TS, shading='auto', cmap='inferno')
plt.colorbar(label='TS (s)')
plt.xlabel('Distance (km)')
plt.ylabel('Profondeur (km)')
plt.title('Temps d\'arrivée S (TS)')
plt.tight_layout()
plt.show()

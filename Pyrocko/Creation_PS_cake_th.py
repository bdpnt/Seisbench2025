
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import numpy as np
import matplotlib.pyplot as plt

MODEL_FILE = "model_pyreenees.nd"

# profondeurs étudiées
depths = [1, 5, 10, 15,20,30]
colors = ["black", "blue", "green","yellow","purple", "red"]

distance_vector = np.arange(0, 100.5, 2)

# --------------------------
# Création modèles ±10%
# --------------------------

def create_velocity_model(input_file, output_file, factor):

    with open(input_file) as f:
        lines = f.readlines()

    new_lines = []

    for line in lines:

        stripped = line.strip()

        # lignes vides ou texte (ex: mantle)
        if stripped == "" or stripped.startswith("#") or stripped.startswith("mantle"):
            new_lines.append(line)
            continue

        parts = line.split()

        # vérifier qu'on a au moins 3 colonnes numériques
        try:
            depth = float(parts[0])
            vp = float(parts[1]) * factor
            vs = float(parts[2]) * factor
        except ValueError:
            new_lines.append(line)
            continue

        # reconstruire la ligne en gardant les autres colonnes
        parts[1] = f"{vp:.4f}"
        parts[2] = f"{vs:.4f}"

        new_line = " ".join(parts) + "\n"
        new_lines.append(new_line)

    with open(output_file, "w") as f:
        f.writelines(new_lines)

create_velocity_model(MODEL_FILE, "model_minus10.nd", 0.95)
create_velocity_model(MODEL_FILE, "model_plus10.nd", 1.05)


# --------------------------
# Fonction calcul arrivals
# --------------------------

def get_arrivals(model, depth, distance):

    cmd = [
        "cake", "arrivals",
        "--sdepth", str(depth),
        "--distances", str(distance),
        "--model", model,
        "--phase", "p,s,P,S"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    ARRP = np.nan
    ARRS = np.nan

    for line in result.stdout.splitlines():

        if len(line) < 50:
            continue

        phase_char = line[41].lower()

        try:
            arrival_time = float(line[14:21])
        except:
            continue

        if phase_char == 'p':
            if np.isnan(ARRP) or arrival_time < ARRP:
                ARRP = arrival_time

        elif phase_char == 's':
            if np.isnan(ARRS) or arrival_time < ARRS:
                ARRS = arrival_time

    return ARRP, ARRS


# --------------------------
# Calcul temps
# --------------------------

models = {
    "ref": MODEL_FILE,
    "minus": "model_minus10.nd",
    "plus": "model_plus10.nd"
}

TP = {m:{} for m in models}
TS = {m:{} for m in models}

for m in models:

    for depth in depths:

        tp = []
        ts = []

        print(f"Model {m} depth {depth}")

        for dist in distance_vector:

            p,s = get_arrivals(models[m], depth, dist)

            tp.append(p)
            ts.append(s)

        TP[m][depth] = np.array(tp)
        TS[m][depth] = np.array(ts)


# --------------------------
# Plot
# --------------------------

plt.figure(figsize=(10,6))

for depth, color in zip(depths, colors):

    tp_ref = TP["ref"][depth]
    ts_ref = TS["ref"][depth]

    tp1 = TP["minus"][depth]
    tp2 = TP["plus"][depth]

    ts1 = TS["minus"][depth]
    ts2 = TS["plus"][depth]
    #print(tp1)
    #print(tp2)
    # bornes correctes
    tp_low = np.minimum(tp1, tp2)
    tp_high = np.maximum(tp1, tp2)

    ts_low = np.minimum(ts1, ts2)
    ts_high = np.maximum(ts1, ts2)

    # bande d'incertitude
    plt.fill_between(distance_vector, tp_low, tp_high,
                     color=color, alpha=0.25)

    #plt.fill_between(distance_vector, ts_low, ts_high,
      #               color=color, alpha=0.25)

    # courbes modèle central
    plt.plot(distance_vector, tp_ref,
             color=color, linestyle='-', linewidth=2,
             label=f"P {depth} km")

    #plt.plot(distance_vector, ts_ref,
    #         color=color, linestyle='--', linewidth=2,
    #         label=f"S {depth} km")

plt.xlabel("Distance (km)")
plt.ylabel("Arrival Time (s)")
plt.title("±5% velocity variation")

# limites des axes
#plt.xlim(20, 100)
plt.ylim(0, 30)

plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()

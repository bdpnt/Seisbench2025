import os
import numpy as np

# -----------------------------
# Paramètres
# -----------------------------


# catalogue IA_lacq
sortie = 'GLOBAL.obs'
aecrire = 'catalogue_GLOBAL_test.txt'

# -----------------------------
# Sauvegarde du dossier courant
# -----------------------------
courant = os.getcwd()

# Aller dans NLL/loc

os.chdir('loc')

# Supprimer les .hdr (équivalent !rm *.hdr)
for f in os.listdir():
    if f.endswith(".hdr"):
        os.remove(f)

# -----------------------------
# Lecture du fichier .hypo_71
# -----------------------------
filename = f"{sortie}.sum.grid0.loc.hypo_71"

Date = []
heuremin = []
ssss = []
lat = []
latmin = []
lon = []
lonmin = []
prof = []
mag = []
no = []
dm = []
gap = []
m = []
rms = []
erh = []
erv = []

with open(filename, 'r') as fid:
    fid.readline()
    fid.readline()

    while True:
        ligne = fid.readline()
        if not ligne:
            break

        try:
            Date.append(ligne[1:7])
            heuremin.append(float(ligne[7:12]))
            ssss.append(float(ligne[12:18]))
            lat.append(float(ligne[18:21]))
            latmin.append(float(ligne[21:27]))
            lon.append(float(ligne[27:31]))
            lonmin.append(float(ligne[31:38]))
            prof.append(float(ligne[38:45]))
            mag.append(float(ligne[47:51]))

            try:
                no.append(float(ligne[52:55]))
                dm.append(float(ligne[55:58]))
                gap.append(float(ligne[58:62]))
                m.append(float(ligne[62:64]))
                rms.append(float(ligne[64:69]))
                erh.append(float(ligne[70:74]))
                erv.append(float(ligne[75:79]))
            except:
                no.append(np.nan)
                dm.append(np.nan)
                gap.append(np.nan)
                m.append(np.nan)
                rms.append(np.nan)
                erh.append(np.nan)
                erv.append(np.nan)

        except:
            continue

# Retour dossier courant
os.chdir(courant)

# -----------------------------
# Ecriture fichier final
# -----------------------------
with open(aecrire, 'w') as fid:

    for i in range(len(Date)):

        datestr1 = Date[i]
        heuremin1 = f"{heuremin[i]:4.0f}"

        if len(heuremin1.strip()) == 1:
            heure1 = 0
            min1 = int(heuremin1)
        elif len(heuremin1.strip()) == 2:
            heure1 = 0
            min1 = int(heuremin1)
        else:
            heure1 = int(heuremin1[:-2])
            min1 = int(heuremin1[-2:])

        if len(datestr1) == 5:
            datestr1 = '0' + datestr1
        if len(datestr1) == 4:
            datestr1 = '00' + datestr1

        year = int(datestr1[0:2])
        month = int(datestr1[2:4])
        day = int(datestr1[4:6])

        latitude = lat[i] + latmin[i] / 60.0
        longitude = lon[i] + lonmin[i] / 60.0

        fid.write(
            f"{year} {month} {day} "
            f"{heure1} {min1} {ssss[i]} "
            f"{latitude} {longitude} {prof[i]} "
            f"{rms[i]} {no[i]} {erh[i]} {erv[i]} {gap[i]}\n"
        )

print("ok")

# -----------------------------
# Statistiques finales
# -----------------------------
rms_arr = np.array(rms)
erh_arr = np.array(erh)
erv_arr = np.array(erv)

print("mean(rms) =", np.nanmean(rms_arr))
print("median(rms) =", np.nanmedian(rms_arr))
print("mean(erh) =", np.nanmean(erh_arr))
print("mean(erv) =", np.nanmean(erv_arr))

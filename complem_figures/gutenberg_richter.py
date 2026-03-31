file_bulletin = '../obs/GLOBAL.obs'
type_mag = 'Mw'
save_file = f'gutenberg_richter/GLOBAL_{type_mag}.png'

# Imports
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Charge bulletin as Dataframe
with open(file_bulletin,'r') as f:
    lines = f.readlines()

bull = [line.lstrip('# ').rstrip('\n').split() for line in lines if line.startswith('# ')]
bull_df = pd.DataFrame(bull, columns=['Year','Month','Day','Hour','Min','Sec','Lat','Lon','Dep','Mag','MagType','MagAuthor','PhaseCount','HorUncer','VerUncer','AzGap','RMS'])
bull_df[['Year','Mag']] = bull_df[['Year','Mag']].apply(pd.to_numeric)

# Cut events after 2019
# bull_df = bull_df[bull_df.Year < 2020]

# Conversion to Mw using laws from Cara et al. [2017]
def ML_to_Mw(mag):
    if mag < 3.117:
        return 0.6642 * mag + 0.4467
    elif mag <= 4:
        return mag - 0.6
    else:
        return 1.4285 * mag - 2.0891

if type_mag == 'Mw':
    bull_df['Mag'] = bull_df.Mag.apply(ML_to_Mw)

# Sort magnitudes in descending order
sorted_mags = np.sort(bull_df.Mag.unique())[::-1]

# Cumulative number of events above each magnitude
cumulative_count = [len(bull_df[bull_df.Mag >= mag]) for mag in sorted_mags]

# Create plot
plt.figure(figsize=(5,6))
sns.scatterplot(
    x=sorted_mags,
    y=cumulative_count,
)
plt.yscale('log')
if type_mag == 'Mw':
    plt.xlabel('Magnitude Mw')
else:
    plt.xlabel('Magnitude ML')
plt.ylabel('N')
plt.title('Gutenberg-Richter law')
plt.xlim(0,6)
plt.ylim(10**0,10**5)
plt.savefig(save_file)
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
from copy import deepcopy

def open_file(file):
    columns = ['year','month','day','hour','minute','second','latitude','longitude','depth','magnitude','rms','no','erh','erv','gap']
    data = pd.read_csv(file, sep=r'\s+', header=None, names=columns)
    data['year'] = np.where(data['year'] > 75, data['year'] + 1900, data['year'] + 2000)
    data['date'] = pd.to_datetime(data[['year', 'month', 'day', 'hour', 'minute', 'second']])
    return data

def match_catalogs(df1, df2, tol_seconds=2):
    cat1 = pd.Series(df1.date)
    cat2 = pd.Series(df2.date)
    
    used = set()
    matches = []

    for i1, t1 in cat1.items():
        start = t1 - pd.Timedelta(seconds=tol_seconds)
        end = t1 + pd.Timedelta(seconds=tol_seconds)
        
        left = cat2.searchsorted(start, side='left')
        right = cat2.searchsorted(end, side='right')
        
        candidate_indices = [i for i in range(left, right) if i not in used]
        
        if len(candidate_indices) == 1:
            i2 = candidate_indices[0]
            matches.append((i1, i2, t1, cat2.iloc[i2]))
            used.add(i2)

    return pd.DataFrame(
        matches,
        columns=["cat1_index", "cat2_index", "cat1_time", "cat2_time"]
    )

def match_df(df1, df2, match):
    idx1 = match.cat1_index.to_list()
    idx2 = match.cat2_index.to_list()

    df1_match = deepcopy(df1)
    df2_match = deepcopy(df2)

    df1_match.iloc[idx1].reset_index()
    df2_match.iloc[idx2].reset_index()

    df_match = pd.DataFrame()

    df_match['gap'] = df1_match.gap
    df_match['rms'] = df1_match.rms
    df_match['no'] = df1_match.no

    df_match['gap_diff'] = df2_match.gap - df1_match.gap
    df_match['rms_diff'] = df2_match.rms - df1_match.rms
    df_match['no_diff'] = df2_match.no - df1_match.no

    return df_match

file_40 = 'RESULT/GLOBAL_W_40.txt'
file_80 = 'RESULT/GLOBAL_W_80.txt'
file_140 = 'RESULT/GLOBAL_W_140.txt'
file_200 = 'RESULT/GLOBAL_W_200.txt'

data_40 = open_file(file_40)
data_80 = open_file(file_80)
data_140 = open_file(file_140)
data_200 = open_file(file_200)

match_40_40 = match_catalogs(data_40,data_40)
match_40_80 = match_catalogs(data_40,data_80)
match_40_140 = match_catalogs(data_40,data_140)
match_40_200 = match_catalogs(data_40,data_200)

df_40_40 = match_df(data_40,data_40,match_40_40)
df_40_80 = match_df(data_40,data_80,match_40_80)
df_40_140 = match_df(data_40,data_140,match_40_140)
df_40_200 = match_df(data_40,data_200,match_40_200)

# FIGURE
fig, axes = plt.subplots(2, 4, sharey='row', figsize=(12, 6))
plt.subplots_adjust(hspace=0.4)

axes = axes.flatten()

# Initiate colormaps
cmap_gap = sns.color_palette("flare", as_cmap=True)
cmap_rms = sns.color_palette("ch:s=.25,rot=-.25", as_cmap=True)

all_df = [df_40_40, df_40_80, df_40_140, df_40_200]

for i,df_i in enumerate(all_df):
    sns.histplot(
        df_i,
        y='gap_diff',
        x='gap',
        bins=50,
        cmap=cmap_gap,
        cbar=False,
        binrange=[(0, 360), (-360, 360)],
        vmin=0,
        vmax=150,
        ax=axes[i]
    )
    axes[i].set_ylabel('Gap Diff. (°)')
    axes[i].set_xlabel('Gap (at 40 km)')
    axes[i].set_yticks([-360, -180, 0, 180, 360])
    axes[i].set_yticklabels(['-360', '-180', '0', '+180', '+360'])
    axes[i].set_xticks([0, 120, 240, 360])
    axes[i].set_xticklabels(['0', '120', '240', '360'])

    sns.histplot(
        df_i,
        y='rms_diff',
        x='rms',
        bins=50,
        cmap=cmap_rms,
        cbar=False,
        binrange=[(0, 0.75), (-1, 1)],
        vmin=0,
        vmax=150,
        ax=axes[i+4]
    )
    axes[i+4].set_ylabel('RMS Diff. (s)')
    axes[i+4].set_xlabel('RMS (at 40 km)')
    axes[i+4].set_yticks([-1.0, -0.5, 0, 0.5, 1.0])
    axes[i+4].set_yticklabels(['-1.00', '-0.50', '0', '+0.50', '+1.00'])
    axes[i+4].set_xticks([0, 0.25, 0.5, 0.75])
    axes[i+4].set_xticklabels(['0', '0.25', '0.5', '0.75'])

# Title per column and annotations
for ID,ax in enumerate(axes[:4]):
    ax.text(
        180,
        420,
        s='Stations under\n' + ['40 km','80 km','140 km','200 km'][ID],
        fontsize=12,
        fontweight='bold',
        horizontalalignment='center',
    )

    ax.text(
        360,
        360,
        s='↑ Loss',
        fontsize=6,
        fontweight='bold',
        horizontalalignment='right',
        verticalalignment='top',
    )

    ax.text(
        360,
        -360,
        s='↓ Gain',
        fontsize=6,
        fontweight='bold',
        horizontalalignment='right',
        verticalalignment='bottom',
    )

for ax in axes[4:]:
    ax.text(
        0.75,
        1,
        s='↑ Loss',
        fontsize=6,
        fontweight='bold',
        horizontalalignment='right',
        verticalalignment='top',
    )

    ax.text(
        0.75,
        -1,
        s='↓ Gain',
        fontsize=6,
        fontweight='bold',
        horizontalalignment='right',
        verticalalignment='bottom',
    )

# "Gap" colorbar
cax_gap = fig.add_axes([0.92, 0.555, 0.01, 0.3])
norm_gap = plt.Normalize(vmin=0, vmax=150)
sm_gap = plt.cm.ScalarMappable(cmap=cmap_gap, norm=norm_gap)
sm_gap.set_array([])
cb_gap = plt.colorbar(sm_gap, cax=cax_gap, ticks=[0, 50, 100, 150])
cb_gap.set_ticklabels(['0', '50', '100', '150+'])

# "RMS" colorbar
cax_rms = fig.add_axes([0.92, 0.135, 0.01, 0.3])
norm_rms = plt.Normalize(vmin=0, vmax=150)
sm_rms = plt.cm.ScalarMappable(cmap=cmap_rms, norm=norm_rms)
sm_rms.set_array([])
cb_rms = plt.colorbar(sm_rms, cax=cax_rms, ticks=[0, 50, 100, 150])
cb_rms.set_ticklabels(['0', '50', '100', '150+'])

plt.savefig('RESULT/FIGURES/Gap_and_RMS.pdf')
plt.close()
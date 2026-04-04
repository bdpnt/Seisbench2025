import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

### PARAMETERS
file_40 = 'RESULT/GLOBAL_W_40.txt'
file_80 = 'RESULT/GLOBAL_W_80.txt'
file_140 = 'RESULT/GLOBAL_W_140.txt'
file_200 = 'RESULT/GLOBAL_W_200.txt'

error = 0 # in km (0 for None)

savefile = f'RESULT/FIGURES/Gap_vs_RMS_{error}.pdf'

### MAIN
def open_file(file):
    columns = ['year','month','day','hour','minute','second','latitude','longitude','depth','magnitude','rms','no','erh','erv','gap']
    data = pd.read_csv(file, sep=r'\s+', header=None, names=columns)
    return data

def cut_error(df, err):
    df = df[df['erh'] <= err]
    df = df[df['erv'] <= err]
    return df

def cut_quantile(df, col, q):
    return df[df[col] <= np.quantile(df[col], q)].copy()

data_40 = open_file(file_40)
data_80 = open_file(file_80)
data_140 = open_file(file_140)
data_200 = open_file(file_200)

if error != 0:
    data_40 = cut_error(data_40, error)
    data_80 = cut_error(data_80, error)
    data_140 = cut_error(data_140, error)
    data_200 = cut_error(data_200, error)

data_40_cut = cut_quantile(data_40, 'rms', 0.99)
data_80_cut = cut_quantile(data_80, 'rms', 0.99)
data_140_cut = cut_quantile(data_140, 'rms', 0.99)
data_200_cut = cut_quantile(data_200, 'rms', 0.99)

## FIGURE
fig, axes = plt.subplots(2, 4, sharex='col', sharey='row', figsize=(12, 6))
axes = axes.T.flatten()

# Initiate colormaps
cmap_rms = sns.color_palette("flare", as_cmap=True)
cmap_no = sns.color_palette("ch:s=.25,rot=-.25", as_cmap=True)

# 40 km
sns.histplot(
    data_40_cut,
    y='rms',
    x='gap',
    bins=50,
    cmap=cmap_rms,
    cbar=False,
    binrange=[(0, 360), (0, 0.75)],
    vmin=0,
    vmax=150,
    ax=axes[0]
)
axes[0].set_ylim(0, 0.75)
axes[0].set_ylabel('RMS', fontsize=12)

sns.histplot(
    data_40,
    y='no',
    x='gap',
    bins=50,
    cmap=cmap_no,
    cbar=False,
    binrange=[(0, 360), (0, 150)],
    vmin=0,
    vmax=150,
    ax=axes[1]
)
axes[1].set_ylim(0, 150)

# 80 km
sns.histplot(
    data_80_cut,
    y='rms',
    x='gap',
    bins=50,
    cmap=cmap_rms,
    cbar=False,
    binrange=[(0, 360), (0, 0.75)],
    vmin=0,
    vmax=150,
    ax=axes[2]
)
axes[2].set_ylim(0, 0.75)
axes[2].set_ylabel('RMS', fontsize=12)

sns.histplot(
    data_80,
    y='no',
    x='gap',
    bins=50,
    cmap=cmap_no,
    cbar=False,
    binrange=[(0, 360), (0, 150)],
    vmin=0,
    vmax=150,
    ax=axes[3]
)
axes[3].set_ylim(0, 150)

# 140 km
sns.histplot(
    data_140_cut,
    y='rms',
    x='gap',
    bins=50,
    cmap=cmap_rms,
    cbar=False,
    binrange=[(0, 360), (0, 0.75)],
    vmin=0,
    vmax=150,
    ax=axes[4]
)
axes[4].set_ylim(0, 0.75)
axes[4].set_ylabel('RMS', fontsize=12)

sns.histplot(
    data_140,
    y='no',
    x='gap',
    bins=50,
    cmap=cmap_no,
    cbar=False,
    binrange=[(0, 360), (0, 150)],
    vmin=0,
    vmax=150,
    ax=axes[5]
)
axes[5].set_ylim(0, 150)

# 200 km
sns.histplot(
    data_200_cut,
    y='rms',
    x='gap',
    bins=50,
    cmap=cmap_rms,
    cbar=False,
    binrange=[(0, 360), (0, 0.75)],
    vmin=0,
    vmax=150,
    ax=axes[6]
)
axes[6].set_ylim(0, 0.75)
axes[6].set_ylabel('RMS', fontsize=12)

sns.histplot(
    data_200,
    y='no',
    x='gap',
    bins=50,
    cmap=cmap_no,
    cbar=False, 
    binrange=[(0, 360), (0, 150)],
    vmin=0,
    vmax=150,
    ax=axes[7]
)
axes[7].set_ylim(0, 150)

# Title per column
for ID,ax in enumerate(axes[::2]):
    ax.text(
        180,
        0.8,
        s=['40 km','80 km','140 km','200 km'][ID],
        fontsize=12,
        fontweight='bold',
        horizontalalignment='center',
    )

# All rows x-axis limits and ticks
for ax in axes:
    ax.set_xlim(0, 360)
    ax.set_xticks([0, 120, 240, 360])

# Top row labels/ticks
for ax in axes[::2]:
    ax.set_ylabel('RMS')
    ax.set_yticks([0, 0.25, 0.5, 0.75])
    ax.set_yticklabels(['0', '.25', '.50', '.75'])

# Bot row labels/ticks
for ax in axes[1::2]:
    ax.set_xlabel('Gap')
    ax.set_ylabel('No. Picks')
    ax.set_yticks([0, 50, 100, 150])
    ax.set_yticklabels(['0', '50', '100', '150'])

# "RMS" colorbar
cax_rms = fig.add_axes([0.92, 0.555, 0.01, 0.3])
norm_rms = plt.Normalize(vmin=0, vmax=150)
sm_rms = plt.cm.ScalarMappable(cmap=cmap_rms, norm=norm_rms)
sm_rms.set_array([])
cb_rms = plt.colorbar(sm_rms, cax=cax_rms, ticks=[0, 50, 100, 150])
cb_rms.set_ticklabels(['0', '50', '100', '150+'])

# "No" colorbar
cax_no = fig.add_axes([0.92, 0.135, 0.01, 0.3])
norm_no = plt.Normalize(vmin=0, vmax=150)
sm_no = plt.cm.ScalarMappable(cmap=cmap_no, norm=norm_no)
sm_no.set_array([])
cb_no = plt.colorbar(sm_no, cax=cax_no, ticks=[0, 50, 100, 150])
cb_no.set_ticklabels(['0', '50', '100', '150+'])

plt.savefig(savefile)
plt.close()
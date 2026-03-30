import pandas as pd
import pygmt as pg

# MAIN
fileStations = '../loc/GLOBAL_C/last.stations'
figSave = 'stations_used/GLOBAL_C.pdf'

#---- Read last.stations file
stations = pd.read_csv(fileStations, header=0, delimiter=' ', names=['Code','x','y','z','Latitude','Longitude','Depth']).drop(columns=['x','y','z'])

#---- Set Pyrenees borders
region = [-2.25,3.5,42,44]

fig = pg.Figure()
with pg.config(MAP_FRAME_TYPE="fancy+"):
    fig.basemap(region=region, projection="M6i", frame='af')
fig.coast(water="skyblue", land='#777777', resolution='i', area_thresh='0/0/1', borders="1/0.75p,black")

#---- Plot events
pg.makecpt(cmap="viridis", series=[0,15,1], reverse=True)
fig.plot(
    x=stations.Longitude,
    y=stations.Latitude,
    style="i0.2c",
    fill='black',
    transparency=30,
)

fig.savefig(figSave, dpi=300)

print(f"Figure succesfully saved @ {figSave}")
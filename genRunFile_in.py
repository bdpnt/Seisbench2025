'''
genRunFile_in generates a new run file in the run/ folder
'''

# CLASS
class Parameters:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        attrs = ', '.join(f"{k}={v}" for k, v in self.__dict__.items())
        return f"Parameters({attrs})"

    def update(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

# FUNCTION
def saveRunFile(parameters):
    lines = []

    # Region coordinates
    lines.append('CONTROL 1 54321\n')
    lines.append(f'TRANS  LAMBERT  WGS-84  {parameters.lat1} {parameters.lon1}  {parameters.lat2} {parameters.lon2} 0.0\n')
    lines.append('\n')

    # Velocity model
    lines.append('# Velocity model\n')
    lines.append(f'VGOUT  {parameters.fileModel}\n')
    lines.append('VGTYPE P\n')
    lines.append('VGGRID  2 9000 800  0.0 0.0 -3  0.05 0.05 0.05  SLOW_LEN\n')
    lines.append('\n')
    lines.append('LAYER    0.0  5.5 0.0       3.2   0.00   2.72 0.0\n')
    lines.append('LAYER    1    5.6 0.0       3.26  0.00  2.7 0.0\n')
    lines.append('LAYER    4    6.1 0.0       3.55  0.00  2.8 0.0\n')
    lines.append('LAYER    11   6.4 0.0       3.72  0.00  2.8 0.0\n')
    lines.append('LAYER    34   8.0 0.00      4.50  0.00  3.32 0.0\n')
    lines.append('\n')
    lines.append(f'GTFILES  {parameters.fileModel}  {parameters.fileTime} P\n')
    lines.append('GTMODE GRID2D ANGLES_NO\n')
    lines.append('\n')

    # Bulletin to read and write
    lines.append('# Bulletin to read and write\n')
    lines.append(f'LOCFILES {parameters.fileBulletinIn} NLLOC_OBS  {parameters.fileTime}  {parameters.fileBulletinOut}\n')
    lines.append('LOCHYPOUT SAVE_HYPO71_SUM\n')
    lines.append('\n')

    # Localization method
    lines.append('# Localization method\n')
    lines.append('LOCGRID 7500 4000 800 0.0 0.0 -3  0.05 0.05 0.05 PROB_DENSITY SAVE\n')
    lines.append('LOCSEARCH  OCT 50 50 5 0.001 50000 500 1 0\n')
    lines.append('LOCMETH EDT_OT_WT 9999 4 -1 -1 1.72 6 -1.0 0\n')
    lines.append('\n')

    # Stations coordinates
    lines.append('# Stations coordinates\n')
    lines.append(f'INCLUDE {parameters.fileStations}\n')
    lines.append('\n')

    # Localization parameters
    lines.append('# Localization parameters\n')
    lines.append('GT_PLFD  1.0e-7  0\n')
    lines.append('LOCGAU 0.05 0.0\n')
    lines.append('LOCGAU2 0.01 0.01 2.0\n')
    lines.append('LOCPHASEID  P   P p G PN PG\n')
    lines.append('LOCPHASEID  S   S s G SN SG\n')
    lines.append('LOCQUAL2ERR 0.05 0.15 0.05 0.15 99999.9\n')
    lines.append('LOCPHSTAT 9999.0 -1 9999.0 1.0 1.0 9999.9 -9999.9 9999.9\n')
    lines.append('\n')

    # Save run file
    with open(parameters.fileSave,'w',encoding='utf-8') as f:
        f.writelines(lines)

    print(f'Succesfully generated file @ {parameters.fileSave}')

# MAIN
if __name__ == '__main__':
    parameters = Parameters(
        fileSave = 'run/runTEST.in',
        lat1 = 45.0,
        lat2 = 41.0,
        lon1 = -3,
        lon2 = 4,
        fileModel = './model/pyrenees',
        fileTime = './time/pyrenees',
        fileBulletinIn = './obs/GLOBAL.obs',
        fileBulletinOut = './loc/GLOBAL.obs',
        fileStations = 'stations/GTSRCE.txt',
    )

    saveRunFile(parameters)
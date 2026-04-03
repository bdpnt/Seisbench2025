'''
genMagModel_obs generates a regression model from a magnitude type from
a .obs Bulletin to another magnitude type from another .obs Bulletin.
'''

from dataclasses import dataclass
import pandas as pd
import math
import numpy as np

@dataclass
class MagModelParams:
    fileName1: str
    fileName2: str
    magType1: str
    magType2: str
    magName1: str
    magName2: str
    distThresh: float
    timeThresh: float
    saveName: str
    saveFigs: str
from scipy.spatial import KDTree
from scipy.odr import ODR, Model, RealData
from scipy.optimize import minimize
from sklearn.metrics import r2_score
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

def haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two geographical points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

def retrieveEvents_fromFile(fileName, magType):
    with open(fileName, 'r', encoding='utf-8', errors='ignore') as fR:
        catLines = fR.readlines()

    eventLines = []
    for line in catLines:
        if line.startswith('###'):
            continue
        elif line.startswith('#'):
            if magType in line:
                eventLines.append(line.rstrip('\n').lstrip('# '))

    print(f"{len(eventLines)} events from Catalog @ {fileName} (MagType '{magType}') successfully retrieved")
    return eventLines

def get_catalogFrame(eventLines):
    latitudes = []
    longitudes = []
    times = []
    magnitudes = []

    for line in eventLines:
        infos = line.split()

        year = infos[0]
        month = infos[1]
        day = infos[2]
        hour = infos[3]
        minute = infos[4]
        second = infos[5]

        times.append(pd.to_datetime(f"{year}-{month}-{day}T{hour}:{minute}:{second}Z"))
        latitudes.append(float(infos[6]))
        longitudes.append(float(infos[7]))
        magnitudes.append(float(infos[9]))

    catalogFrame = pd.DataFrame({
        'latitude': latitudes,
        'longitude': longitudes,
        'time': times,
        'magnitude': magnitudes,
    })

    return catalogFrame

def matchEvents(catalog1, catalog2, distThresh, timeThresh):
    """Catalog1 is the catalog to convert, distance in km and time in seconds"""
    timeThresh = pd.Timedelta(seconds=timeThresh)

    coords2 = catalog2[['latitude', 'longitude']].values
    tree = KDTree(coords2)

    matched_pairs = []
    matched_indices_catalog1 = set()
    matched_indices_catalog2 = set()

    for idx1, row in catalog1.iterrows():
        if idx1 in matched_indices_catalog1:
            continue

        _, idx = tree.query([row['latitude'], row['longitude']], k=100)

        best_match_idx = None
        best_match_distance = float('inf')
        best_match_time_diff = float('inf')

        for i in idx:
            if i in matched_indices_catalog2:
                continue

            candidate = catalog2.iloc[i]
            distance_km = haversine(row['latitude'], row['longitude'], candidate['latitude'], candidate['longitude'])

            if distance_km <= distThresh:
                time_diff = abs((row['time'] - candidate['time']).total_seconds())

                if time_diff <= timeThresh.total_seconds():
                    if distance_km < best_match_distance or (distance_km == best_match_distance and time_diff < best_match_time_diff):
                        best_match_idx = i
                        best_match_distance = distance_km
                        best_match_time_diff = time_diff

        if best_match_idx is not None:
            matched_indices_catalog1.add(idx1)
            matched_indices_catalog2.add(best_match_idx)
            matched_pairs.append({
                'catalog1_idx': idx1,
                'catalog2_idx': best_match_idx,
                'distance_km': best_match_distance,
                'time_diff_seconds': best_match_time_diff,
                'magnitude1': row['magnitude'],
                'magnitude2': catalog2.iloc[best_match_idx]['magnitude']
            })

    return pd.DataFrame(matched_pairs), matched_indices_catalog1, matched_indices_catalog2

def linear_func(p, x):
    slope, intercept = p
    return slope * x + intercept

def convertMagnitudes(parameters, printFigs=False):
    print('\n#########')
    print(f'\nGenerating model for {parameters.magName1} to {parameters.magName2} magnitudes conversion...\n') # opening line

    #--- Match events from both catalogs
    events1 = retrieveEvents_fromFile(parameters.fileName1, parameters.magType1)
    events2 = retrieveEvents_fromFile(parameters.fileName2, parameters.magType2)

    catalog1 = get_catalogFrame(events1)
    catalog2 = get_catalogFrame(events2)

    matchedFrame, matchInd1, matchInd2 = matchEvents(catalog1, catalog2, distThresh=parameters.distThresh, timeThresh=parameters.timeThresh)

    #--- Handle no match case
    if len(matchedFrame) == 0:
        print("\nNo match found between Catalogs, please check distance/time thresholds or your data files")
        print('\n#########\n') # closing line
        return
    else:
        print(f"\nEvents from Catalogs successfully matched")
        print(f"    - matched events: {len(matchedFrame)}")

    #--- Show unmatched events
    all_indices_catalog1 = set(catalog1.index)
    unmatched_indices_catalog1 = list(all_indices_catalog1 - matchInd1)
    unmatched_events_catalog1 = catalog1.loc[unmatched_indices_catalog1]
    print(f"    - unmatched events in Catalog @ {parameters.fileName1}: {len(unmatched_events_catalog1)}/{len(catalog1)}")

    all_indices_catalog2 = set(catalog2.index)
    unmatched_indices_catalog2 = list(all_indices_catalog2 - matchInd2)
    unmatched_events_catalog2 = catalog2.loc[unmatched_indices_catalog2]
    print(f"    - unmatched events in Catalog @ {parameters.fileName2}: {len(unmatched_events_catalog2)}/{len(catalog2)}")

    #--- If less than 100 events
    if len(matchedFrame) < 100:
        print(f"\nNot enough matched events to continue")
        print('\n#########\n') # closing line
        return

    #--- Split data into M >= 2 and M < 2
    matchedFrame['magnitude_group'] = matchedFrame['magnitude1'].apply(lambda x: f'{parameters.magName1} ≥ 2' if x >= 2 else f'{parameters.magName1} < 2')
    groups = matchedFrame.groupby('magnitude_group')

    #--- Train model for M >= 2 using orthogonal regression
    group_geq_2 = groups.get_group(f'{parameters.magName1} ≥ 2')
    X_geq_2 = group_geq_2['magnitude1'].values
    y_geq_2 = group_geq_2['magnitude2'].values

    linear_model_geq_2 = Model(linear_func)
    data_geq_2 = RealData(X_geq_2, y_geq_2)
    odr_geq_2 = ODR(data_geq_2, linear_model_geq_2, beta0=[1., 0.])
    output_geq_2 = odr_geq_2.run()
    slope_geq_2, intercept_geq_2 = output_geq_2.beta

    # Calculate the predicted value at M=2 for M >= 2 model
    y_at_2 = slope_geq_2 * 2 + intercept_geq_2

    #--- Train model for M < 2 with continuity constraint using orthogonal regression
    group_lt_2 = groups.get_group(f'{parameters.magName1} < 2')
    X_lt_2 = group_lt_2['magnitude1'].values
    y_lt_2 = group_lt_2['magnitude2'].values

    # Constraint: intercept + slope * 2 = y_at_2
    def constrained_linear_func(p, x):
        slope, intercept = p
        return slope * x + intercept

    def objective(params):
        slope, intercept = params
        residuals = y_lt_2 - (intercept + slope * X_lt_2)
        return np.sum(residuals**2)

    def constraint(params):
        slope, intercept = params
        return intercept + slope * 2 - y_at_2

    # Initial guess for slope and intercept
    initial_guess = [1, 0]

    # Define the constraint as a dictionary
    cons = {'type': 'eq', 'fun': constraint}

    # Minimize the objective function subject to the constraint
    result = minimize(objective, initial_guess, constraints=cons, method='SLSQP')

    # Extract the optimized parameters
    slope_lt_2, intercept_lt_2 = result.x

    #--- Store both models
    models = {
        f'{parameters.magName1} ≥ 2': {'slope': slope_geq_2, 'intercept': intercept_geq_2},
        f'{parameters.magName1} < 2': {'slope': slope_lt_2, 'intercept': intercept_lt_2}
    }

    #--- Plot both regressions
    if printFigs:
        fig, ax = plt.subplots(figsize=(10, 7))
        sns.scatterplot(data=matchedFrame, x='magnitude1', y='magnitude2', hue='magnitude_group', alpha=0.6, ax=ax)

        # Plot regression lines
        x_range_lt_2 = np.linspace(matchedFrame['magnitude1'].min(), 2, 50)
        x_range_geq_2 = np.linspace(2, matchedFrame['magnitude1'].max(), 50)
        y_lt_2 = slope_lt_2 * x_range_lt_2 + intercept_lt_2
        y_geq_2 = slope_geq_2 * x_range_geq_2 + intercept_geq_2

        ax.plot(x_range_lt_2, y_lt_2, color='blue', label=f'{parameters.magName1} < 2: y = {slope_lt_2:.3f}x + {intercept_lt_2:.3f}')
        ax.plot(x_range_geq_2, y_geq_2, color='red', label=f'{parameters.magName1} ≥ 2: y = {slope_geq_2:.3f}x + {intercept_geq_2:.3f}')
        ax.axvline(x=2, color='gray', linestyle='--', label=f'Inflexion at {parameters.magName1} = 2')

        ax.set_xlabel(f'Magnitude {parameters.magName1}')
        ax.set_ylabel(f'Magnitude {parameters.magName2}')
        ax.set_title('Piecewise Linear Regression: Magnitude Conversion (Orthogonal)')
        ax.legend()
        ax.grid(True)
        plt.savefig(parameters.saveFigs + f'{parameters.magName1}_2_{parameters.magName2}.png')
        plt.close(fig)

    #--- Calculate residuals and R² for both models
    matchedFrame['predicted_magnitude2'] = np.nan
    for idx, row in matchedFrame.iterrows():
        if row['magnitude1'] >= 2:
            matchedFrame.at[idx, 'predicted_magnitude2'] = slope_geq_2 * row['magnitude1'] + intercept_geq_2
        else:
            matchedFrame.at[idx, 'predicted_magnitude2'] = slope_lt_2 * row['magnitude1'] + intercept_lt_2

    matchedFrame['residual'] = matchedFrame['magnitude2'] - matchedFrame['predicted_magnitude2']

    # Calculate R²
    R2_geq_2 = r2_score(group_geq_2['magnitude2'], slope_geq_2 * group_geq_2['magnitude1'] + intercept_geq_2)
    R2_lt_2 = r2_score(group_lt_2['magnitude2'], slope_lt_2 * group_lt_2['magnitude1'] + intercept_lt_2)
    print('\nOrthogonal regression models successfully trained')
    print(f"    - R² for {parameters.magName1} ≥ 2: {R2_geq_2:.3f}")
    print(f"    - R² for {parameters.magName1} < 2: {R2_lt_2:.3f} (constrained regression)")

    # Calculate BIC
    n = len(matchedFrame)
    k_BIC = 4  # 2 slopes + 2 intercepts
    SSR_BIC = np.sum(matchedFrame['residual']**2)
    sigma2_BIC = SSR_BIC / n
    BIC = k_BIC * np.log(n) + n * np.log(2 * np.pi * sigma2_BIC) + n
    print(f"    - BIC for global model: {BIC:.3f}")

    # Outliers (IQR method)
    Q1 = matchedFrame['residual'].quantile(0.25)
    Q3 = matchedFrame['residual'].quantile(0.75)
    IQR = Q3 - Q1
    matchedFrame['is_outlier_iqr'] = (matchedFrame['residual'] < (Q1 - 1.5 * IQR)) | (matchedFrame['residual'] > (Q3 + 1.5 * IQR))
    outliers = matchedFrame[matchedFrame['is_outlier_iqr']]
    print(f"    - Found {len(outliers)}/{len(matchedFrame)} outliers (IQR method)")

    # Plot residuals
    if printFigs:
        figResiduals = plt.figure(figsize=(10, 7))
        sns.scatterplot(data=matchedFrame, x='magnitude1', y='residual', hue='magnitude_group', alpha=0.4)
        sns.scatterplot(data=outliers, x='magnitude1', y='residual', color='red', label='Outliers')
        plt.axhline(y=0, color='black', linestyle='--')
        plt.xlabel(f'Magnitude (Type {parameters.magName1})')
        plt.ylabel(f'Residual (Observed - Predicted)\n(Type {parameters.magName2})')
        plt.title(f'Residuals with IQR Outliers\nM < 2: R² = {R2_lt_2:.3f}, M ≥ 2: R² = {R2_geq_2:.3f}\nBIC: {BIC:.3f}')
        plt.legend()
        plt.grid(True)
        plt.savefig(parameters.saveFigs + f'Residuals_{parameters.magName1}_2_{parameters.magName2}.png')
        plt.close(figResiduals)

    #--- Save both models
    joblib.dump(models, parameters.saveName)
    print(f"\nModels successfully saved @ {parameters.saveName}\n")
    print(f"Model for {parameters.magName1} ≥ 2: y = {slope_geq_2:.3f} * x + {intercept_geq_2:.3f}")
    print(f"Model for {parameters.magName1} < 2: y = {slope_lt_2:.3f} * x + {intercept_lt_2:.3f}")
    print('\n#########\n') # closing line

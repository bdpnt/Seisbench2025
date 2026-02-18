# Seisbench2025

## Inventory
To generate the global Inventory in the **stations/** folder, follow these steps :
- all the Inventories must be downloaded as either ```.xml``` (QUAKEML format), except for OMP Inventories ;
- for OMP inventories, use ```_checkNetworks.py```, ```_checkElevation.py``` and ```_csv2xml.py```, depending on the Inventory (must see one by one) ;
- use ```fusionInventory_xml.py``` to fusion all ```.xml``` files into a Global one, while adding a unique code for each station

## Bulletin
To generate the global Bulletin in the **obs/** folder, follow these steps :
- for IGN, LDG and OMP Catalogs, must have corresponding ```.txt``` files in the **ORGCATALOGS/** folder ;
- use ```fetchRESIF.py```, ```fetchICGC.py``` to fetch the data from FDSN and ICGC website ;
- use ```RESIF2obs.py```, ```ICGC2obs.py```, ```IGN2obs.py```, ```LDG2obs.py``` and ```OMP2obs.py``` to generate the ```.obs``` files ;
- use ```updateBulletinPicks_obs.py``` to associate every pick with a unique network/station couple from the Global Inventory ;
- use ```availableMagTypes_obs.py``` to see which magnitude types are available for a specific ```.obs``` file ;
- use ```genMagModel_obs.py``` to generate a magnitude model for a specific magnitude type to ML LDG, for a specific ```.obs``` file ;
- use ```useMagModels_obs.py``` to update all magnitudes in all ```.obs``` files to ML LDG magnitudes ;
- use ```updateBulletinsAOI_obs.py``` to remove events outside of areas designated for all Catalogs ;
- use ```fusionBulletins_obs.py``` to fusion all ```.obs``` files into a Global one, matching events in the process ;
- use ```mapGlobalBulletin_obs.py``` to generate the map of all events in the ```GLOBAL.obs``` file

## NLL workflow
- ```GLOBAL.obs``` now contains already all the picks needed for the NLL workflow
- use ```genGTSRCE.py``` to generate the ```GTSRCE.txt``` file containing all the stations that appear in ```GLOBAL.obs```

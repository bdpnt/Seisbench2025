'''
genTest_obs reads an OBS file and generates a test OBS file with the first samples.
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

# FUNCTIONS
def generate_test(parameters):
    #--- Read OBS
    with open(parameters.fileName, 'r', encoding='utf-8', errors='ignore') as fR:
        catLines = fR.readlines()
    print(f"Events from Catalog succesfully retrieved")

    #--- Generate Test OBS
    with open(parameters.saveName, 'w') as f:
        # Check for events
        event_count = 0
        last_ind = None
        for ind, line in enumerate(catLines):
            if line.startswith("###"):
                continue
            elif line.startswith("#"):
                event_count += 1
                last_ind = ind  # Record the index
                if event_count == 11:  # Stop after the 11th occurrence
                    break
        
        # Get the 10 first events
        testLines = catLines[:last_ind-1]

        for line in testLines:
            f.write(line)

    # Print        
    print(f"Test catalog succesfully written to {parameters.saveName}")

# MAIN
if __name__ == '__main__':
    #---- Parameters
    parameters = Parameters(
        fileName="obs/IGN_20-25.obs",
        saveName = "obs/TEST_IGN_20-25.obs",
    )

    #---- Write Test OBS fil
    generate_test(parameters)
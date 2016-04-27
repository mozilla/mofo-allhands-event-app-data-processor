def parseListFromEnvVar(str):
    theList = str.split(',')

    for i, sheetName in enumerate(theList):
        theList[i] = theList[i].strip()

    return theList

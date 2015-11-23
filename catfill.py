import argparse
import redpy
import numpy as np
import obspy
from obspy import UTCDateTime
import time
import pandas as pd

# Added this to remove the slew of warnings obspy/numpy was throwing at me
import warnings
warnings.filterwarnings("ignore")

"""
Run this script to fill the table with data from the past using a catalog of events.
 
usage: catfill.py [-h] [-v] [-c CONFIGFILE] csvfile

positional arguments:
  csvfile               catalog csv file with a 'Time UTC' column of event times

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         increase written print statements
  -c CONFIGFILE, --configfile CONFIGFILE
                        use configuration file named CONFIGFILE instead of
                        default settings.cfg
"""

parser = argparse.ArgumentParser(description=
    "Backfills table with data from the past")
parser.add_argument("csvfile",
    help="catalog csv file with a 'Time UTC' column of event times")
parser.add_argument("-v", "--verbose", action="count", default=0,
    help="increase written print statements")
parser.add_argument("-c", "--configfile",
    help="use configuration file named CONFIGFILE instead of default settings.cfg")
args = parser.parse_args()

if args.configfile:
    opt = redpy.config.Options(args.configfile)
    if args.verbose: print("Using config file: {0}".format(args.configfile))
else:
    opt = redpy.config.Options("settings.cfg")
    if args.verbose: print("Using config file: settings.cfg")

if args.verbose: print("Opening hdf5 table: {0}".format(opt.filename))
h5file, rtable, otable, ctable, jtable = redpy.table.openTable(opt)
    

t = time.time()

# Read in csv file using pandas
df = pd.read_csv(args.csvfile)
# Grab event times from 'Time UTC' column, convert to datetimes also
eventlist = pd.to_datetime(df['Time UTC']).tolist()

# Assumes list is youngest to oldest, we want oldest to youngest!
for event in eventlist[::-1]:
    
    etime = UTCDateTime(event)
    
    if args.verbose: print(etime)
    
    # Download and trigger
    try:
        st = redpy.trigger.getCatData(etime, opt)
        alltrigs = redpy.trigger.trigger(st, rtable, opt)
        
		# Clean out data spikes etc.
        trigs, junk = redpy.trigger.dataclean(alltrigs, opt, flag=1)
        
		# Save junk triggers in separate table for quality checking purposes
        for i in range(len(junk)):
            redpy.table.populateJunk(jtable,junk[i],0,opt)
            
    except (TypeError, obspy.fdsn.header.FDSNException):
	    print('Could not download or trigger data... moving on')
	    trigs = []
    
    if len(trigs) > 0:        
        id = rtable.attrs.previd        
        if len(trigs) == 1:        
            ostart = 0
            if len(otable) == 0:
                # First trigger goes to orphans table
                redpy.table.populateOrphan(otable, 0, trigs[0], opt)
                ostart = 1
            else:        
                id = id + 1
                redpy.correlation.runCorrelation(rtable, otable, ctable, trigs[0], id, opt)        
        else:
            ostart = 0
            if len(otable) == 0:
                # First trigger goes to orphans table
                redpy.table.populateOrphan(otable, 0, trigs[0], opt)
                ostart = 1        
            # Loop through remaining triggers
            for i in range(ostart,len(trigs)):  
                id = id + 1
                redpy.correlation.runCorrelation(rtable, otable, ctable, trigs[i], id, opt)            
        rtable.attrs.previd = id        
    
    # Don't expire orphans yet while testing
    # redpy.table.clearExpiredOrphans(otable, opt, tstart+(n+1)*opt.nsec)
    
    # Deal with leftovers (currently thrown away)
    leftovers = rtable.get_where_list('clusterNumber == -1')
    if leftovers.any():
        leftovers[::-1].sort()
        print("Removing leftovers in clustering: {0}".format(len(leftovers)))
        for l in leftovers:
            rtable.remove_row(l)
    
    # Print some stats
    if args.verbose:
        print("Length of Orphan table: {}".format(len(otable)))
        if len(rtable) > 1:
            print("Number of repeaters: {}".format(len(rtable)))
            print("Number of clusters: {}".format(max(rtable.cols.clusterNumber[:])+1))
    
    if len(rtable) > 1:
        redpy.plotting.createTimelineFigure(rtable, ctable, opt)

# Clean things up at the end of the import
redpy.cluster.deepClean(rtable, ctable, opt)
redpy.cluster.runFullOPTICS(rtable, ctable, opt)
redpy.plotting.createTimelineFigure(rtable, ctable, opt)

print("Time spent: {} minutes".format((time.time()-t)/60))

if args.verbose: print("Closing table...")
h5file.close()
if args.verbose: print("Done")
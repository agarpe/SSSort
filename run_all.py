import sys
import glob
import os

try:
	file = sys.argv[1]
except:
	print("Error: First argument must be the config file path")
	exit()

print("Analyzing from %s"%file)

# sorting by clustering based on detected spikes
cmd = "python sssort.py %s"%file
print("##########################################\n\n")
print(cmd)
os.system(cmd)
print("\n\n")

# Run post-processing 
cmd = "python post_run_manual_merger.py %s"%file
print("##########################################\n\n")
print(cmd)
os.system(cmd)
print("\n\n")

# cluster identification based on templates
cmd = "python cluster_identification.py %s"%file
print("##########################################\n\n")
print(cmd)
os.system(cmd)
print("\n\n")

# Run post-processing 
cmd = "python post_processing.py %s"%file
print("##########################################\n\n")
print(cmd)
os.system(cmd)
print("\n\n")

import sys
import os
import neo
from neo import Spike2IO
from neo import NixIO
import quantities as pq
import copy

import dill
import os
import sys


"""
*** modified by AGP 2021-11-10: Adaptation from smr2nix to generate dill file***

Data format requirements:
The neo.core.Block that is read by SSSort must:
1) contain one or more segments - each segment is treated as a seperate trial
and is sorted seperately (template matching. Templates are gathered from the
entire recording)
2) in each segment, analogsignals[0] must contain the recorded voltage
3) Block must be written by NixIO
"""


def smr2dill(path):
    """
    converts a .smr file to a dill file containing the neo.core.Block suitable
    for the SeqPeelSort run.

    This is a user specific function tailored to my recording settings, and
    servers here as an example.

    Args:
        path (str): the path to the .smr file
        cut_time (Quantity)(2,): specifying how much time before and after a
            trigger is defining the time of a trial. In my case, a trigger
            occured at the onset of stimulation
    """

    Reader = Spike2IO(filename=path)
    Blk = Reader.read_block()

    outpath = os.path.splitext(path)[0]+'.dill'
   
    # print(Blk.segments[0].analogsignals)

    with open(outpath, 'wb') as fH:
        print("dumping neo.block to dill file %s" % outpath)
        dill.dump(Blk, fH)


if __name__ == '__main__':
    smr2dill(sys.argv[1])

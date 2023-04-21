# system
import sys
import os
import time
import copy
if os.name == 'posix':
    import resource
import warnings
from tqdm import tqdm
import threading

# sci
import scipy as sp
import numpy as np
from scipy import stats, signal
import quantities as pq
import pandas as pd

# ml
import sklearn
from sklearn.neighbors import LocalOutlierFactor
from sklearn.decomposition import PCA
from sklearn import metrics

# ephys
import neo
import elephant as ele

# print
import colorama
import tableprint as tp

# plotting
import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore")
t0 = time.time()

"""
 
 ##     ## ######## ##       ########  ######## ########   ######  
 ##     ## ##       ##       ##     ## ##       ##     ## ##    ## 
 ##     ## ##       ##       ##     ## ##       ##     ## ##       
 ######### ######   ##       ########  ######   ########   ######  
 ##     ## ##       ##       ##        ##       ##   ##         ## 
 ##     ## ##       ##       ##        ##       ##    ##  ##    ## 
 ##     ## ######## ######## ##        ######## ##     ##  ######  
 
"""

def print_msg(msg, log=True):
    """prints the msg string with elapsed time and current memory usage.

    Args:
        msg (str): the string to print
        log (bool): write the msg to the log as well

    """
    if os.name == 'posix':
        mem_used = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
        # msg = "%s%s\t%s\t%s%s" % (colorama.Fore.CYAN, timestr, memstr, colorama.Fore.GREEN, msg)
        mem_used = np.around(mem_used, 2)
        memstr = '('+str(mem_used) + ' GB): '
        timestr = tp.humantime(np.around(time.time()-t0,2))
        print(colorama.Fore.CYAN + timestr + '\t' +  memstr + '\t' +
              colorama.Fore.GREEN + msg)
        if log:
            with open('log.log', 'a+') as fH:
                log_str = timestr + '\t' +  memstr + '\t' + msg + '\n'
                fH.writelines(log_str)
    else:
        timestr = tp.humantime(np.around(time.time()-t0,2))
        print(colorama.Fore.CYAN + timestr + '\t' +
              colorama.Fore.GREEN + msg)
        if log:
            with open('log.log', 'a+') as fH:
                log_str = timestr + '\t' + '\t' + msg
                fH.writelines(log_str)
    pass

def select_by_dict(objs, **selection):
    """
    selects elements in a list of neo objects with annotations matching the
    selection dict.

    Args:
        objs (list): a list of neo objects that have annotations
        selection (dict): a dict containing key-value pairs for selection

    Returns:
        list: a list containing the subset of matching neo objects
    """
    res = []
    for obj in objs:
        if selection.items() <= obj.annotations.items():
            res.append(obj)
    return res

def sort_units(units):
    """ helper to sort units ascendingly according to their number """
    units = np.array(units,dtype='int32')
    units = np.sort(units).astype('U')
    return list(units)

def get_units(SpikeInfo, unit_column, remove_unassinged=True):
    """ helper that returns all units in a given unit column, with or without unassigned """
    units = list(pd.unique(SpikeInfo[unit_column]))
    if remove_unassinged:
        if '-1' in units:
            units.remove('-1')
    return sort_units(units)

def unassign_spikes(SpikeInfo, unit_column, min_good=5):
    """ unassign spikes from unit it unit does not contain enough spikes as samples """
    units = get_units(SpikeInfo, unit_column)
    for unit in units:
        Df = SpikeInfo.groupby(unit_column).get_group(unit)
        if np.sum(Df['good']) < min_good:
            print_msg("not enough good spikes for unit %s" %unit)
            SpikeInfo.loc[Df.index, unit_column] = '-1'
    return SpikeInfo


"""
 
  ######  ########  #### ##    ## ########    ########  ######## ######## ########  ######  ######## 
 ##    ## ##     ##  ##  ##   ##  ##          ##     ## ##          ##    ##       ##    ##    ##    
 ##       ##     ##  ##  ##  ##   ##          ##     ## ##          ##    ##       ##          ##    
  ######  ########   ##  #####    ######      ##     ## ######      ##    ######   ##          ##    
       ## ##         ##  ##  ##   ##          ##     ## ##          ##    ##       ##          ##    
 ##    ## ##         ##  ##   ##  ##          ##     ## ##          ##    ##       ##    ##    ##    
  ######  ##        #### ##    ## ########    ########  ########    ##    ########  ######     ##    
 
"""

def MAD(AnalogSignal, keep_units=True):
    """ median absolute deviation of an AnalogSignal """
    X = AnalogSignal.magnitude
    mad = np.median(np.absolute(X - np.median(X)))
    if keep_units:
        mad = mad * AnalogSignal.units
    return mad

def spike_detect(AnalogSignal, min_height, min_prom, lowpass_freq=1000*pq.Hz):

    data = AnalogSignal.magnitude.flatten()

    res = signal.find_peaks(data, height=[min_height, np.inf], prominence=[min_prom, np.inf])

    peak_inds = res[0]
    peak_amps = res[1]['peak_heights'][:, np.newaxis, np.newaxis]  * AnalogSignal.units

    SpikeTrain = neo.core.SpikeTrain(AnalogSignal.times[peak_inds],
                                        t_start=AnalogSignal.t_start,
                                        t_stop=AnalogSignal.t_stop,
                                        sampling_rate=AnalogSignal.sampling_rate,
                                        waveform=peak_amps)
    
    return SpikeTrain

"""
 
 ######## ######## ##     ## ########  ##          ###    ######## ########  ######  
    ##    ##       ###   ### ##     ## ##         ## ##      ##    ##       ##    ## 
    ##    ##       #### #### ##     ## ##        ##   ##     ##    ##       ##       
    ##    ######   ## ### ## ########  ##       ##     ##    ##    ######    ######  
    ##    ##       ##     ## ##        ##       #########    ##    ##             ## 
    ##    ##       ##     ## ##        ##       ##     ##    ##    ##       ##    ## 
    ##    ######## ##     ## ##        ######## ##     ##    ##    ########  ######  
 
"""

def get_Templates(data, inds, n_samples):
    """ slice windows of n_samples (symmetric) out of data at inds """
    hwsize = np.int32(n_samples/2)

    Templates = np.zeros((n_samples,inds.shape[0]))
    for i, ix in enumerate(inds):
        Templates[:,i] = data[ix-hwsize:ix+hwsize]

    return Templates

def outlier_reject(Templates, n_neighbors=80):
    """ detect outliers using sklearns LOF, return outlier indices """
    clf = LocalOutlierFactor(n_neighbors=n_neighbors)
    bad_inds = clf.fit_predict(Templates.T) == -1
    return bad_inds

def peak_reject(Templates, f=3):
    """ detect outliers using peak rejection criterion. Peak must be at least
    f times larger than first or last sample. Return outlier indices """
    # peak criterion

    n_samples = Templates.shape[0]
    mid_ix = int(n_samples/2)
    peak = Templates[mid_ix,:]
    left = Templates[0,:]
    right = Templates[-1,:]

    # this takes care of negative or positive spikes
    if np.average(Templates[mid_ix,:]) > 0:
        bad_inds = np.logical_or(left > peak/f, right > peak/f)
    else:
        bad_inds = np.logical_or(left < peak/f, right < peak/f)
    return bad_inds

def reject_spikes(Templates, SpikeInfo, unit_column, n_neighbors=80, verbose=False):
    """ reject bad spikes from Templates, updates SpikeInfo """
    units = get_units(SpikeInfo, unit_column)
    spike_labels = SpikeInfo[unit_column]
    for unit in units:
        ix = np.where(spike_labels == unit)[0]
        a = outlier_reject(Templates[:,ix], n_neighbors)
        b = peak_reject(Templates[:,ix])
        good_inds_unit = ~np.logical_or(a,b)

        SpikeInfo.loc[ix,'good'] = good_inds_unit
        
        if verbose:
            n_total = ix.shape[0]
            n_good = np.sum(good_inds_unit)
            n_bad = np.sum(~good_inds_unit)
            frac = n_good / n_total
            print_msg("# spikes for unit %s: total:%i \t good/bad:%i,%i \t %.2f" % (unit, n_total, n_good, n_bad, frac))

"""
 
  ######  ########  #### ##    ## ########    ##     ##  #######  ########  ######## ##       
 ##    ## ##     ##  ##  ##   ##  ##          ###   ### ##     ## ##     ## ##       ##       
 ##       ##     ##  ##  ##  ##   ##          #### #### ##     ## ##     ## ##       ##       
  ######  ########   ##  #####    ######      ## ### ## ##     ## ##     ## ######   ##       
       ## ##         ##  ##  ##   ##          ##     ## ##     ## ##     ## ##       ##       
 ##    ## ##         ##  ##   ##  ##          ##     ## ##     ## ##     ## ##       ##       
  ######  ##        #### ##    ## ########    ##     ##  #######  ########  ######## ######## 
 
"""
def lin(x, *args):
    m, b = args
    return x*m+b

class Spike_Model():
    """ models how firing rate influences spike shape. First forms a 
    lower dimensional embedding of spikes in PC space and then fits a 
    linear relationship on how the spikes change in this space. """

    def __init__(self, n_comp=5):
        self.n_comp = n_comp
        self.Templates = None
        self.frates = None
        pass

    def fit(self, Templates, frates):
        """ fits the linear model """
        
        # keep data
        self.Templates = Templates
        self.frates = frates

        # make pca from templates
        self.pca = PCA(n_components=self.n_comp)
        self.pca.fit(Templates.T)
        pca_templates = self.pca.transform(Templates.T)

        self.pfits = []
        p0 = [0,0]
        for i in range(self.n_comp):
            pfit = sp.stats.linregress(frates, pca_templates[:,i])[:2]
            self.pfits.append(pfit)

    def predict(self, fr):
        """ predicts spike shape at firing rate fr, in PC space, returns
        inverse transform: the actual spike shape as it would be measured """
        pca_i = [lin(fr,*self.pfits[i]) for i in range(len(self.pfits))]
        return self.pca.inverse_transform(pca_i)

def train_Models(SpikeInfo, unit_column, Templates, n_comp=5, verbose=True):
    """ trains models for all units, using labels from given unit_column """

    if verbose:
        print_msg("training model on: " + unit_column)

    units = get_units(SpikeInfo, unit_column)

    Models = {}
    for unit in units:
        # get the corresponding spikes - restrict training to good spikes
        SInfo = SpikeInfo.groupby([unit_column,'good']).get_group((unit,True))
        # data
        ix = SInfo['id']
        T = Templates[:,ix.values]
        # frates
        frates = SInfo['frate_fast']
        # model
        Models[unit] = Spike_Model(n_comp=n_comp)
        Models[unit].fit(T, frates)
    
    return Models

"""
 
 ########     ###    ######## ########    ########  ######  ######## #### ##     ##    ###    ######## ####  #######  ##    ## 
 ##     ##   ## ##      ##    ##          ##       ##    ##    ##     ##  ###   ###   ## ##      ##     ##  ##     ## ###   ## 
 ##     ##  ##   ##     ##    ##          ##       ##          ##     ##  #### ####  ##   ##     ##     ##  ##     ## ####  ## 
 ########  ##     ##    ##    ######      ######    ######     ##     ##  ## ### ## ##     ##    ##     ##  ##     ## ## ## ## 
 ##   ##   #########    ##    ##          ##             ##    ##     ##  ##     ## #########    ##     ##  ##     ## ##  #### 
 ##    ##  ##     ##    ##    ##          ##       ##    ##    ##     ##  ##     ## ##     ##    ##     ##  ##     ## ##   ### 
 ##     ## ##     ##    ##    ########    ########  ######     ##    #### ##     ## ##     ##    ##    ####  #######  ##    ## 
 
"""

# def local_frate1(t, mu, sig):
#     """ local firing rate - symmetric gaussian kernel with width parameter sig """
#     return 1/(sig*np.sqrt(2*np.pi)) * np.exp(-0.5 * ((t-mu)/sig)**2)

def local_frate(t, mu, tau):
    """ local firing rate - causal alpha kernel with shape parameter tau """
    y = (1/tau**2)*(t-mu)*np.exp(-(t-mu)/tau)
    y[t < mu] = 0
    return y

def est_rate(spike_times, eval_times, sig):
    """ returns estimated rate at spike_times """
    rate = local_frate(eval_times[:,np.newaxis], spike_times[np.newaxis,:], sig).sum(1)
    return rate

def calc_update_frates(Segments, SpikeInfo, unit_column, kernel_fast, kernel_slow):
    """ calculate all firing rates for all units, based on unit_column. Updates SpikeInfo """
    # TODO - mix of new and old syntax - Segments are not needed
    
    from_units = get_units(SpikeInfo, unit_column, remove_unassinged=True)
    to_units = get_units(SpikeInfo, unit_column, remove_unassinged=False)

    # estimating firing rate profile for "from unit" and getting the rate at "to unit" timepoints
    for i, seg  in enumerate(Segments):
        for j, from_unit in enumerate(from_units):
            try:
                SInfo = SpikeInfo.groupby([unit_column,'segment']).get_group((from_unit,i))

                # spike times
                from_times = SInfo['time'].values

                # estimate its own rate at its own spike times
                rate = est_rate(from_times, from_times, kernel_fast)

                # set
                ix = SInfo['id']
                SpikeInfo.loc[ix,'frate_fast'] = rate
            except:
                # can not set it's own rate, when there are no spikes in this segment for this unit
                pass

            # the rates on others
            for k, to_unit in enumerate(to_units):
                try:
                    SInfo = SpikeInfo.groupby([unit_column, 'segment']).get_group((to_unit,i))

                    # spike times
                    to_times = SInfo['time'].values

                    # the rates of the other units at this units spike times
                    pred_rate = est_rate(from_times, to_times, kernel_slow)

                    ix = SInfo['id']
                    SpikeInfo.loc[ix,'frate_from_'+from_unit] = pred_rate
                except:
                    # similar: when no spikes in this segment, can not set
                    pass


"""
 
  ######   ######   #######  ########  ######## 
 ##    ## ##    ## ##     ## ##     ## ##       
 ##       ##       ##     ## ##     ## ##       
  ######  ##       ##     ## ########  ######   
       ## ##       ##     ## ##   ##   ##       
 ##    ## ##    ## ##     ## ##    ##  ##       
  ######   ######   #######  ##     ## ######## 
 
"""

def Rss(X,Y):
    """ sum of squared residuals """
    return np.sum((X-Y)**2) / X.shape[0]

# def Score_spikes(Templates, SpikeInfo, unit_column, Models, score_metric=Rss, penalty=0.1):
#     """ Score all spikes using Models """

#     spike_ids = SpikeInfo['id'].values

#     units = get_units(SpikeInfo, unit_column)
#     n_units = len(units)

#     n_spikes = spike_ids.shape[0]
#     Scores = np.zeros((n_spikes,n_units))
#     Rates = np.zeros((n_spikes,n_units))

#     for i, spike_id in enumerate(spike_ids):
#         Rates[i,:] = [SpikeInfo.loc[spike_id,'frate_from_%s' % unit] for unit in units]
#         spike = Templates[:, spike_id]

#         for j, unit in enumerate(units):
#             # get the corresponding rate
#             rate = Rates[i,j]

#             # the simulated data
#             spike_pred = Models[unit].predict(rate)
#             Scores[i,j] = score_metric(spike, spike_pred)

#     Scores[np.isnan(Scores)] = np.inf
    
#     # penalty adjust
#     unit_inds = [units.index(i) if (i != '-1')  else -1 for i in SpikeInfo[unit_column].values]
#     for i, ui in enumerate(unit_inds):
#         if ui != -1:
#             Scores[i,ui] = Scores[i,ui] * (1+penalty)
            
#     return Scores, units

def Score_spikes(Templates, SpikeInfo, unit_column, Models, score_metric=Rss, penalty=0.1):
    """ Score all spikes using Models """

    spike_ids = SpikeInfo['id'].values

    units = get_units(SpikeInfo, unit_column)
    n_units = len(units)

    n_spikes = spike_ids.shape[0]
    Scores = sp.zeros((n_spikes,n_units))
    Rates = sp.zeros((n_spikes,n_units))

    for i, spike_id in enumerate(spike_ids):
        Rates[i,:] = [SpikeInfo.loc[spike_id,'frate_from_%s' % unit] for unit in units]
        spike = Templates[:, spike_id]

        for j, unit in enumerate(units):
            # get the corresponding rate
            rate = Rates[i,j]

            # the simulated data
            spike_pred = Models[unit].predict(rate)
            Scores[i,j] = score_metric(spike, spike_pred)

            # penalty adjust
            if int(unit) != SpikeInfo.loc[spike_id, unit_column]:
                Scores[i,j] = Scores[i,j] * (1+penalty)

    Scores[sp.isnan(Scores)] = sp.inf
    
    # extra penalty for "trash cluster"
    trash_ix = np.argmin([np.max(Models[u].predict(1)) for u in units])
    Scores[:,trash_ix] = Scores[:,trash_ix] * 4
            
    return Scores, units

"""
 
  ######  ##       ##     ##  ######  ######## ######## ########  
 ##    ## ##       ##     ## ##    ##    ##    ##       ##     ## 
 ##       ##       ##     ## ##          ##    ##       ##     ## 
 ##       ##       ##     ##  ######     ##    ######   ########  
 ##       ##       ##     ##       ##    ##    ##       ##   ##   
 ##    ## ##       ##     ## ##    ##    ##    ##       ##    ##  
  ######  ########  #######   ######     ##    ######## ##     ## 
 
"""

def calculate_pairwise_distances(Templates, SpikeInfo, unit_column, n_comp=5):
    """ calculate all pairwise distances between Templates in PC space defined by n_comp.
    returns matrix of average distances and of their sd """

    units = get_units(SpikeInfo, unit_column)
    n_units = len(units)

    Avgs = np.zeros((n_units,n_units))
    Sds = np.zeros((n_units,n_units))
    
    pca = PCA(n_components=n_comp)
    X = pca.fit_transform(Templates.T)

    for i,unit_a in enumerate(units):
        for j, unit_b in enumerate(units):
            ix_a = SpikeInfo.groupby([unit_column, 'good']).get_group((unit_a, True))['id']
            ix_b = SpikeInfo.groupby([unit_column, 'good']).get_group((unit_b, True))['id']
            T_a = X[ix_a,:]
            T_b = X[ix_b,:]
            D_pw = metrics.pairwise.euclidean_distances(T_a,T_b)
            Avgs[i,j] = np.average(D_pw)
            Sds[i,j] = np.std(D_pw)
    return Avgs, Sds

def best_merge(Avgs, Sds, units, alpha=1):
    """ merge two units if their average between distance is lower than within distance.
    SD scaling by factor alpha regulates aggressive vs. conservative merging """
    Q = copy.copy(Avgs)
    
    for i in range(Avgs.shape[0]):
        Q[i,i] = Avgs[i,i] + alpha * Sds[i,i]

    merge_candidates = list(zip(np.arange(Q.shape[0]),np.argmin(Q,1)))
    for i in range(Q.shape[0]):
        if (i,i) in merge_candidates:
            merge_candidates.remove((i,i))

    if len(merge_candidates) > 0:
        min_ix = np.argmin([Q[c] for c in merge_candidates])
        pair = merge_candidates[min_ix]
        merge = [units[pair[0]],units[pair[1]]]
    else:
         merge = []

    return merge
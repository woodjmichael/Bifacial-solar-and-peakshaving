""" Bifacial Peak Shaving
"""
import math
import pandas as pd
from _utils import *

def net_load_peak_reduction_variable_TOU(df,angle1,angle2):
    all_results = pd.DataFrame(columns=['TOU begin [h]',
                                        'TOU end [h]',
                                        'max peak reduction [kW]',
                                        'avg peak reduction [kW]',
                                        'min peak reduction [kW]'])
    for peak_begin in list(range(8,21)):
        for peak_end in list(range(9,22)):
            if (peak_end-peak_begin) >= 2:
                peaks = calc_monthly_peaks(df[f'netload_{angle1}'],peak_begin,peak_end)
                
                peaks = pd.concat((peaks,calc_monthly_peaks(df[f'netload_{angle2}'],
                                                            peak_begin,peak_end)),
                                  axis=1)
                peaks['peak_reduction'] = peaks[f'netload_{angle1} kw'] - peaks[f'netload_{angle2} kw']
                
                pr_max = peaks.peak_reduction.max().round(1)
                pr_avg = peaks.peak_reduction.mean().round(1)
                pr_min = peaks.peak_reduction.min().round(1)
                #print(f'{peak_begin:3d} {peak_end:3d} -- {pr_max:7.2f} {pr_avg:7.2f} {pr_min:7.2f}')
                all_results.loc[len(all_results)] = [peak_begin,peak_end,pr_max,pr_avg,pr_min]
                #results
                
    all_results['TOU begin [h]'] = all_results['TOU begin [h]'].astype(int)
    all_results['TOU end [h]'] = all_results['TOU end [h]'].astype(int)
    return all_results

def update_soe(soe:list,power:float,soe0:float,interval_min:int=60)->float:
    """Update state of energy from actual battery power

    Args:
        soe (list of floats): state of energy vector
        power (float): battery power (+ is discharge, - is charge)
        soe0 (float): initial state of energy

    Returns:
        float: next timestep state of energy
    """
    if len(soe) == 0:
        last_soe = soe0
    else:
        last_soe = soe[-1]

    energy = power * (interval_min/60) # kwh = kw * interval_h = kw * interval_min / (60 min/h)
    #next_soe = last_soe - energy*0.9
    
    if power > 0: # discharge
        next_soe = last_soe - energy/0.9
    elif power < 0: # charge
        next_soe = last_soe - energy*0.9
    else:
        next_soe = last_soe
        
    return next_soe

def batt_request(soe:list,power:float,soe0:float,soe_max:float,interval_min:int=60)->float:
    """Validate battery power based on state of energy max and min

    Args:
        soe (list of floats): state of energy vector
        power (float): battery power (+ is discharge, - is charge)
        soe0 (float): initial state of energy
        soe_max (float): maximum state of energy

    Returns:
        float: valdiated battery power (+ is discharge, - is charge)
    """
    
    if len(soe) == 0:
        last_soe = soe0
    else:
        last_soe = soe[-1]
        
    if power > 0: # discharge
        available_energy = (last_soe-0)*0.9 
        available_power = available_energy/(interval_min/60)
        power = min(power,available_power)
    elif power < 0: # charge
        available_energy = (soe_max-last_soe)/.9
        available_power = available_energy/(interval_min/60)
        power = max(power,-1*available_power)
    else:
        power = 0
    return power

def peak_shaving_sim_old(df2,nl_col,threshold,soe0,TOU_hours,soe_max=None):
    if soe_max is None:
        soe_max = soe0
    tol = 0.001 # tolerance
    df2 = df2.copy(deep=True)
    tou_first,tou_last = TOU_hours[0],TOU_hours[-1]
    batt,soe = [],[]    
    for net_load,t in zip(df2[nl_col],df2.index):
        if t.hour in TOU_hours:
            batt.append(batt_request(soe,net_load-threshold,soe0,soe_max))
        else:
            batt.append(min(0,batt_request(soe,net_load-threshold,soe0,soe_max)))
        soe.append(update_soe(soe,batt[-1],soe0))
        
    df2['batt'] = batt
    df2['soe'] = soe

    df2['utility'] = df2[nl_col] - df2.batt
    
    return any( df2[[tou_first<=h<=tou_last for h in df2.index.hour]].utility>(threshold+tol) ), df2

def peak_shaving_sim(df:pd.DataFrame,
                      netload_col:str,
                      soe_max:float,                      
                      thresholds:list=None,
                      TOU:list=None,
                      soe0_pu:float=1,
                      soc=True,
                      utility_chg_max:float=0):
    """Simulate peak shaving battery dispatch

    Args:
        ds_netload (pd.Series): net load vector
        thresholds (float): battery will be dispatched to keep import from utility below this value
            during threshold_h
        soe_max (float): maximum battery state of energy
        soe0 (float): initial battery state of energy
        utility_chg_max (float, optional): max absolute value that battery will charge at during 
            non-TOU hours. Defaults to 0.

    Returns:
        (bool,pd.DataFrame): sim failed for this battery size?, dispatch vectors
    """
    
    df = df.copy(deep=True) # we'll be modifying this
    interval_min = int(df.index.to_series().diff().mean().seconds/60)
    
    # TOU
    if len(TOU)>=1: threshold0_h = TOU[0]['hours']
    if len(TOU)>=2: threshold1_h = TOU[1]['hours']
    if len(TOU)>=3: threshold2_h = TOU[2]['hours']
    threshold_all_h = []
    for tou_level in TOU:
        threshold_all_h += tou_level['hours']
        
    # thresholds
    if len(thresholds)>=1: threshold0 = thresholds[0]
    if len(thresholds)>=2: threshold1 = thresholds[1]
    if len(thresholds)>=3: threshold2 = thresholds[2]
    
    soe0 = soe0_pu*soe_max
    tol = 0.001 # tolerance
    
    batt,soe = [],[]
    for netload,t in zip(df[netload_col],df[netload_col].index):
        if t.hour in threshold_all_h:
            threshold = 1e6
            if t.hour in threshold0_h:
                threshold = min(threshold,threshold0)    
            if t.hour in threshold1_h:
                threshold = min(threshold,threshold1)
            if t.hour in threshold2_h:
                threshold = min(threshold,threshold2)
            batt.append(batt_request(soe,netload-threshold,soe0,soe_max,interval_min))
        else:
            batt.append(min(0,batt_request(soe,min(netload,-utility_chg_max),soe0,soe_max,interval_min)))
        soe.append(update_soe(soe,batt[-1],soe0,interval_min))
        
    df['batt'] = batt
    df['soe'] = soe
    df['utility'] = df[netload_col] - df.batt
    if soc:
        df['soc'] = df.soe/soe_max

    # determine if there was a failure
    h_0,h_f = threshold0_h[0],threshold0_h[-1]
    failure = any( df[[h_0<=h<=h_f for h in df.index.hour]].utility>(threshold0+tol) )
    if threshold1 is not None:
        h_0,h_f = threshold1_h[0],threshold1_h[-1]
        failure = failure or any( df[[h_0<=h<=h_f for h in df.index.hour]].utility>(threshold1+tol) )    
    if threshold2 is not None:
        h_0,h_f = threshold2_h[0],threshold2_h[-1]
        failure = failure or any( df[[h_0<=h<=h_f for h in df.index.hour]].utility>(threshold2+tol) )
        

    return failure, df

def find_smallest_soe0(df2,
                       net_load_col,
                       threshold,
                       batt_kwh_max,
                       TOU_hours,
                       step=1,
                       output=True,
                       utility_max_chg_pu=None,
                       utility_max_chg=100000,
                       soe0_pu=1):        
    
    # Find a good initial batter kwh capacity by scaling the passed value
    for multiplier in [1,1.1,2,5,10,25,100]:
        batt_kwh = batt_kwh_max*multiplier
        fail,_ = peak_shaving_sim(df2,net_load_col,threshold,batt_kwh,TOU_hours,soe0_pu,min(utility_max_chg_pu*batt_kwh,utility_max_chg))
        if not fail:
            break
        else:
            print(f'No solution found for battery max kWh multiplier = {multiplier}')
            step = step * 10**order_of_magnitude(multiplier) # increase step with order of magnitude of multiplier
    
    # Find the lowest batt_kwh without peak shaving failures
    if fail == False:
        for kwh in [x*step for x in range(int(batt_kwh/step),0,-1)]:
            fail,_ = peak_shaving_sim(df2,net_load_col,threshold,kwh,TOU_hours,soe0_pu,min(utility_max_chg_pu*kwh,utility_max_chg))
            if fail == True:
                break
    else:
        print('Get out of here with your AAA batteries!!')
        return 0,df2
                
    # Solution is the smallest size that didn't fail
    kwh += step
    fail,df3 = peak_shaving_sim(df2,net_load_col,threshold,kwh,TOU_hours,soe0_pu,min(utility_max_chg_pu*kwh,utility_max_chg))
    if (fail == False) and output:
        print(f'Solution found: {net_load_col}, Threshold kw = {threshold:.1f}, Battery kWh = {kwh:.1f},')
    else:
        print(f'Failure to find solution: {net_load_col}, Threshold kw = {threshold:.1f}, Battery kWh max = {batt_kwh_max:.1f},')

    return kwh,df3

def calc_power_cost(ds:pd.Series,tou:list,peak_interval_min:int=60)->float:
    ds = ds.resample(f'{peak_interval_min}min').mean()
    cost = 0
    for tou_level in tou:
        price,hours = tou_level['price'],tou_level['hours']
        cost += ds[[True if h in hours else False for h in ds.index.hour]].max() * price
    return cost


def f(thresholds,df_month,angle,batt_kwh,tou):
    th0,th1,th2 = thresholds
    fail,dispatch = peak_shaving_sim(   df_month,
                                    f'netload_{angle}',
                                    batt_kwh,
                                    [th0,th1,th2],
                                    tou,
                                    utility_chg_max=batt_kwh,)                
    cost = calc_power_cost(dispatch.utility,tou)
    return cost,fail,dispatch

def grad_f(th_i,df_month,angle,batt_kwh,tou):
    #c,fail,_ = f(th_i)
    
    d = 0.05
    
    c0_0,fail,_ = f([x+dx for x,dx in zip(th_i,[-d,0,0])],df_month,angle,batt_kwh,tou)
    if fail == True: c0_0,fail,_ = f(th_i,df_month,angle,batt_kwh,tou)
    c0_1,fail,_ = f([x+dx for x,dx in zip(th_i,[d,0,0])],df_month,angle,batt_kwh,tou)
    if fail == True: c0_1,fail,_ = f(th_i,df_month,angle,batt_kwh,tou)
    
    
    c1_0,fail,_ = f([x+dx for x,dx in zip(th_i,[0,-d,0])],df_month,angle,batt_kwh,tou)
    if fail == True: c1_0,fail,_ = f(th_i,df_month,angle,batt_kwh,tou)
    c1_1,fail,_ = f([x+dx for x,dx in zip(th_i,[0,d,0])],df_month,angle,batt_kwh,tou)
    if fail == True: c1_1,fail,_ = f(th_i,df_month,angle,batt_kwh,tou)
    
    
    c2_0,fail,_ = f([x+dx for x,dx in zip(th_i,[0,0,-d])],df_month,angle,batt_kwh,tou)
    if fail == True: c2_0,fail,_ = f(th_i,df_month,angle,batt_kwh,tou)
    c2_1,fail,_ = f([x+dx for x,dx in zip(th_i,[0,0,d])],df_month,angle,batt_kwh,tou)
    if fail == True: c2_1,fail,_ = f(th_i,df_month,angle,batt_kwh,tou)

    
    return (c0_0-c0_1,c1_0-c1_1,c2_0-c2_1)

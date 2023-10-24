""" Bifacial Peak Shaving
"""
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

def batt_request(soe,power,soe0):
    if len(soe) == 0:
        last_soe = soe0
    else:
        last_soe = soe[-1]
        
    if power > 0: # discharge
        power = min(power,last_soe*0.9)
    elif power < 0: # charge
        power = max(power,-1*(soe0-last_soe)/.9)
    else:
        power = 0
    return power

def update_soe(soe,power,soe0):
    if len(soe) == 0:
        last_soe = soe0
    else:
        last_soe = soe[-1]
            
    if power > 0: # discharge
        next_soe = last_soe - power/0.9
    elif power < 0: # charge
        next_soe = last_soe - power*0.9
    else:
        next_soe = last_soe
        
    return next_soe

def peak_shaving_sim(df2,nl_col,threshold,soe0,TOU_hours):
    tol = 0.001 # tolerance
    df2 = df2.copy(deep=True)
    tou_first,tou_last = TOU_hours[0],TOU_hours[-1]
    batt,soe = [],[]    
    for net_load,t in zip(df2[nl_col],df2.index):
        if t.hour in TOU_hours:
            batt.append(batt_request(soe,net_load-threshold,soe0))
        else:
            batt.append(min(0,batt_request(soe,net_load-threshold,soe0)))
        soe.append(update_soe(soe,batt[-1],soe0))
        
    df2['batt'] = batt
    df2['soe'] = soe

    df2['utility'] = df2[nl_col] - df2.batt
    
    return any( df2[[tou_first<=h<=tou_last for h in df2.index.hour]].utility>(threshold+tol) ), df2

def find_smallest_soe0(df2,net_load_col,threshold,batt_kwh_max,TOU_hours,step=1,output=True):
    
    # Determine a good starting (max) batt_kwh
    batt_kwh = batt_kwh_max
    fail,df3 = peak_shaving_sim(df2,net_load_col,threshold,batt_kwh,TOU_hours)
    if fail == True:
        print('Failed on first battery size, try 1.1x')
        batt_kwh = batt_kwh_max*1.1
        fail,df3 = peak_shaving_sim(df2,net_load_col,threshold,batt_kwh,TOU_hours)
        if fail == True:
            print('Failed on first battery size, try 2x')
            batt_kwh = batt_kwh_max*2
            fail,df3 = peak_shaving_sim(df2,net_load_col,threshold,batt_kwh,TOU_hours)
            if fail == True:
                print('Failed on first battery size, try 5x')
                batt_kwh = batt_kwh_max*5
                fail,df3 = peak_shaving_sim(df2,net_load_col,threshold,batt_kwh,TOU_hours)
                if fail == True:
                    print('Failed on first battery size, try 10x')
                    batt_kwh = batt_kwh_max*10
                    fail,df3 = peak_shaving_sim(df2,net_load_col,threshold,batt_kwh,TOU_hours)
                    if fail == True:
                        print('Get outta here with your AA batteries!')
    
    # Find the lowest batt_kwh without peak shaving failures
    if fail == False:
        for kwh in [x*step for x in range(int(batt_kwh/step),0,-1)]:
            fail,df3 = peak_shaving_sim(df2,net_load_col,threshold,kwh,TOU_hours)
            if fail == True:
                if kwh==batt_kwh:
                    print('Failed on first battery size, try larger')
                    break
                else:
                    break
                
    # Solution is the smallest size that didn't fail
    kwh += step
    fail,df3 = peak_shaving_sim(df2,net_load_col,threshold,kwh,TOU_hours)
    if (fail == False) and output:
        print(f'Solution found: {net_load_col}, Threshold kw = {threshold:.1f}, Battery kWh = {kwh:.1f},')
    else:
        print(f'Failure to find solution: {net_load_col}, Threshold kw = {threshold:.1f}, Battery kWh max = {batt_kwh_max:.1f},')

    return kwh,df3
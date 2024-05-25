""" utils.py
Generally useufl utility functions
"""

__version__ = 28

import os
import sys
import shutil
import math
import yaml
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from plotly.subplots import make_subplots
from src.post_and_poll import get_api_results

class dotdict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__
    
def setup(config_file:str=None) -> dotdict:
    
    if config_file is not None:
        #cfg = dotdict(json.load(open(config_file, 'r')))
                
        with open(config_file, 'r') as stream:
            d=yaml.safe_load(stream)
        cfg = dotdict(d)

    
    note = ''

    if len(sys.argv) > 1:
        for i, arg in enumerate(sys.argv[1:]):
            if arg[:3] == '--f':
                break
            if arg[-4:] == 'json':
                config_file = arg
                cfg = dotdict(json.load(open(config_file, 'r')))
            if arg == '-a':
                cfg.solar_angles = [sys.argv[i + 2]]
                note += f'a{sys.argv[i + 2]}_'
            if arg == '-s':
                cfg.solar_scaler = float(sys.argv[i + 2])
                note += f's{cfg.solar_scaler:.1f}_'
            if arg == 'TEST':
                cfg.test = True
                note += 'TEST_'             
            if arg == '-n':
                note += sys.argv[i + 2] + '_'     
                cfg = dotdict(json.load(open(config_file, 'r')))
                
    cfg['filename'] = config_file           
                
    if cfg.dev:
        note += 'DEV_'
    if 'energy_price_sell_vector' in cfg.keys():
        cfg.energy_price_sell_vector = pd.read_csv( cfg.energy_price_sell_vector,
                                                    comment='#',
                                                    index_col=0,
                                                    parse_dates=True)
    if cfg.note is not None:
        note += cfg.note + '_'
    else:
        note = ''
        
    cfg.solar_file = cfg.data_dir + cfg.solar_file
    cfg.load_file = cfg.data_dir + cfg.load_file
    cfg.tariff_file = cfg.data_dir + cfg.tariff_file

    # outputs dir
    cfg.output_filename_stub = (f'{cfg.out_dir}{config_file.split(".")[0]}_v{__version__}_{note}')

    tou = {}
    for key in cfg.keys():
        if key[:3] == 'tou':
            tou[key] = cfg[key]
    cfg.tou = tou
    
    # check version number
    assert cfg.version == __version__, f'Version mismatch: {cfg.version} != {__version__}'                    

    # create output directory
    tic = pd.Timestamp.now()
    cfg.outdir = cfg.output_filename_stub + tic.strftime('%y.%m.%d-%H.%M') + '/'
    if not os.path.exists(cfg.outdir):
        os.mkdir(cfg.outdir)
    else:
        cfg.outdir = cfg.outdir[:-1]+tic.strftime('.%S') + '/'
        os.mkdir(cfg.outdir)
        
    # copy over yaml config
    shutil.copyfile(cfg.filename, cfg.outdir+cfg.filename)
    
    with open(cfg.tariff_file, 'r') as f:
        tariff = json.load(f)
        
    load = pd.read_csv(cfg.load_file,
                       index_col=0,
                       parse_dates=True)[[cfg.load_col]]
    load = load.resample('1h').mean()   

    return cfg,tariff,load
    
def import_series(name,downsample=False):
    df = pd.read_csv(name,header=None)
    if downsample:
        df = pd.DataFrame(df.values.flatten(),
                        index=pd.date_range(start='2019-1-1 0:00', periods=35040, freq='15min'))
        df = df.resample('1h').mean()                                            
    return list(df.values.flatten())

def import_df(name,col,t0=None,scale=None,resamp=None):
    df = pd.read_csv(name,index_col=0,comment='#',parse_dates=True)
    deltaT = int(df.index.to_series().diff().dropna().mean().seconds/60)
    L = int(60/deltaT * 8760)
    if t0 is None:
        df = df[col][:L]
    else:
        df = df[col][t0:][:L]
    if scale is not None:
        df = df/scale
    if resamp is not None:
        df = df.resample(resamp).mean()
    df[df<0] = 0
    return list(df.values.flatten())

def import_json(name):
    with open(name, 'r') as fp:
        jsondict = json.load(fp)
    return jsondict

def export_json(jsondict,outdir):
    with open(outdir+'post.json', 'w') as fp:
        json.dump(jsondict, fp)

def parse_dispatch_series(_api_response):
    load            = _api_response["outputs"]["ElectricLoad"]["load_series_kw"]
    grid_to_batt    = _api_response["outputs"]["ElectricUtility"]["electric_to_storage_series_kw"]
    pv_to_batt      = _api_response["outputs"]["PV"]["electric_to_storage_series_kw"]
    size_kw         = _api_response["outputs"]["PV"]["size_kw"]
    pv  = [x*size_kw for x in _api_response["outputs"]["PV"]["production_factor_series"]]
    if 'ElectricStorage' in _api_response['outputs'].keys():
        batt_to_load    = _api_response["outputs"]["ElectricStorage"]["storage_to_load_series_kw"]
        soc             = _api_response["outputs"]["ElectricStorage"]["soc_series_fraction"]
        #soc = [x*post['ElectricStorage']['max_kwh'] for x in soc]
        batt = [a-b-c for a,b,c in zip(batt_to_load, grid_to_batt, pv_to_batt, )]
    
    #buy             = pd.read_csv('electric_rates/jplv4_price-buy_aut19_35040.csv',header=None)
    #buy.index       = pd.date_range(start='2019-1-1', periods=35040, freq='15T')
    #buy.columns     = ['buy']
    #sell            = pd.read_csv('electric_rates/jplv4_price-sell_aut19_35040.csv',header=None)
    #sell.index      = pd.date_range(start='2019-1-1', periods=35040, freq='15T')
    #sell.columns    = ['sell']
    
    #p = pd.concat((buy,sell),axis=1).resample('1h').mean()

    if 'ElectricStorage' in _api_response['outputs'].keys():
        df = pd.DataFrame({'load':load,'pv':pv,'batt':batt,'soc':soc},
                        index=pd.date_range('2019-1-1 0:00',periods=8760,freq='1h'))
        #df = pd.concat((df,p),axis=1)
        df['grid'] = df['load'] - df['pv'] - df['batt']
    else:
        df = pd.DataFrame({'load':load,'pv':pv},
                        index=pd.date_range('2019-1-1 0:00',periods=8760,freq='1h'))
        df['grid'] = df['load'] - df['pv']

    #df = df['2019-10-14':'2019-10-28']

    #df['cost'] = df[df.grid>0].grid * df[df.grid>0].buy * -1
    #df['revenue'] = df[df.grid<0].grid * df[df.grid<0].sell * -1
    df.fillna(0, inplace=True)

    #df.to_csv('dispatch_series.csv')
    
    return df    
        
def plotly_stacked(df,
                solar='solar',
                solar_name='Solar',
                solar_forecast='solar_forecast',
                solar_forecast_name='Solar Forecast',
                load='load',
                load_name='Load',
                load_forecast='load_forecast',
                load_forecast_name='Load Forecast',
                batt='batt',
                discharge='discharge',
                discharge_name='Battery Discharge',
                charge='charge',
                load_charge_name='Load + Charge',
                utility='utility',
                utility_name='Utility',        
                soc='soc',
                soc_name='SOC (right axis)',
                soe='soe',
                soe_name='SOE (right axis)',
                threshold0=None,
                threshold0_h=None,
                threshold1=None,
                threshold1_h=None,
                threshold2=None,
                threshold2_h=None,
                ylim=None,
                size=None,
                title=None,
                fig=None,
                units_power='kW',
                units_energy='kWh',
                round_digits=1,
                upsample_min=None,
                theme='plotly'):
    """ Make plotly graph with some data stacked in area-fill style
    """
    
    df = df.copy(deep=True) # we'll be modifying this
    
    # upsample for more accurate viewing
    if upsample_min is not None:
        freq_min = int(df.index.to_series().diff().dropna().mean().seconds/60)
        new_length = len(df) * (freq_min / upsample_min)
        df = upsample_df(df,freq=f'{upsample_min}min',periods=new_length)
        
    # threshold vectors
    if threshold0 is not None:
        df['threshold0'] = [threshold0 if x in threshold0_h else pd.NA for x in df.index.hour]
    if threshold1 is not None:
        df['threshold1'] = [threshold1 if x in threshold1_h else pd.NA for x in df.index.hour]
    if threshold2 is not None:
        df['threshold2'] = [threshold2 if x in threshold2_h else pd.NA for x in df.index.hour]
    
    #export='export'
    loadPlusCharge = 'loadPlusCharge'

    if charge not in df.columns:
        df[charge] =    [max(0,-1*x) for x in df[batt]]
        df[discharge] =    [max(0,x) for x in df[batt]]    
    df[loadPlusCharge] = df[load]+df[charge]
    #df[export] = df[solar] - df[loadPlusCharge] #[-1*min(0,x) for x in df[utility]]
    df[utility] = [max(0,x) for x in df[utility]]
    df[solar] = df[solar]#df[load] - df[utility]
    
    # plot
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    

    fig.add_trace(
        go.Scatter(
            name=solar_name,
            x=df.index, y=df[solar].round(round_digits),
            mode='lines',
            stackgroup='one',
            line=dict(width=0,color='gold'),
        ),
        secondary_y=False,
    )
    if solar_forecast in df.columns:
        fig.add_trace(
            go.Scatter(
                name=solar_forecast_name,
                x=df.index, y=df[solar_forecast].round(round_digits),
                mode='lines',
                #stackgroup='one',
                line=dict(width=1.5, dash='dash',color='orange'),
            ),
            secondary_y=False,
        )
    fig.add_trace(
        go.Scatter(
            name=utility_name,
            x=df.index, y=df[utility].round(round_digits),
            mode='lines',
            stackgroup='one',
            line=dict(width=0, color='darkseagreen'),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name=discharge_name,
            x=df.index, y=df[discharge].round(round_digits),
            mode='lines',
            stackgroup='one',
            line=dict(width=0, color='dodgerblue'),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name=load_charge_name,
            x=df.index, y=df[loadPlusCharge].round(round_digits),
            mode='lines',
            #stackgroup='one',
            line=dict(width=1.5, color='dodgerblue'),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name=load_name,
            x=df.index, y=df[load].round(round_digits),
            mode='lines',
            #stackgroup='one',
            line=dict(width=1.5, color='indigo'),
        ),
        secondary_y=False,
    )
    if load_forecast in df.columns:
        fig.add_trace(
            go.Scatter(
                name=load_forecast_name,
                x=df.index, y=df[load_forecast].round(round_digits),
                mode='lines',
                #stackgroup='one',
                line=dict(width=1.5, dash='dash',color='indigo'),
            ),
            secondary_y=False,
        )
    if threshold0 is not None:
        if threshold1 is None:
            name = 'Threshold'
        else:
            name = 'Threshold 0'
        fig.add_trace(
            go.Scatter(
                name=name,
                x=df.index, y=df['threshold0'],
                mode='lines',
                #stackgroup='one',
                line=dict(width=1.5, color='palevioletred'),
            ),
            secondary_y=False,
        )
    if threshold1 is not None:
        fig.add_trace(
            go.Scatter(
                name='Threshold 1',
                x=df.index, y=df['threshold1'],
                mode='lines',
                #stackgroup='one',
                line=dict(width=1.5, color='mediumvioletred'),
            ),
            secondary_y=False,
        )
    if threshold2 is not None:
        fig.add_trace(
            go.Scatter(
                name='Threshold 2',
                x=df.index, y=df['threshold2'],
                mode='lines',
                #stackgroup='one',
                line=dict(width=1.5, color='crimson'),
            ),
            secondary_y=False,
        )        
    if soc in df.columns:
        fig.add_trace(
            go.Scatter(
                name=soc_name,
                x=df.index, y=(df[soc]*100).round(round_digits),
                mode='lines',
                line=dict(width=1, dash='dot',color='coral'),
            ),
            secondary_y=True,
        ) 
    elif soe in df.columns:
        fig.add_trace(
            go.Scatter(
                name=soe_name,
                x=df.index, y=df[soe].round(round_digits),
                mode='lines',
                line=dict(width=1, dash='dot',color='coral'),
            ),
            secondary_y=True,
        )
        
    fig.update_traces(hovertemplate=None)#, xhoverformat='%{4}f')
    fig.update_layout(hovermode='x',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation='h'),
                    legend_traceorder='reversed',
                    template=theme,
                    title=title,)
    if size is not None:
        fig.update_layout(width=size[0],height=size[1])
    
    if soc in df.columns:
        fig.update_yaxes(title_text='%',range=(0, 100),secondary_y=True)
    elif soe in df.columns:
        fig.update_yaxes(title_text=units_energy,range=(0, df[soe].max()),secondary_y=True)

    else:
        fig.update_yaxes(title_text=units_power, secondary_y=False)

    if ylim is None:
        ymax = max(df[loadPlusCharge].max(),df[utility].max(),df[solar].max())
        if load_forecast in df.columns:
            ymax = max(ymax,df[load_forecast].max())
        fig.update_yaxes(range=(-.025*ymax, 1.1*ymax),secondary_y=False)
    else:
        fig.update_yaxes(range=(ylim[0], ylim[1]),secondary_y=False)
        
    fig.show()
    
    return fig
        
def calc_ac(ds:pd.Series,shifts:list)->pd.DataFrame:
    ''' Calculate autocorrelation of a data series "ds" for lag values "shifts".
    Return a list of autocorrelation values, one value for each shift in "shifts."'''
    ac = []
    for s in shifts:
        ac.append( pd.concat((ds,ds.shift(s)),axis=1).corr().iloc[0,1] )
        
    ac = pd.DataFrame({'autocorr':ac},index=shifts)
    ac.index = ac.index.rename('lag timesteps')
    return ac

def calc_mae(true:pd.Series,pred:pd.Series,normalize=1)->float:
    ''' Calculate mean absolute error between two series "true" and "pred"'''
    if normalize is True:
        normalize = max(true.max(),pred.max())
    return (true/normalize - pred/normalize).abs().mean()

def calc_mae2(true,pred,normalize=False):
    if normalize:
        norm = np.max(true)
    else:
        norm = 1
    return np.mean(np.abs(true.values/norm-pred.values/norm))

def order_of_magnitude(x:float)->int:
    """ Calculate order of magnitude

    Args:
        x (float): real number

    Returns:
        int: order of magnitude
    """
    
    return math.floor(math.log(x, 10))


def upsample_df(df,periods,freq,method='ffill'):
    df2 = pd.DataFrame([],index=pd.date_range(df.index[0],periods=periods,freq=freq))
    for col in df.columns:
        df2.loc[df.index,col] = df[col].values
    df2 = df2.fillna(method=method)
    return df2


def shift_and_wraparound(ds:pd.Series,i:int):
    """ Shift data and wraparound the end
    pos = shift left/up
    neg = shift right/down
    """
    return list(ds.values[i:]) + list(ds.values[:i])
    
    
def calc_monthly_peaks(ds:pd.Series,peak_begin:int,peak_end:int) -> pd.Series:
    """ Calculate max power (1 hr non-moving average) of the month

    Args:
        ds (pd.Series): timeseries to calculate on
        peak_begin (int): start of peak TOU period (inclusive)
        peak_end (int): end of peak TOU period (exclusive)

    Returns:
        pd.Series: _description_
    """
    peak,ipeak = [],[]
    for month in ds.index.month.unique():
        ds_month = ds[ds.index.month==month]
        idx = [peak_begin<=h<peak_end for h in ds_month.index.hour]
        peak.append( ds_month[idx].max().round(1))
        ipeak.append(ds_month[idx].idxmax())

    results = pd.DataFrame({f'{ds.name} kw':peak,
                            f'{ds.name} t':ipeak,})
    results.index = list(range(1,13))
    return results

def calc_monthly_peaks2(ds:pd.Series,peak_hours:list) -> pd.Series:
    """ Calculate max power (1 hr non-moving average) of the month

    Args:
        ds (pd.Series): timeseries to calculate on
        peak_hours (list): hour for which peak applies

    Returns:
        pd.Series: _description_
    """
    if len(peak_hours) == 0:
        return None
    else:
        peak,ipeak = [],[]
        for month in ds.index.month.unique():
            ds_month = ds[ds.index.month==month]
            peak.append( ds_month[ds_month.index.hour.isin(peak_hours)].max().round(1))
            ipeak.append(ds_month[ds_month.index.hour.isin(peak_hours)].idxmax())

        results = pd.DataFrame({f'{ds.name} kw':peak,
                                f'{ds.name} t':ipeak,})
        results.index = list(range(1,13))
        return results

def create_post(cfg:str,
                solar_kw:float=None,
                batt_kw:float=None,
                batt_h:float=None,
                solar_kw_range=False,
                batt_kw_range=False,
                batt_h_range=False,
                load_kw_series:pd.Series=None,
                solar_kw_series:pd.Series=None,
                load_col:str=None):
    
    # Defaults
    if solar_kw is None: solar_kw = cfg.solar_kw
    if batt_kw is None: batt_kw = cfg.batt_kw
    if batt_h is None: batt_h = cfg.batt_h
    if load_col is None: load_col = cfg.load_col

    post = cfg.post    
    
    # Solar
    post['PV'].update({ "min_kw":solar_kw,
                        "max_kw":solar_kw,            
                        "production_factor_series":import_df(cfg.solar_file,
                                                             cfg.solar_col,
                                                             resamp=cfg.solar_resamp,
                                                             scale=cfg.solar_scaler)})
    if solar_kw_series is not None:
        post['PV'].update({"production_factor_series":list(solar_kw_series.values / solar_kw_series.max())})                           
    if solar_kw_range:
        post['PV'].update({ "min_kw":0})
        
    # Load
    post['ElectricLoad'].update({'loads_kw':import_df(cfg.load_file,
                                                      load_col,
                                                      resamp=cfg.load_resamp),
                                 'year':cfg.year})
    if load_kw_series is not None:
        post['ElectricLoad'].update({'loads_kw':list(load_kw_series.values),
                                     'year':load_kw_series.index[0].year})

    # Battery            
    post['ElectricStorage'].update({
            "min_kw":batt_kw,               "max_kw":batt_kw,
            "min_kwh":batt_kw*batt_h,       "max_kwh":batt_kw*batt_h,})
    if batt_kw_range:
        post['ElectricStorage'].update({"min_kw":0})
    if batt_h_range:
        post['ElectricStorage'].update({"min_kwh":0})    


    # Tariff
    post["ElectricTariff"].update({"urdb_response":import_json(cfg.tariff_file),})
    if 'energy_price_sell_constant' in cfg.keys():
        post["ElectricTariff"].update({
            'wholesale_rate':[cfg.energy_price_sell_constant]*(8760*post['Settings']['time_steps_per_hour'])})
    elif 'energy_price_sell_file' in cfg.keys():
        post["ElectricTariff"].update({
            'wholesale_rate':import_df(cfg.data_dir+'/'+cfg.energy_price_sell_file,
                                       cfg.energy_price_sell_col)                       })
    
    export_json(post,cfg.outdir)
    
    return post

def run_reopt(post, print_results=False,api_key=None):

    outputs_file_name = "results_file"
    root_url = "https://developer.nrel.gov/api/reopt/stable" # /stable == /v3 
    
    tries = 1
    success = False
    
    while not success and tries < 6:
        print(f'Trying API request: {tries}')
    
        try:
            api_response = get_api_results(post=post, 
                                        API_KEY=api_key, 
                                        api_url=root_url, 
                                        results_file= f'outputs/{outputs_file_name}.json', 
                                        run_id=None)
        except:
            print('API request failed')
    
        if api_response is not None:
            if 'PV' in api_response['outputs'].keys():
                if 'ElectricTariff' in api_response['outputs'].keys():
                    if 'ElectricLoad' in api_response['outputs'].keys():    
                        success = True
                        print('Success!')
        else:
            tries += 1
                        
    if not success:
        print('API request failed')
        quit()
        api_response = None
    else:
        energy_cost =      api_response["outputs"]["ElectricTariff"]["year_one_energy_cost_before_tax"]
        demand_cost =      api_response["outputs"]["ElectricTariff"]["year_one_demand_cost_before_tax"]
        fixed_cost =      api_response["outputs"]["ElectricTariff"]["year_one_fixed_cost_before_tax"]
        min_chg_adder =      api_response["outputs"]["ElectricTariff"]["year_one_min_charge_adder_before_tax"]
        energy_revenue =   api_response["outputs"]["ElectricTariff"]["year_one_export_benefit_before_tax"]
        netcost =   energy_cost + demand_cost + fixed_cost + min_chg_adder - energy_revenue
        npv =       api_response['outputs']['Financial']['npv']
        spp =       api_response['outputs']['Financial']['simple_payback_years']

        if api_response["status"] != "optimal":
            print('Error!: not optimal', api_response["status"])

        if print_results:    
            print('Status = ',              api_response["status"])
            print("Energy cost ($) = ",     energy_cost)
            print("Demand cost ($) = ",     demand_cost)
            print('Fixed cost ($) = ',  fixed_cost)
            print('Min charge adder ($) = ',  min_chg_adder)
            print('Energy revenue ($) = ',  energy_revenue)
            print('Net cost ($) = ',        netcost)
            #print('NPV ($) and Payback Period (y) = ',        npv, spp)
            print('')
            print('PV Size (kW) = ',        api_response["outputs"]["PV"]["size_kw"])
            if "ElectricStorage" in api_response["outputs"].keys():
                print('Storage Size (kW-kwh) = ',api_response["outputs"]["ElectricStorage"]["size_kw"],'-',api_response["outputs"]["ElectricStorage"]["size_kwh"])
        
    return api_response#, energy_cost, demand_cost, netcost
    
def indices_equal_to_value(l:list,v:int) -> list:
    return [i for i, x in enumerate(l) if x == v]

def indices_not_equal_to_value(l:list,v:int) -> list:
    return [i for i, x in enumerate(l) if x != v]

def build_price_vectors(index:pd.DatetimeIndex,tariff:dict,cfg:dict) -> pd.DataFrame:
    prices = {'energy':[],'demand':[]}

    for t in index:

        if t.weekday() in [0,1,2,3,4]:
            weekend_or_weekday = 'weekday'
        else:
            weekend_or_weekday = 'weekend'

        tou_level = tariff[f'demand{weekend_or_weekday}schedule'][t.month-1][t.hour]
        demand_rate = tariff['demandratestructure'][tou_level][0]['rate']
        prices['demand'].append(demand_rate)

        tou_level = tariff[f'energy{weekend_or_weekday}schedule'][t.month-1][t.hour]
        energy_rate = tariff['energyratestructure'][tou_level][0]['rate']
        prices['energy'].append(energy_rate)
        
    if 'energy_price_sell_constant' in cfg.keys():
        sell_prices = [cfg.energy_price_sell_constant]*(8760*cfg['post']['Settings']['time_steps_per_hour'])
    
    elif 'energy_price_sell_file' in cfg.keys():
        sell_prices = import_df(cfg.data_dir+'/'+cfg.energy_price_sell_file,
                                cfg.energy_price_sell_col)
        
    prices['sellback'] = sell_prices

    prices = pd.DataFrame(prices,index=index)
    return prices

def calc_demand_charge(month:int,prices:pd.DataFrame,tariff:dict,load:pd.Series) -> float:
    if load.name is None:
        load.name = 'P(kW)'
    demand_rate_structure = [x[0]['rate'] for x in tariff['demandratestructure']]
    nonzero_demand_rate_levels = indices_not_equal_to_value(demand_rate_structure,0)
    
    demand_charge = 0
    for tou_level in nonzero_demand_rate_levels:    
        tou_hours = indices_equal_to_value(tariff['demandweekdayschedule'][month-1],tou_level)
        monthly_peaks = calc_monthly_peaks2(load,tou_hours)

        if monthly_peaks is not None:
            demand_rate = prices.loc[monthly_peaks[f'{load.name} t'][month]].demand
            demand = monthly_peaks[f'{load.name} kw'][month]
        else: # this tou_level is not in effect for this month
            demand_rate = 0
            demand = 0

        demand_charge += demand * demand_rate
        
    return demand_charge

def calc_energy_charge(month:int,prices:pd.Series,load:pd.Series) -> float:
    load_pos = load.copy(deep=True)
    load_pos[load_pos<0] = 0
    energy_cost = (prices[prices.index.month==month] * load_pos[load_pos.index.month==month]).sum()
    
    #load_neg = load.copy(deep=True)
    #load_neg[load_neg>0] = 0
    #load_neg = load_neg * -1
    #energy_revenue = sum([x*y for x,y in zip([0.054]*len(load_neg),load_neg[load_neg.index.month==month])])
    
    return energy_cost# + energy_revenue

def calc_energy_revenue(month:int,prices:pd.Series,load:pd.Series) -> float:
    #load_pos = load.copy(deep=True)
    #load_pos[load_pos<0] = 0
    #energy_cost = (prices[prices.index.month==month] * load_pos[load_pos.index.month==month]).sum()
    
    load_neg = load.copy(deep=True)
    load_neg[load_neg>0] = 0
    load_neg = load_neg * -1
    energy_revenue = (prices[prices.index.month==month] * load_neg[load_neg.index.month==month]).sum()
    
    return energy_revenue

def calc_retail_electric_cost(dispatch:pd.DataFrame,tariff:dict,cfg:dict,month=None,grid_col='grid'):
    ''' Option to pass a single month or a all 12 months are calculated
    '''
    if month is None:
        months = list(range(1,13))
    else:
        months = [month]
    demand_charge = 0
    energy_charge = 0
    energy_revenue = 0
    for month in months:
        prices = build_price_vectors(dispatch.index,tariff,cfg)
        demand_charge += round(calc_demand_charge(month,prices,tariff,dispatch.loc[:,grid_col]),1)
        energy_charge += round(calc_energy_charge(month,prices.energy,dispatch.loc[:,grid_col]),1)
        energy_revenue += round(calc_energy_revenue(month,prices.sellback,dispatch.loc[:,grid_col]),1)
    return dotdict({'energy':energy_charge,
            'demand':demand_charge,
            'sellback':energy_revenue,
            'total':demand_charge+energy_charge-energy_revenue})
    
def load_sellback_prices(filename):
    prices = pd.read_csv(filename,
                         index_col=0,
                         parse_dates=True,
                         comment='#')
    return list(prices.iloc[:,1])
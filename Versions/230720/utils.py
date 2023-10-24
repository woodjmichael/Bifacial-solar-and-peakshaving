""" utils.py
Generally useufl utility functions
"""

import pandas as pd
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from plotly.subplots import make_subplots  

def plot_weekly(ds,
                title:str=None,
                ylabel:str=None,
                interval_min:int=60,
                alpha:float=0.1,
                begin_on_monday:bool=True,
                colors:list=['indigo','gold','magenta']):
    """ Plot a series with weeks super-imposed on each other. Index should be complete (no gaps)
    for this to work right. Trims any remaining data after an integer number of weeks.

    Args:
        ds (pd.Series or list): pandas series(es) to plot
        title (str, optional): title
        ylabel (str, optional): what to call the y-axis        
        interval_min (int): timeseries data interval
        alpha (float, optional): transparency of plot lines, defaults to 0.1
        begin_on_monday (bool, optional): have the first day on the plot be monday, defaults to True
        colors (list, optional): list of colors strings
    """
    dpd = int(24*60/interval_min) # data per day
    plt.figure(figsize=(10,5))
    t = [x/dpd for x in range(7*dpd)] # days    
    if not isinstance(ds,(list,tuple)):
        ylabel = ds.name
        ds = [ds]
    for ds2,color in zip(ds,colors):
        ds2 = ds2.copy(deep=True)
        dt_start = ds2.index.min()
        if dt_start != dt_start.floor('1d'):
            dt_start = dt_start.floor('1d') + pd.Timedelta(hours=24)
        if begin_on_monday and (dt_start.weekday() != 0):
            days = 7 - dt_start.weekday()
            dt_start += pd.Timedelta(hours=24*days)
        ds2 = ds2[dt_start:]
        n_weeks = len(ds2)//(7*dpd)
        ds2 = ds2.iloc[:int(n_weeks*7*dpd)]
        if len(ds)>1:
            plt.plot(t,ds2.values.reshape(n_weeks,7*dpd).T,color,alpha=alpha)
        else:
            plt.plot(t,ds2.values.reshape(n_weeks,7*dpd).T,alpha=alpha)
    plt.ylabel(ylabel)
    plt.xlabel('Days from Monday 0:00')
    plt.title(title)
    if len(ds)>1:
        legend_items = []
        for s,color in zip(ds,colors):
            legend_items.append(mpatches.Patch(color=color, label=s.name))
        plt.legend(handles=legend_items)
    plt.show()    
    
def plot_daily(ds:pd.Series,
               interval_min:int,
               alpha:float=0.1,
               title=None):
    """ Plot a series with days super-imposed on each other. Index should be complete (no gaps)
    for this to work right. Trims any remaining data after an integer number of days.

    Args:
        ds (pd.Series): pandas series to plot
        interval_min (int): timeseries data interval
        alpha (float, optional): transparency of plot lines, defaults to 0.1
        begin_on_monday (bool, optional): have the first day on the plot be monday, defaults to True
    """
    dpd = int(24*60/interval_min) # data per day
    ds2 = ds.copy(deep=True)
    dt_start = ds.index.min()
    if dt_start != dt_start.floor('1d'):
        dt_start = dt_start.floor('1d') + pd.Timedelta(hours=24)
    ds2 = ds2[dt_start:]
    n_days = len(ds2)//(dpd)
    ds2 = ds2.iloc[:int(n_days*dpd)]
    
    t = list(range(24)) # hours
    plt.plot(t, ds2.values.reshape(n_days,dpd).T,alpha=alpha)
    plt.ylabel(ds.name)
    plt.xlabel('Hours from 0:00')
    plt.title(title)
    plt.show()

    
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

def plotly_stacked(df1,
                   solar='solar',
                   load='load',
                   batt='batt',
                   discharge='discharge',
                   charge='charge',
                   utility='utility',
                   soc='soc',
                   soe='soe',
                   ylim=None,
                   title=None,
                   fig=None,
                   units_power='kW',
                   units_energy='kWh',
                   round_digits=1):
    ''' Make plotly graph with some data stacked in area-fill style'''
    
    df = df1.copy(deep=True)
    #export='export'
    loadPlusCharge = 'loadPlusCharge'
    
    for col in df.columns:
        df[col] = df[col].round(round_digits)

    if charge not in df.columns:
        df[charge] =    [max(0,-1*x) for x in df[batt]]
        df[discharge] =    [max(0,x) for x in df[batt]]    
    df[loadPlusCharge] = df[load]+df[charge]
    #df[export] = df[solar] - df[loadPlusCharge] #[-1*min(0,x) for x in df[utility]]
    df[utility] = [max(0,x) for x in df[utility]]
    df[solar] = df[solar]#df[load] - df[utility]
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(
        go.Scatter(
            name='Utility Import',
            x=df.index, y=df[utility],
            mode='lines',
            stackgroup='one',
            line=dict(width=0, color='darkseagreen')
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name='Solar',
            x=df.index, y=df[solar],
            mode='lines',
            stackgroup='one',
            line=dict(width=0,color='gold'),
        ),
        secondary_y=False,
    )
    # fig.add_trace(
    #     go.Scatter(
    #         name='Export',
    #         x=df.index, y=df[export],
    #         mode='lines',
    #         stackgroup='one',
    #         line=dict(width=0,color='khaki'),
    #     ),
    #     secondary_y=False,
    # )
    fig.add_trace(
        go.Scatter(
            name='Battery Discharge',
            x=df.index, y=df[discharge],
            mode='lines',
            stackgroup='one',
            line=dict(width=0, color='dodgerblue'),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name='Load + Charge',
            x=df.index, y=df[loadPlusCharge],
            mode='lines',
            #stackgroup='one',
            line=dict(width=1.5, dash='dash', color='dodgerblue'),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name='Load',
            x=df.index, y=df[load],
            mode='lines',
            #stackgroup='one',
            line=dict(width=1.5, color='indigo'),
        ),
        secondary_y=False,
    )
    if soe in df.columns:
        fig.add_trace(
            go.Scatter(
                name='SOE (right axis)',
                x=df.index, y=df[soe],
                mode='lines',
                line=dict(width=1, dash='dot',color='lightcoral'),
            ),
            secondary_y=True,
        )
    elif soc in df.columns:
        fig.add_trace(
            go.Scatter(
                name='SOC (right axis)',
                x=df.index, y=df[soc],
                mode='lines',
                line=dict(width=1, dash='dot',color='lightcoral'),
            ),
            secondary_y=True,
        )            
    fig.update_traces(hovertemplate=None)#, xhoverformat='%{4}f')
    fig.update_layout(hovermode='x',
                      paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)',
                      legend=dict(orientation='h'),
                      legend_traceorder='reversed',
                      )
    
    fig.update_yaxes(title_text=units_power, secondary_y=False)
    
    if soe in df.columns:
        fig.update_yaxes(title_text=units_energy,range=(0, df[soe].max()),secondary_y=True)
    elif soc in df.columns:
        fig.update_yaxes(title_text='%',range=(0, 100),secondary_y=True)

    fig.update_layout(title=title)
    if ylim:
        fig.update_yaxes(range=(ylim[0], ylim[1]),secondary_y=False)
        
    fig.show()
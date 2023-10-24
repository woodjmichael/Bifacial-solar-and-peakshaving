# %%
import pandas as pd
from bifacial_peak_shaving import *
from _utils import *
pd.options.plotting.backend='plotly'

# %% [markdown]
# # Data

# %%
dir = './Data/'

# %% [markdown]
# ## Load

# %%
load = pd.read_csv(dir+'acn_caltech_profile_1y.csv',
                   #index_col=0,
                   #parse_dates=True,
                   comment='#',
                   usecols=[2],
                   )
                    #.resample('1h').mean()
                    #.fillna(method='ffill')
                    #.loc['2018-4-26':'2019-3-22']
#load = pd.DataFrame({'Load (kW)':list(load.loc['2019-1-2 0:00':'2019-1-2 16:00','Load (kW)'])+list(load.loc[:,'Load (kW)'])},
#                     index=pd.date_range('2019-1-1 0:00',periods=8760,freq='1h'))
#load.loc['2019-5-20'] = load.loc['2019-5-22'].values
#load.loc['2019-5-21'] = load.loc['2019-5-22'].values
load.index = pd.date_range('1901-1-1 0:00',periods=35040,freq='15min')
load = load.resample('1h').mean()
print(load.info())
#plot_weekly(load['Load (kW)'])
#load.plot()

# %%
#load.plot.box(x=load.index,y=load['Load (kW)'])

# %% [markdown]
# ## Solar
# 
# - 7 kWp, TMY
# 
# - Net zero capacity
# 
#   - $capacity[kWp] = production[kWh] \times yield [\frac{kWh}{kWp}]^{-1}$

# %%
solar_angles = ['s20','w20','w90','s20w90']
solar = pd.concat(( 
                    pd.read_csv(dir+'Solar/Modelled/lemooreCA_7kwp_s20deg.csv',index_col=0),
                    pd.read_csv(dir+'Solar/Modelled/lemooreCA_7kwp_w20deg.csv',index_col=0),
                    pd.read_csv(dir+'Solar/Modelled/lemooreCA_7kwp_w90deg.csv',index_col=0),
                    pd.read_csv(dir+'Solar/Modelled/lemooreCA_3.5kwp_s20deg_3.5kwp_w90deg.csv',index_col=0),
                   ),
                  axis=1)
solar.index = pd.date_range('1900-1-1 0:00',periods=8760,freq='1h')
solar.columns = solar_angles
net_zero_capacity = load['Load (kW)'].sum() / (solar.s20.sum()/7) # load=production / yield
solar = solar * net_zero_capacity/7 # scale to net 0
solar.describe()

# %%
# for col in solar:
#     plot_daily(solar[col],title=col,interval_min=60)

# %% [markdown]
# ## Net load

# %%
solar.index = load.index
df = pd.concat((load,solar),axis=1)
df.columns = ['load'] + ['solar_'+x for x in solar.columns]
for angle in solar.columns:
    df[f'netload_{angle}'] = df['load'] - solar[angle]

# %%
from numpy import random as rnd

def f(thresholds):
    th0,th1,th2 = thresholds
    fail,dispatch = peak_shaving_sim(   df_month,
                                    f'netload_{angle}',
                                    batt_kwh,
                                    [th0,th1,th2],
                                    TOU,
                                    utility_chg_max=batt_kwh,)                
    cost = calc_power_cost(dispatch.utility,TOU)
    return cost,fail,dispatch

def grad_f(th_i):
    #c,fail,_ = f(th_i)
    
    d = 0.05
    
    c0_0,fail,_ = f([x+dx for x,dx in zip(th_i,[-d,0,0])])
    if fail == True: c0_0,fail,_ = f(th_i)
    c0_1,fail,_ = f([x+dx for x,dx in zip(th_i,[d,0,0])])
    if fail == True: c0_1,fail,_ = f(th_i)
    
    
    c1_0,fail,_ = f([x+dx for x,dx in zip(th_i,[0,-d,0])])
    if fail == True: c1_0,fail,_ = f(th_i)
    c1_1,fail,_ = f([x+dx for x,dx in zip(th_i,[0,d,0])])
    if fail == True: c1_1,fail,_ = f(th_i)
    
    
    c2_0,fail,_ = f([x+dx for x,dx in zip(th_i,[0,0,-d])])
    if fail == True: c2_0,fail,_ = f(th_i)
    c2_1,fail,_ = f([x+dx for x,dx in zip(th_i,[0,0,d])])
    if fail == True: c2_1,fail,_ = f(th_i)

    
    return (c0_0-c0_1,c1_0-c1_1,c2_0-c2_1)

TOU = [{'price':26.07,      'hours':list(range(24)) },
       {'price': 6.81,      'hours':list(range(14,16))+list(range(21,23))},
       {'price':32.90,      'hours':list(range(16,21))}]

threshold_max = 70
grid_step = 5

tic = pd.Timestamp.now()

output_filename = 'caltech_ev_mjw3__output__'+tic.strftime('%y-%m-%d %H-%M-%S')+'.csv'
output = pd.DataFrame([],columns=['angle','batt kwh','total cost','jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'])

for angle in ['s20','w90']:#['s20','w20','w90','s20w90']:
    for batt_kwh in [200]:#[50,100,200,400,600,1000,2000]:
        print(f'\n/// Begin {angle} {batt_kwh} kwh at '+pd.Timestamp.now().strftime('%y-%m-%d %H-%M-%S'))
        best_monthly = pd.DataFrame([],columns=['month','threshold0','threshold1','threshold2','cost'])
        for month in df.index.month.unique():
            df_month = df[['load',f'solar_{angle}',f'netload_{angle}']].loc[f'1901-{month}']
            r = pd.DataFrame([], columns=['i','fail','th0','th1','th2','c','deltac','dc'])
            k = 0
            for th0 in range(0,threshold_max,grid_step):
                for th1 in range(0,threshold_max,grid_step):
                    for th2 in range(0,threshold_max,grid_step):
                        k += 1
                        fail,dispatch = peak_shaving_sim(   df_month,
                                                            f'netload_{angle}',
                                                            batt_kwh,
                                                            [th0,th1,th2],
                                                            TOU,
                                                            utility_chg_max=batt_kwh,)                
                        #if fail == False:
                        cost = calc_power_cost(dispatch.utility,TOU)
                        r.loc[len(r)] = [k,fail,th0,th1,th2,cost,pd.NA,pd.NA]
                        
            best_cost = r[r.fail==False]['c'].min()
            imin = r[r.fail==False]['c'].idxmin()
            best_th0 = r.loc[imin].th0
            best_th1 = r.loc[imin].th1
            best_th2 = r.loc[imin].th2                        
            
            print(f'{pd.Timestamp.now()} Rough grid search done month {month} thresholds=({best_th0:.1f},{best_th1:.1f},{best_th2:.1f}), cost={best_cost:.1f} ')
                        
            for th0 in range(0,10*int(1+best_th0*1.25)):
                th0 = th0/10
                for th1 in range(0,10*int(1+best_th1*1.25)):
                    th1 = th1/10
                    for th2 in range(0,10*int(1+best_th2*1.25)):
                        th2 = th2/10
                        k += 1
                        fail,dispatch = peak_shaving_sim(   df_month,
                                                            f'netload_{angle}',
                                                            batt_kwh,
                                                            [th0,th1,th2],
                                                            TOU,
                                                            utility_chg_max=batt_kwh,)                
                        #if fail == False:
                        cost = calc_power_cost(dispatch.utility,TOU)
                        r.loc[len(r)] = [k,fail,th0,th1,th2,cost,pd.NA,pd.NA]
            
            best_cost = r[r.fail==False]['c'].min()  
            imin = r[r.fail==False]['c'].idxmin()
            best_th0 = r.loc[imin].th0
            best_th1 = r.loc[imin].th1
            best_th2 = r.loc[imin].th2     
            
            #print(f'{pd.Timestamp.now()} Fine grid search done month {month} thresholds=({best_th0:.1f},{best_th1:.1f},{best_th2:.1f}) ')
            
            # LR = (0.1,0.1,0.1)
            
            # c = []
            # th = [[best_th0,best_th1,best_th2]]
            # cost,fail,dispatch = f(th[0])
            # c.append(cost)
            
            # final_countdown = 20
            # for i in range(1,500):
            #     dc = grad_f(th[i-1])
            #     dth = [(dx+nz)*lr for dx,lr,nz in zip(dc,LR,rnd.rand(3))]
            #     new_th = [max(0,x+dx) for x,dx in zip(th[i-1],dth)]
            #     th.append(new_th)
            #     cost,fail,dispatch = f(th[i])                    
            #     c.append(cost)
                
            #     r.loc[len(r)] = [i+k,
            #                      fail,
            #                      round(th[i][0],3),
            #                      round(th[i][1],3),
            #                      round(th[i][2],3),
            #                      c[i],
            #                      c[i]-c[i-1],
            #                      [round(x,3) for x in dc]]
                

            #     # stopping conditions
                
            #     if r[['deltac']][k:].dropna().rolling(100).std().iloc[-1,0] > 10:
            #         break
                
            #     # deltac = r[['deltac']].rolling(100).mean()[k:].dropna()
            #     # if len(deltac[deltac.deltac > -0.1]) >= 50:
            #     #     break
                
            #     # if abs(c[i]-c[i-1])<0.3:
            #     #     final_countdown -= 1
                    
            #     # if final_countdown == 0:
            #     #     break
            
            # # LR = (0.01,0.01,0.01)
            
            # # j = i
            # # for i in range(j,j+500):
            # #     dc = grad_f(th[i-1])
            # #     dth = [(dx+nz)*lr for dx,lr,nz in zip(dc,LR,rnd.rand(3))]
            # #     new_th = [max(0,x+dx) for x,dx in zip(th[i-1],dth)]
            # #     th.append(new_th)
            # #     cost,fail,dispatch = f(th[i])                    
            # #     c.append(cost)
                
            # #     r.loc[len(r)] = [i+k,
            # #                      fail,
            # #                      round(th[i][0],3),
            # #                      round(th[i][1],3),
            # #                      round(th[i][2],3),
            # #                      c[i],
            # #                      c[i]-c[i-1],
            # #                      [round(x,3) for x in dc]]

            if len(r)>0:
                r.index = r.i
                imin = r[r.fail==False]['c'].idxmin()
                best_monthly.loc[len(best_monthly)] = [month,
                                                       r.loc[imin].th0,
                                                       r.loc[imin].th1,
                                                       r.loc[imin].th2,
                                                       r[r.fail==False]['c'].min()]
                
            print(f'{pd.Timestamp.now()} Done month {month} thresholds=({best_th0:.1f},{best_th1:.1f},{best_th2:.1f}) cost={best_cost:.1f}')                    
        
        best_monthly.index = best_monthly.month
        best_monthly = best_monthly.drop(columns=['month'])
        
        # print('/// Best monthly')
        # print(f'Batt kwh {batt_kwh}')
        # print(f'Total cost {best_monthly.cost.sum():.1f}')
        # print(best_monthly.T,'\n\n')
        
        new_row = [angle, batt_kwh, best_monthly.cost.sum()]
        for th0,th1,th2 in zip(best_monthly.threshold0,best_monthly.threshold1,best_monthly.threshold2):
            new_row.append( (th0,th1,th2) )
        output.loc[len(output)] = new_row
        output.to_csv(output_filename)
        
# r.loc[r.fail==False,'c'] = r[r.fail==False].c
# r.loc[r.fail==True,'c (fail)'] = r[r.fail==True].c
# r[['c','c (fail)']].plot()
print('Elapsed',pd.Timestamp.now()-tic)
# %%

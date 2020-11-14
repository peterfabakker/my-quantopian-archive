from quantopian.pipeline import Pipeline
from quantopian.algorithm import attach_pipeline, pipeline_output
from quantopian.pipeline.factors import CustomFactor
from quantopian.pipeline.data.quandl import cboe_vix
from scipy  import  polyfit, polyval, signal
from pandas import DataFrame,Series
from zipline.utils.tradingcalendar import get_early_closes
from zipline.utils import tradingcalendar
from zipline.finance.execution import LimitOrder
from datetime import timedelta
from functools import partial
import scipy as sp
import scipy.stats as stats
import datetime
import pytz
import pandas as pd
import numpy as np
import re
import operator
import functools 

AdaptationWindow = 250
vxstUrl = 'https://www.quandl.com/api/v3/datasets/CBOE/VXST.csv?api_key=g1JnvyQVs7Kzdi5gLHBP'
vx1Url = 'https://www.quandl.com/api/v3/datasets/CHRIS/CBOE_VX1.csv?api_key=g1JnvyQVs7Kzdi5gLHBP'
vx2Url = 'https://www.quandl.com/api/v3/datasets/CHRIS/CBOE_VX2.csv?api_key=g1JnvyQVs7Kzdi5gLHBP'
vxvUrl = 'https://www.quandl.com/api/v3/datasets/CBOE/VXV.csv?api_key=kwAkJd42J2bgFWF-Wyda'

def initialize(context):
    # Robinhood only allows long positions, use this trading
    # guard in case
    set_long_only()
    
    # Since we are trading with Robinhood we can set this to $0!
    set_commission(commission.PerTrade(cost=0))
    
    # Define the instruments in the portfolio:
    context.sidsLongVol  = sid(38054) #VXX
    context.sidsShortVol = sid(40516) #XIV
    context.sidsShortSPY = sid(22887) #EDV
    context.sidsLongSPY  = sid(8554) #SPY
    
    context.ivts = []
    context.ivts_medianfiltered = []
    context.threshold = 1
    context.wait_trigger=False
    context.vixpipe = None

    pipe = Pipeline()
    attach_pipeline(pipe, 'vix_pipeline')  
    pipe.add(GetVol(inputs=[cboe_vix.vix_close]), 'vix')

    fetch_csv(vxstUrl,  
              symbol='VXST',  
              date_column='Date',  
              pre_func=addFields,  
              post_func=shift_data)
    
    fetch_csv(vx1Url,  
              symbol='VX1',  
              date_column='Trade Date',  
              pre_func=addFieldsVX,  
              post_func=shift_dataVX)
    
    fetch_csv(vx2Url,  
              symbol='VX2',  
              date_column='Trade Date',  
              pre_func=addFieldsVX,  
              post_func=shift_dataVX)
        
    fetch_csv(vxvUrl,  
              symbol='VXV',  
              date_column='Date',
              pre_func=addFieldsVXV,
              post_func=shift_dataVXV)


    
    
    # Rebalance every day after market open.
    schedule_function(
        ordering_logic, 
        date_rule=date_rules.every_day(), 
        time_rule=time_rules.market_open()
    )
    
def before_trading_start(context, data):
    output = pipeline_output('vix_pipeline')
    output = output.dropna()    
    context.vixpipe = output    

def ordering_logic(context, data):
    vix = context.vixpipe.loc[symbol('VXX')]['vix']
    vxst = data.current('VXST','Close')
    vx1 = data.current('VX1','Close')
    vx2 = data.current('VX2','Close')
    vxv = data.current('VXV','Close')
    
    slope9 = (vix/vxst)
    slope12 = (vx2/vx1)
    ivts = (vix/vxv)
    #ivts = (vix/vxst)
    last_ratio = vx1/vx2
    
    context.ivts.append(ivts)
    ivts_medianfiltered = sp.signal.medfilt(context.ivts,5)[-1]
    context.ivts_medianfiltered.append(ivts_medianfiltered)
    if ivts_medianfiltered == 0.0: 
        ivts_medianfiltered=1.0  
    ivts_median = ivts_medianfiltered
      
    record(slope9=slope9*100 -100)    
    record(slope12=slope12*100 -100) 
    record(vix_val=vix)

    #sometimes you need to wait to things start changing  
    if context.wait_trigger and (last_ratio > context.threshold or vix < 18):
        close_positions(context.sidsShortVol, context, data)
        close_positions(context.sidsLongSPY, context, data) 
        close_positions(context.sidsLongVol, context, data)
        rebalance(context.sidsShortSPY, context, data, 1)
        return
    else:
        context.wait_trigger = False
               
    if last_ratio < context.threshold or vix > 28:
        close_positions(context.sidsLongVol, context, data) 
        close_positions(context.sidsLongSPY, context, data) 
        close_positions(context.sidsShortSPY, context, data)        
        rebalance(context.sidsShortVol, context, data, 1)
        context.wait_trigger = True  
    elif ivts_median > (np.mean(context.ivts_medianfiltered[-22:]) +0.01):
        close_positions(context.sidsLongVol, context, data) 
        close_positions(context.sidsShortVol, context, data)
        close_positions(context.sidsLongSPY, context, data) 
        rebalance(context.sidsShortSPY, context, data, 1)  
        context.wait_trigger = False    
    elif last_ratio > context.threshold:
        close_positions(context.sidsShortVol, context, data)
        close_positions(context.sidsLongSPY, context, data) 
        close_positions(context.sidsShortSPY, context, data)
        rebalance(context.sidsLongVol, context, data, 1)
        context.wait_trigger = False            
    elif ivts_median < (np.mean(context.ivts_medianfiltered[-22:]) -0.01):
        close_positions(context.sidsLongVol, context, data) 
        close_positions(context.sidsShortVol, context, data)
        close_positions(context.sidsShortSPY, context, data)           
        rebalance(context.sidsLongSPY, context, data, 1)
        context.wait_trigger = False                 
    else:     
       close_positions(context.sidsShortVol, context, data)
       close_positions(context.sidsShortSPY, context, data)
       close_positions(context.sidsLongSPY, context, data) 
       close_positions(context.sidsLongVol, context, data)
       context.wait_trigger = False     
        
def rebalance(sid,context,data,factor): 
    # We use .95 as the cash because all market orders are converted into 
    # limit orders with a 5% buffer. So any market order placed through
    # Robinhood is submitted as a limit order with (last_traded_price * 1.05)
    valid_portfolio_value = (context.portfolio.cash * .95)
    value = (factor * valid_portfolio_value)
    
    log.info("Attempting to increase exposure in %s positions" %(sid.symbol))
    log.info("Value: $%s" %(value))
    price = data.current(sid, 'price')
    if value >= price:
        if data.can_trade(sid): 
            o_id = order_value(sid, value)   
            log.info("Ordering %s shares of %s" %
                                 (get_order(o_id).amount,
                                  sid.symbol))
    else:
        log.info("Insufficient Funds") 
            
def close_positions(sid,context,data):
    
    valid_portfolio_value = context.portfolio.cash

    for stock in context.portfolio.positions:
    # Calculate dollar amount of each position in context.assets
    # that we currently hold
        position = context.portfolio.positions[stock]
        valid_portfolio_value += position.last_sale_price * \
        position.amount
               
    
    log.info("Attempting to reduce exposure in %s positions" %(sid.symbol))
    """
    This calculates the percentage of each security that we currently
    hold in the portfolio.
    """
    if sid in context.portfolio.positions:
        position = context.portfolio.positions[sid]
        value_held = position.last_sale_price * position.amount
        percent_held = value_held/float(valid_portfolio_value)
    else:
        percent_held = 0.0

    # Calculate the percent of each security that we want to sell
    percent_to_order = 0.0 - percent_held

    # Calculate the dollar value to order for this security
    value = percent_to_order * valid_portfolio_value
    log.info("Value: $%s" %(value))

    #reduce exposure in open positions
    if value != 0.0:
        if data.can_trade(sid): 
            o_id = order_value(sid, value)   
            log.info("Selling %s shares of %s" %
                                 (get_order(o_id).amount,
                                  sid.symbol))
    else:
        log.info("No Exposure")    
                            
def handle_data(context, data): 
    record(leverage=context.account.leverage)
    record(cash=context.portfolio.cash)

class GetVol(CustomFactor):    
    window_length = 1    
    def compute(self, today, assets, out, vol):
        out[:] = vol 

def fix_close(df,closeField):  
    df = df.rename(columns={closeField:'Close'})  
    # remove spurious asterisks  
    df['Date'] = df['Date'].apply(lambda dt: re.sub('\*','',dt))  
    # convert date column to timestamps  
    df['Date'] = df['Date'].apply(lambda dt: pd.Timestamp(datetime.datetime.strptime(dt,'%Y-%m-%d')))  
    df = df.sort(columns='Date', ascending=True)  
    return df

def fix_closeVX(df,closeField):  
    df = df.rename(columns={closeField:'Close'})  
    # remove spurious asterisks  
    df['Trade Date'] = df['Trade Date'].apply(lambda dt: re.sub('\*','',dt))  
    # convert date column to timestamps  
    df['Trade Date'] = df['Trade Date'].apply(lambda dt: pd.Timestamp(datetime.datetime.strptime(dt,'%Y-%m-%d')))  
    df = df.sort(columns='Trade Date', ascending=True)  
    return df

def fix_closeVXV(df,closeField):  
    df = df.rename(columns={closeField:'Close'})  
    # remove spurious asterisks  
    #df['Date'] = df['Date'].apply(lambda dt: re.sub('\*','',dt))  
    # convert date column to timestamps  
    df['Date'] = df['Date'].apply(lambda dt: pd.Timestamp(datetime.datetime.strptime(dt,'%Y-%m-%d')))  
    df = df.sort(columns='Date', ascending=True)  
    return df

def subsequent_trading_date(date):  
    tdays = tradingcalendar.trading_days  
    last_date = pd.to_datetime(date)  
    last_dt = tradingcalendar.canonicalize_datetime(last_date)  
    next_dt = tdays[tdays.searchsorted(last_dt) + 1]  
    return next_dt

def add_last_bar(df):  
    last_date = df.index[-1]  
    subsequent_date = subsequent_trading_date(last_date)  
    blank_row = Series({}, index=df.columns, name=subsequent_date)  
    # add today, and shift all previous data up to today. This  
    # should result in the same data frames as in backtest  
    df = df.append(blank_row).shift(1).dropna(how='all')  
    return df

def shift_data(df):  
    df = add_last_bar(df)  
    df.fillna(method='ffill')  
    df['PrevCloses'] = my_rolling_apply_series(df['Close'], to_csv_str, AdaptationWindow)  
    dates = Series(df.index)  
    dates.index = df.index  
    df['PrevDates'] = my_rolling_apply_series(dates, to_csv_str, AdaptationWindow)  
    return df

def shift_dataVX(df): 
    df = add_last_bar(df)  
    df.fillna(method='ffill')  
    df = add_last_bar(df)  
    df.fillna(method='ffill')      
    df['PrevCloses'] = my_rolling_apply_series(df['Close'], to_csv_str, AdaptationWindow)  
    dates = Series(df.index)  
    dates.index = df.index  
    df['PrevDates'] = my_rolling_apply_series(dates, to_csv_str, AdaptationWindow)  
    return df

def shift_dataVXV(df):  
    df = add_last_bar(df)  
    df.fillna(method='ffill')  
    df['PrevCloses'] = my_rolling_apply_series(df['Close'], to_csv_str, AdaptationWindow)  
    dates = Series(df.index)  
    dates.index = df.index  
    df['PrevDates'] = my_rolling_apply_series(dates, to_csv_str, AdaptationWindow)  
    return df    

def unpack_from_data(data, sym):  
    v = data.current(sym, 'PrevCloses')
    i = data.current(sym, 'PrevDates')
    return from_csv_strs(i,v,True).apply(float)  

def addFields(df):  
    df = fix_close(df,'Close')  
    return df

def addFieldsVX(df):  
    df = fix_closeVX(df,'Close')  
    return df

def addFieldsVXV(df):  
    df = fix_closeVXV(df,'CLOSE')  
    return df
# convert a series of values to a comma-separated string of said values  
def to_csv_str(s):  
    return functools.reduce(lambda x,y: x+','+y, Series(s).apply(str))

# a specific instance of rolling apply, for Series of any type (not just numeric,  
# ala pandas.rolling_apply), where the index of the series is set to the indices  
# of the last elements of each subset  
def my_rolling_apply_series(s_in, f, n):  
    s_out = Series([f(s_in[i:i+n]) for i in range(0,len(s_in)-(n-1))])  
    s_out.index = s_in.index[n-1:]  
    return s_out

# reconstitutes a Series from two csv-encoded strings, one of the index, one of the values  
def from_csv_strs(x, y, idx_is_date):  
    s = Series(y.split(','),index=x.split(','))  
    if (idx_is_date):  
        s.index = s.index.map(lambda x: pd.Timestamp(x))  
    return s
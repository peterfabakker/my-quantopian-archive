def initialize(context):
    # AAPL
    context.security = sid(24)

    # rebalance 関数を毎日クローズ一分前（15：59）に実行するように指定
    schedule_function(rebalance, 
                      date_rule=date_rules.every_day(),
                      time_rule=time_rules.market_close(minutes = 1))

def rebalance(context, data):
    # 過去5日間の平均を取得して，今日の価格よりも１％大きければLong
    # 今日価格が移動平均より小さければ，ポジションクローズする

    # 過去5日間のヒストリカルデータを取得．
    # 【注意】https://www.quantopian.com/help#ide-history に説明があるとおり，
    # 日中にヒストリカルデータを複数日分取得すると，
    # 「過去4日分と今現在の価格」が取得できます．現在価格はhistorical data 同様，アジャストされた価格です．
    price_history = data.history(
        context.security,
        fields='price',
        bar_count=5,
        frequency='1d'
    )
    # price_historyを出力
    # log.info(price_history)

    # 平均値
    average_price = price_history.mean()
        
    # 現在の価格
    current_price = data.current(context.security, 'price') 
    # log.info(current_price)
    
    # 注文しようとしている銘柄が，現在上場されているか確認
    if data.can_trade(context.security):
        # 平均値より，１％大きければ，Long
        if current_price > (1.01 * average_price):
            # 成り行きで10株買う
            order_value(context.security, 1000)
            log.info("Buying %s" % (context.security.symbol))
        # 平均値より小さければ，ポジションをクローズ    
        elif current_price < average_price:
            # 0と注文することでポジションを精算することになる
            order(context.security, 0)
            log.info("Selling %s" % (context.security.symbol))
    
    # 平均値と現在価格を描画
    record(current_price=current_price, average_price=average_price)
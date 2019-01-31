# encoding: UTF-8

from __future__ import division
import shelve
from datetime import datetime
import time
from collections import OrderedDict

from vnpy.trader.vtConstant import (DIRECTION_LONG, DIRECTION_SHORT,
                                    OFFSET_OPEN, OFFSET_CLOSE, OFFSET_UNKNOWN, EXCHANGE_HUOBI, EXCHANGE_BINANCE)
from vnpy.trader.uiQt import QtWidgets
from vnpy.trader.app.algoTrading.algoTemplate import AlgoTemplate
from vnpy.trader.app.algoTrading.uiAlgoWidget import AlgoWidget, QtWidgets
from Detector import TimeSeriesAnormalyDetector
from vnpy.trader.vtObject import *
from vnpy.trader.vtTaskTimer import TaskTimer
from vnpy.trader.vtFunction import getTempPath

########################################################################
class TopIncrAlgo(AlgoTemplate):
    """TOP拉升识别，快速识别拉升套利"""
    
    templateName = u'Top拉升识别委托'

    #----------------------------------------------------------------------
    def __init__(self, engine, setting, algoName):
        """Constructor"""
        super(TopIncrAlgo, self).__init__(engine, setting, algoName)
        
        self.analyseDict = {}
        
        # 参数，强制类型转换，保证从CSV加载的配置正确
        self.quoteCurrency = str(setting['quoteCurrency']).upper()            # 基础币种
        self.monitorCurrency = str(setting['monitorCurrency']).upper()       
        self.orderFee = float(setting['orderFee'])    # 委托每个交易对买入最多数量
        self.inPer = float(setting['inPer'])/100  # 统计周期,在此周期内判断均价，用于判断增长速率，是否急剧拉升
        self.inStopPer = float(setting['inStopPer'])/100  # 委托买入条件，增长百分比
        self.outPer = float(setting['outPer'])/100  # 委托卖出条件，达到条件就卖出
        self.waitTime = int(setting['waitTime'])  # 委托买入后等待成交时间，没有成交到时间后取消订单
        
        self.quoteCurrency2 = str(setting['quoteCurrency2']).upper()            # 计价货币
        self.monitorCurrency2 = str(setting['monitorCurrency2']).upper()       
        self.orderFee2 = float(setting['orderFee2'])    # 委托每个交易对买入最多数量
        self.inPer2 = float(setting['inPer2'])/100  # 统计周期,在此周期内判断均价，用于判断增长速率，是否急剧拉升
        self.inStopPer2 = float(setting['inStopPer2'])/100  # 委托买入条件，增长百分比
        self.outPer2 = float(setting['outPer2'])/100  # 委托卖出条件，达到条件就卖出
        self.waitTime2 = int(setting['waitTime2'])  # 委托买入后等待成交时间，没有成交到时间后取消订单
        
        self.writeLog(u'算法启动...请耐心等待')
        
        huobiConnected = self.queryConnectEnabled('HUOBI')
        binanceConnected = self.queryConnectEnabled('BINANCE')
        
        if self.monitorCurrency.strip()=='':
        
            #根据条件查找要监控的合约
            contracts = self.getAllContracts()
            if not contracts:
                self.writeLog(u'查询合约失败，无法获得合约列表') 
                return
                      
            for contract in contracts:
                #计价币种相同就加入监控
                if contract.quote.upper() == self.quoteCurrency: 
                    #排除过期的火币
                    if contract.base.upper() == 'VEN' or contract.base.upper() == 'CDC': 
                        continue
                    self.addAnalyzeDict(contract, 1)
                else:
                    pass   
        else:
            array = self.monitorCurrency.split(',')
            for currency in array:
                if huobiConnected:
                    symbol = currency.lower() + self.quoteCurrency.lower()
                    vtSymbol = '.'.join([symbol, EXCHANGE_HUOBI])               
                    contract = self.getContract(vtSymbol)
                    if contract:
                        self.addAnalyzeDict(contract, 1) 
                
                if binanceConnected:
                    symbol = currency.upper() + self.quoteCurrency.upper()
                    vtSymbol = '.'.join([symbol, EXCHANGE_BINANCE])               
                    contract = self.getContract(vtSymbol)
                    if contract:
                        self.addAnalyzeDict(contract, 1) 
                
                
        #增加第二个监控币种
        if self.quoteCurrency2 !='':
            if self.monitorCurrency2.strip()=='':
            
                #根据条件查找要监控的合约
                contracts = self.getAllContracts()
                if not contracts:
                    self.writeLog(u'查询合约失败，无法获得合约列表') 
                    return
                          
                for contract in contracts:
                    if contract.quote.upper() == self.quoteCurrency2: 
                        #排除过期的火币
                        if contract.base.upper() == 'VEN' or contract.base.upper() == 'CDC': 
                            continue
                        self.addAnalyzeDict(contract, 2)
                    else:
                        pass   
            else:
                array = self.monitorCurrency2.split(',')
                for currency in array:
                    if huobiConnected:
                        symbol = currency.lower() + self.quoteCurrency2.lower()
                        vtSymbol = '.'.join([symbol, EXCHANGE_HUOBI])               
                        contract = self.getContract(vtSymbol)
                        if contract:
                            self.addAnalyzeDict(contract, 2) 
                    
                    if binanceConnected:
                        symbol = currency.upper() + self.quoteCurrency2.upper()
                        vtSymbol = '.'.join([symbol, EXCHANGE_BINANCE])               
                        contract = self.getContract(vtSymbol)
                        if contract:
                            self.addAnalyzeDict(contract, 2) 
        
        #对于币安，按照列表统一订阅，此时需要发起订阅websocket数据
        if binanceConnected:
            self.commitSubscribe('BINANCE')
        
        #算法初始化为异步，避免获取K线事件回调先于算法初始化，故延时15s后再获取K线数据;K线数据更新异步，延迟再读取文件历史交易数据避免被覆盖
        self.timer = TaskTimer()
        self.timer.join_task(self.getBasePriceInit, [], interval=15, intervalCycle=False)
        self.timer.join_task(self.readTodayData, [], interval=25, intervalCycle=False)
        self.timer.join_task(self.getBasePriceHuobi, [], timing=0.000001)
        self.timer.join_task(self.getBasePriceBinance, [], timing=8.000001)
        self.timer.start()
        self.paramEvent()
        self.varEvent()
    
    #----------------------------------------------------------------------
    def addAnalyzeDict(self, contract, flag):
        
        analyse =VtAnalyseData()
        analyse.symbol = contract.symbol
        analyse.vtSymbol = contract.vtSymbol
        analyse.exchange = contract.exchange
        analyse.priceTick = contract.priceTick
        analyse.size = contract.size
        analyse.partition = contract.partition
        
        if flag == 1:
            analyse.orderFee = self.orderFee    
            analyse.inPer = self.inPer 
            analyse.inStopPer = self.inStopPer
            analyse.outPer = self.outPer
            analyse.waitTime = self.waitTime            
        elif flag == 2:
            analyse.orderFee = self.orderFee2    
            analyse.inPer = self.inPer2 
            analyse.inStopPer = self.inStopPer2
            analyse.outPer = self.outPer2
            analyse.waitTime = self.waitTime2  
        else:
            self.writeLog(u'初始化分析对象错误')
        
        analyse.count = 0
        analyse.basePrice = 0
        analyse.increaseCount = 0
        analyse.buyAverPrice = 0.0
        analyse.lastPrice  = 0.0
        analyse.buyFee = 0.0
        analyse.positionVolume = 0.0
        analyse.lastSellPrice = 0.0
        analyse.offset = OFFSET_OPEN
        analyse.orderId = 0
        analyse.orderId2 = 0
        analyse.positionCounter = 0 
        analyse.buyTime = 0 
        analyse.buyPrice = 0
        analyse.flag = 0
        self.analyseDict[contract.vtSymbol] = analyse
        
        self.subscribe(contract.vtSymbol)  
        self.writeLog(u'%s 加入监控对象' %contract.vtSymbol)
            
    #----------------------------------------------------------------------
    def getBasePriceInit(self):
        self.writeLog(u'获取K线基本价格') 
        for key,analyse in self.analyseDict.items():
            if analyse.exchange == EXCHANGE_HUOBI:
                self.getKLineHistory(analyse.vtSymbol, '1day', 5)
            elif analyse.exchange == EXCHANGE_BINANCE:
                self.getKLineHistory(analyse.vtSymbol, '1d', 5)
                
    #----------------------------------------------------------------------
    def readTodayData(self):
        #读取今天成交情况初始化
        fielName = "analyse_" + time.strftime('%Y-%m-%d',time.localtime(time.time())) + ".vt"
        path = getTempPath(fielName)        
        f = shelve.open(path)
        if 'data' in f:
            self.writeLog(u'重启后重新读取下今天为止运行数据') 
            d = f['data']
            for key, item in d.items():
                if item.vtSymbol in self.analyseDict: 
                    self.analyseDict[item.vtSymbol].count = item.count
                    self.analyseDict[item.vtSymbol].basePrice = item.basePrice
                    self.analyseDict[item.vtSymbol].increaseCount = item.increaseCount
                    self.analyseDict[item.vtSymbol].buyAverPrice = item.buyAverPrice
                    self.analyseDict[item.vtSymbol].lastPrice  = item.lastPrice
                    self.analyseDict[item.vtSymbol].buyFee = item.buyFee
                    self.analyseDict[item.vtSymbol].positionVolume = item.positionVolume
                    self.analyseDict[item.vtSymbol].lastSellPrice  = item.lastSellPrice
                    self.analyseDict[item.vtSymbol].offset = item.offset
                    self.analyseDict[item.vtSymbol].flag = item.flag
                    self.analyseDict[item.vtSymbol].buyTime = item.buyTime
                    self.analyseDict[item.vtSymbol].buyPrice = item.buyPrice
            self.writeLog(u'读取上次买卖记录成功')
        f.close()
            
    #----------------------------------------------------------------------
    def getBasePriceHuobi(self):
        self.writeLog(u'定时任务执行,火币刷新基线交易价格') 
        for key,analyse in self.analyseDict.items():
            if analyse.exchange == EXCHANGE_HUOBI:
                self.getKLineHistory(analyse.vtSymbol, '1day', 5)
            
    #----------------------------------------------------------------------
    def getBasePriceBinance(self):
        self.writeLog(u'定时任务执行,币安刷新基线交易价格') 
        for key,analyse in self.analyseDict.items():
            if analyse.exchange == EXCHANGE_BINANCE:
                self.getKLineHistory(analyse.vtSymbol, '1d', 5)
    
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """"""
        #huobiGateway文件对订阅的深度和详细数据进行了封装
        vtSymbol = tick.vtSymbol      
        analyse = self.analyseDict[vtSymbol]
        
        if not analyse:
            return
       
        base = analyse.basePrice       
        if base == 0:
            return
        
        current = tick.lastPrice  
        
        if (current <= base):
            #decline ,add pubishment mechanisms
            analyse.increaseCount -= 1
            #增加强制平仓
            if current < analyse.buyPrice * (1 - 0.1) and analyse.positionVolume > 0 and analyse.flag != 2:
                volume = self.roundValue(analyse.positionVolume, analyse.size)
                price = current
                if volume > 0:
                    if analyse.orderId2 > 0:
                        self.cancelOrder(analyse.orderId2)
                    self.writeLog(u'合约此时增长次数:%s' %(analyse.increaseCount))
                    #analyse.orderId2 = self.sell(vtSymbol, price, volume)
                    self.writeLog(u'%s强制平仓，卖出价格:%s,卖出数量:%s,买入价格:%s' %(vtSymbol,price,volume,analyse.buyPrice))
                    
                #设置要等待卖出成交后再继续卖出，否则会导致不断卖出，超过持有量
                analyse.flag = 2  #
                
                return
       
        increase = (current - base)/base
        
        
        #开仓状态才进行买入
        if increase > analyse.inPer and increase < analyse.inStopPer:
            if current > analyse.lastPrice:      
                analyse.increaseCount += 1  
                #buy
                if analyse.increaseCount > 2 and analyse.offset == OFFSET_OPEN and analyse.flag != 1: 
                    price = min(current, tick.askPrice1)
                    #按照买入价格计算可以买入的数量
                    if  analyse.lastSellPrice > 0  and analyse.buyAverPrice > 0:
                        priceDeap = analyse.lastSellPrice - analyse.buyAverPrice
                        if price > analyse.lastSellPrice - priceDeap * 0.33:
                            return
                    
                    volume = self.roundValue((analyse.orderFee - analyse.buyFee)/price, analyse.size)
                    if volume > 0:
                        analyse.buyFee  = analyse.buyFee + volume * price #买入用了多少基本币
                        analyse.count = 0
                        analyse.orderId = self.buy(vtSymbol, price, volume)
                        analyse.buyTime = int(time.time())   #秒 时间戳
                        analyse.buyPrice = price
                        self.writeLog(u'%s合约买入委托买入,订单ID:%s,买入价格:%s,买入数量:%s' %(vtSymbol, analyse.orderId, price, volume))
                        analyse.offset = OFFSET_CLOSE
                        analyse.lastPrice = current
                        #增加到监控列表里才能监听到订单的成交信息
                        self.addSymbolsMonitor(analyse.vtSymbol)
                        return
                    else:
                        analyse.offset = OFFSET_CLOSE
                        self.writeLog(u'%s合约买入余额不足，买入价格:%s,不执行买入' %(vtSymbol,price))
            
        analyse.lastPrice = current
                
        if analyse.buyAverPrice > 0 and (current - analyse.buyAverPrice)/analyse.buyAverPrice > analyse.outPer and  analyse.offset != OFFSET_UNKNOWN:
            #sell,如果当前时间比买入不到五分钟则不卖
            if time.time() - analyse.buyTime < 300: 
                return
            volume = self.roundValue(analyse.positionVolume, analyse.size)
            price = max(current, tick.askPrice1 - analyse.priceTick)
            if volume > 0:
                self.writeLog(u'合约此时增长次数:%s' %(analyse.increaseCount))
                analyse.orderId2 = self.sell(vtSymbol, price, volume)
                self.writeLog(u'%s合约买入委托卖出，卖出价格:%s,卖出数量:%s' %(vtSymbol,price,volume))
                analyse.flag = 1  #今天不再买入
            
            #设置要等待卖出成交后再继续卖出，否则会导致不断卖出，超过持有量
            analyse.offset = OFFSET_UNKNOWN
        
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """"""
        vtSymbol = trade.vtSymbol
        analyse = self.analyseDict[vtSymbol]
        
        if not analyse:
            self.writeLog(u'%s合约没有查找到分析对象，严重错误.' %(vtSymbol))
            return
        
        if trade.direction == DIRECTION_LONG:
            analyse.buyAverPrice = (analyse.buyAverPrice * analyse.positionVolume + trade.volume * trade.price)/(analyse.positionVolume + trade.volume - trade.filledFees)
            analyse.positionVolume = analyse.positionVolume + trade.volume - trade.filledFees
            self.writeLog(u'%s合约买入成功,成交数量:%s,成交价格:%s.' %(vtSymbol, trade.volume, trade.price))
        else:
            if analyse.positionVolume == trade.volume:
                analyse.count = 0
                analyse.buyAverPrice = 0
            else:
                #对于部分卖出，持仓均价不变，BUG:计算由于四舍五入会导致均价变小
                pass
            
            analyse.lastSellPrice = trade.price  
            analyse.positionVolume = analyse.positionVolume - trade.volume
            analyse.buyFee = analyse.buyFee - (self.roundValue((trade.volume * trade.price),0.00000001) - trade.filledFees)
            self.writeLog(u'%s合约卖出成功,成交数量:%s,成交价格:%s.' %(vtSymbol, trade.volume, trade.price))
            if analyse.buyFee < 0:#卖出已经大于收入,归零
                self.writeLog(u'%s合约卖出收益%s个基本货币.' %(vtSymbol, (0-analyse.buyFee)))
                analyse.buyFee = 0
            
            #持仓比小于一定数量才继续开放买入
            if (analyse.buyAverPrice * analyse.positionVolume / analyse.orderFee < 0.05):
                analyse.increaseCount = 0
                analyse.offset = OFFSET_OPEN
     
        analyse.tradeList.append(trade.tradeID)
    
    #----------------------------------------------------------------------
    def onOrder(self, order):
        """"""
        pass
    
    #----------------------------------------------------------------------
    def onHistory(self, history):
        """""" 
        vtSymbol = history.vtSymbol
        
        analyse = self.analyseDict[vtSymbol]
        if not analyse:
            return
        
        if history.exchange == EXCHANGE_HUOBI:
            analyse.baseList = history.barList
            analyse.basePrice = history.barList[0]['open']
            analyse.lastSellPrice = 0.0
            analyse.increaseCount = 0
            analyse.flag = 0
        elif history.exchange == EXCHANGE_BINANCE:
            analyse.baseList = history.barList
            analyse.basePrice = history.barList[0][1]
            analyse.lastSellPrice = 0.0
            analyse.increaseCount = 0
            analyse.flag = 0
   
    #----------------------------------------------------------------------
    def onTimer(self):
        """"""
        for key,analyse in self.analyseDict.items():
            if analyse.positionVolume > 0:
                analyse.count += 1
                if analyse.count == analyse.waitTime:
                    #如果从文件读取了持仓量，但是orderId为0，避免这种情况错误打印增加过滤条件
                    if analyse.orderId > 0:
                        order = self.getActiveOrder(analyse.orderId)
                        if not order:
                            self.writeLog(u'错误,%s达到设置时间，未查询到订单信息:%s' %(analyse.vtSymbol,analyse.orderId))
                        else:
                            if order.direction == DIRECTION_LONG and order.tradedVolume < order.totalVolume:
                                self.writeLog(u'错误,%s达到设置时间，取消买入部分成功的订单:%s' %(analyse.vtSymbol,analyse.orderId))
                                self.cancelOrder(analyse.orderId)
                            
                        
                    #如果已经委托卖出，则不再继续卖出
                    if analyse.offset == OFFSET_UNKNOWN:
                        return
                    
                    analyse.offset = OFFSET_CLOSE
                    #超时后还有持仓,此时如果买一价比平均价高则委托卖出，最多亏损手续费
                    tick = self.getTick(analyse.vtSymbol)
                    if tick.bidPrice1 >= analyse.buyAverPrice:
                        volume = self.roundValue(analyse.positionVolume, analyse.size)
                        if volume > 0:
                            self.writeLog(u'合约此时增长次数:%s' %(analyse.increaseCount))
                            analyse.orderId2 = self.sell(analyse.vtSymbol, tick.bidPrice1, volume)
                            self.writeLog(u'%s达到设置等待时间，微量上涨，卖出价格:%s,卖出数量:%s' %(analyse.vtSymbol,tick.bidPrice1,volume))
                    else:
                        #否则就挂单，可能长期卖不出去，手续费是0.002
                        price = analyse.buyAverPrice * (1 + 0.005)
                        newPrice = self.roundValue(price, analyse.priceTick)
                        volume = self.roundValue(analyse.positionVolume, analyse.size)
                        if volume > 0:  
                            self.writeLog(u'合约此时增长次数:%s' %(analyse.increaseCount))
                            analyse.orderId2 = self.sell(analyse.vtSymbol, newPrice, volume)
                            self.writeLog(u'%s达到设置等待时间，下降，挂单卖出价格:%s,卖出数量:%s' %(analyse.vtSymbol,newPrice,volume)) 
            else:
                if analyse.orderId > 0 and (int(time.time()) - analyse.buyTime)  > analyse.waitTime:
                    self.writeLog(u'委托买入未成交，取消委托,订单号:%s,交易对象:%s' %(analyse.orderId, analyse.vtSymbol))
                    self.cancelOrder(analyse.orderId)
                    analyse.orderId = 0
                    analyse.offset == OFFSET_OPEN

    
    #----------------------------------------------------------------------
    def onStop(self):
        """"""
        if self.timer:
            self.timer.stop()
        fielName = "analyse_" + time.strftime('%Y-%m-%d',time.localtime(time.time())) + ".vt"
        path = getTempPath(fielName)
        f = shelve.open(path)
        f['data'] = self.analyseDict
        f.close()        
              
        
        self.writeLog(u'停止算法')
        self.varEvent()
        
    #----------------------------------------------------------------------
    def varEvent(self):
        """更新变量"""
        d = OrderedDict()
        d[u'算法状态'] = self.active
        self.putVarEvent(d)
    
    #----------------------------------------------------------------------
    def paramEvent(self):
        """更新参数"""
        d = OrderedDict()
        d[u'计价币种'] = self.quoteCurrency
        d[u'交易对币值'] = self.orderFee
        d[u'开始买入'] = self.inPer
        d[u'最高买入'] = self.inStopPer 
        d[u'卖出条件'] = self.outPer
        d[u'等待时间'] = self.waitTime 
        
        d[u'计价币种2'] = self.quoteCurrency2
        d[u'交易对币值2'] = self.orderFee2
        d[u'开始买入2'] = self.inPer2
        d[u'最高买入2'] = self.inStopPer2 
        d[u'卖出条件2'] = self.outPer2
        d[u'等待时间2'] = self.waitTime2
        self.putParamEvent(d)


########################################################################
class TopIncrWidget(AlgoWidget):
    """"""
    
    #----------------------------------------------------------------------
    def __init__(self, algoEngine, parent=None):
        """Constructor"""
        super(TopIncrWidget, self).__init__(algoEngine, parent)
        
        self.templateName = TopIncrAlgo.templateName
        
    #----------------------------------------------------------------------
    def initAlgoLayout(self):
        """"""
        self.lineSymbol = QtWidgets.QLineEdit()
        
        self.orderFee = QtWidgets.QDoubleSpinBox()
        self.orderFee.setMaximum(1000)
        self.orderFee.setDecimals(8)
        
        self.quoteCurrency = QtWidgets.QLineEdit()
        self.monitorCurrency = QtWidgets.QLineEdit()
        
        self.inPer = QtWidgets.QDoubleSpinBox()
        self.inPer.setMinimum(0)
        self.inPer.setMaximum(100)
        self.inPer.setDecimals(1) 
        
        self.inStopPer = QtWidgets.QDoubleSpinBox()
        self.inStopPer.setMinimum(0)
        self.inStopPer.setMaximum(100)
        self.inStopPer.setDecimals(1)         
        
        self.outPer = QtWidgets.QDoubleSpinBox()
        self.outPer.setMinimum(0)
        self.outPer.setMaximum(100)
        self.outPer.setDecimals(1)  
        
        self.waitTime = QtWidgets.QSpinBox()
        self.waitTime.setMinimum(1)
        self.waitTime.setMaximum(36000)  
        self.waitTime.setValue(600)
        
        self.orderFee2 = QtWidgets.QDoubleSpinBox()
        self.orderFee2.setMaximum(1000)
        self.orderFee2.setDecimals(8)
        
        self.quoteCurrency2 = QtWidgets.QLineEdit()
        self.monitorCurrency2 = QtWidgets.QLineEdit()
        
        self.inPer2 = QtWidgets.QDoubleSpinBox()
        self.inPer2.setMinimum(0)
        self.inPer2.setMaximum(100)
        self.inPer2.setDecimals(1) 
        
        self.inStopPer2 = QtWidgets.QDoubleSpinBox()
        self.inStopPer2.setMinimum(0)
        self.inStopPer2.setMaximum(100)
        self.inStopPer2.setDecimals(1)         
        
        self.outPer2 = QtWidgets.QDoubleSpinBox()
        self.outPer2.setMinimum(0)
        self.outPer2.setMaximum(100)
        self.outPer2.setDecimals(1)  
        
        self.waitTime2 = QtWidgets.QSpinBox()
        self.waitTime2.setMinimum(1)
        self.waitTime2.setMaximum(36000)  
        self.waitTime2.setValue(600)        
  
        Label = QtWidgets.QLabel
        
        grid = QtWidgets.QGridLayout()
        grid.addWidget(Label(u'计价币种'), 0, 0)
        grid.addWidget(self.quoteCurrency, 0, 1)
        grid.addWidget(Label(u'监控币种(可选)'), 1, 0)
        grid.addWidget(self.monitorCurrency, 1, 1)
        grid.addWidget(Label(u'交易对币值'), 2, 0)
        grid.addWidget(self.orderFee, 2, 1)    
        grid.addWidget(Label(u'开始买入(%)'), 3, 0)
        grid.addWidget(self.inPer, 3, 1)
        grid.addWidget(Label(u'最高买入(%)'), 4, 0)
        grid.addWidget(self.inStopPer, 4, 1)
        grid.addWidget(Label(u'卖出条件(%)'), 5, 0)
        grid.addWidget(self.outPer, 5, 1)
        grid.addWidget(Label(u'观察时间(秒)'), 6, 0)
        grid.addWidget(self.waitTime, 6, 1)
        
        grid.addWidget(Label(u'计价币种2'), 7, 0)
        grid.addWidget(self.quoteCurrency2, 7, 1)
        grid.addWidget(Label(u'监控币种2(可选)'), 8, 0)
        grid.addWidget(self.monitorCurrency2, 8, 1)
        grid.addWidget(Label(u'交易对币值2'), 9, 0)
        grid.addWidget(self.orderFee2, 9, 1)    
        grid.addWidget(Label(u'开始买入2(%)'), 10, 0)
        grid.addWidget(self.inPer2, 10, 1)
        grid.addWidget(Label(u'最高买入2(%)'), 11, 0)
        grid.addWidget(self.inStopPer2, 11, 1)
        grid.addWidget(Label(u'卖出条件2(%)'), 12, 0)
        grid.addWidget(self.outPer2, 12, 1)
        grid.addWidget(Label(u'观察时间2(秒)'), 13, 0)
        grid.addWidget(self.waitTime2, 13, 1)
        
        
        return grid
    
    #----------------------------------------------------------------------
    def getAlgoSetting(self):
        """"""
        setting = OrderedDict()
        setting['templateName'] = TopIncrAlgo.templateName
        setting['quoteCurrency'] = str(self.quoteCurrency.text())
        setting['monitorCurrency'] = str(self.monitorCurrency.text())
        setting['orderFee'] = float(self.orderFee.value())
        setting['inPer'] = float(self.inPer.text())
        setting['inStopPer'] = float(self.inStopPer.text())
        setting['outPer'] = float(self.outPer.text())
        setting['waitTime'] = int(self.waitTime.text())
        
        setting['quoteCurrency2'] = str(self.quoteCurrency2.text())
        setting['monitorCurrency2'] = str(self.monitorCurrency2.text())
        setting['orderFee2'] = float(self.orderFee2.value())
        setting['inPer2'] = float(self.inPer2.text())
        setting['inStopPer2'] = float(self.inStopPer2.text())
        setting['outPer2'] = float(self.outPer2.text())
        setting['waitTime2'] = int(self.waitTime2.text())        
        
        return setting
    
    
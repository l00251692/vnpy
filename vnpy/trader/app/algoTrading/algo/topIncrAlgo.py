# encoding: UTF-8

from __future__ import division
from collections import OrderedDict

from datetime import datetime, timedelta
from vnpy.trader.vtConstant import (DIRECTION_LONG, DIRECTION_SHORT,
                                    OFFSET_OPEN, OFFSET_CLOSE)
from vnpy.trader.uiQt import QtWidgets
from vnpy.trader.app.algoTrading.algoTemplate import AlgoTemplate
from vnpy.trader.app.algoTrading.uiAlgoWidget import AlgoWidget, QtWidgets
from Detector import TimeSeriesAnormalyDetector
from vnpy.trader.vtObject import *
from vnpy.trader.vtTaskTimer import TaskTimer

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
        
        self.writeLog(u'算法启动...请耐心等待')
        
        if self.monitorCurrency.strip()=='':
        
            #根据条件查找要监控的合约
            contracts = self.getAllContracts()
            if not contracts:
                self.writeLog(u'%s查询合约失败，无法获得合约列表' %(algo.algoName)) 
                return
                      
            for tmp in contracts:
                baseCurrency,quoteCurrency = tmp.name.split('/')
                #计价币种相同就加入监控
                if quoteCurrency == self.quoteCurrency: 
                    #排除过期的火币
                    if baseCurrency == 'VEN' or baseCurrency == 'CDC': 
                        continue
                    analyse =VtAnalyseData()
                    analyse.symbol = tmp.symbol
                    analyse.vtSymbol = tmp.vtSymbol
                    analyse.exchange = tmp.exchange
                    analyse.priceTick = tmp.priceTick
                    analyse.size = tmp.size
                    analyse.partition = tmp.partition
                    analyse.count = 0
                    analyse.basePrice = 0
                    analyse.increaseCount = 0
                    analyse.buyAverPrice = 0.0
                    analyse.lastPrice  = 0.0
                    analyse.buyVolume = 0.0
                    analyse.positionVolume = 0.0
                    analyse.offset = OFFSET_OPEN
                    self.analyseDict[tmp.vtSymbol] = analyse
                    self.getKLineHistory(tmp.vtSymbol, '1day', 5)
                    #detector = TimeSeriesAnormalyDetector(0.2, 0.5, 0.6, 0.5, 0.5, 5)
                    #self.analyseDict[tmp.vtSymbol] = detector
                    self.subscribe(tmp.vtSymbol)
                else:
                    pass   
        else:
            array = self.monitorCurrency.split(',')
            for currency in array:
                symbol = currency.lower() + self.quoteCurrency.lower()
                vtSymbol = '.'.join([symbol, 'HUOBI'])               
                contract = self.getContract(vtSymbol)
                if not contract:
                    self.writeLog(u'%s合约查找失败，无法卖出' %vtSymbol)
                    continue
                analyse =VtAnalyseData()
                analyse.symbol = contract.symbol
                analyse.vtSymbol = contract.vtSymbol
                analyse.exchange = contract.exchange
                analyse.priceTick = contract.priceTick
                analyse.size = contract.size
                analyse.partition = contract.partition
                analyse.count = 0
                analyse.basePrice = 0
                analyse.increaseCount = 0
                analyse.buyAverPrice = 0.0
                analyse.lastPrice  = 0.0
                analyse.buyFee = 0.0
                analyse.positionVolume = 0.0
                analyse.offset = OFFSET_OPEN
                self.analyseDict[contract.vtSymbol] = analyse
                self.getKLineHistory(contract.vtSymbol, '1day', 5)
                self.writeLog(u'%s合约进行监控' %vtSymbol)
                self.subscribe(contract.vtSymbol)
                   
        self.timer = TaskTimer()
        self.timer.join_task(self.taskTimer, [], timing=0)
        self.timer.start()
        self.paramEvent()
        self.varEvent()
    
    #----------------------------------------------------------------------
    def taskTimer(self):
        self.writeLog(u'定时任务执行,获取最新的交易价格') 
        for key,analyse in self.analyseDict.items():
            self.getKLineHistory(analyse.vtSymbol, '1day', 5) 
    
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
            return
       
        increase = (current - base)/base
        
        
        #开仓状态才进行买入
        if increase > self.inPer and increase < self.inStopPer:
            if current > analyse.lastPrice:      
                analyse.increaseCount += 1  
                #buy
                if analyse.increaseCount > 2 and analyse.offset == OFFSET_OPEN: 
                    price = min(current, tick.askPrice1)
                    #按照买入价格计算可以买入的数量
                    volume = self.roundValue((self.orderFee - analyse.buyFee)/price, analyse.size)
                    if count > 0:
                        analyse.buyFee  = analyse.buyFee + volume * price #买入用了多少基本币
                        #self.buy(vtSymbol, price, count)
                        self.writeLog(u'%s合约买入委托买入，买入价格:%s,买入数量:%s' %(vtSymbol,price,volume))
                        analyse.offset == OFFSET_CLOSE
                        analyse.lastPrice = current
                        #增加到监控列表里才能监听到订单的成交信息
                        self.addSymbolsMonitor('HUOBI',analyse.symbol)
                        return
                    else:
                        self.writeLog(u'%s合约买入余额不足，买入价格:%s,不执行买入' %(vtSymbol,price))
            else:
                analyse.increaseCount -= 1
            
        analyse.lastPrice = current
                
        if analyse.buyAverPrice > 0 and (current - analyse.buyAverPrice)/analyse.buyAverPrice > self.outPer:
            #sell
            volume = self.roundValue(analyse.positionVolume, analyse.size)
            price = max(current, tick.askPrice1 - analyse.priceTick)
            if volume > 0:
                self.writeLog(u'%s合约此时增长次数:%s' %(analyse.increaseCount))
                self.sell(vtSymbol, price, volume)
                self.writeLog(u'%s合约买入委托卖出，卖出价格:%s,卖出数量:%s' %(vtSymbol,price,volume))
        
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
        else:
            if analyse.positionVolume == trade.volume:
                analyse.count = 0
                analyse.buyAverPrice = 0
            else:
                analyse.buyAverPrice = (analyse.buyAverPrice * analyse.positionVolume - trade.volume * trade.price)/(analyse.positionVolume - trade.volume) 
                
            analyse.positionVolume = analyse.positionVolume - trade.volume
            analyse.buyFee = analyse.buyFee - (self.roundValue((trade.volume * trade.price),0.00000001) - trade.filledFees)
            
            if analyse.buyFee < 0:#卖出已经大于收入,归零
                self.writeLog(u'%s合约卖出收益%s个基本货币.' %(vtSymbol, (0-analyse.buyFee)))
                analyse.buyFee = 0
            
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
        symbol = history.symbol
        vtSymbol = history.vtSymbol
        
        analyse = self.analyseDict[vtSymbol]
        if not analyse:
            return
        
        analyse.baseList = history.barList
        analyse.basePrice = history.barList[0]['open']
    #----------------------------------------------------------------------
    def onTimer(self):
        """"""
        for key,analyse in self.analyseDict.items():
            if analyse.positionVolume > 0:
                analyse.count += 1
                if analyse.count == self.waitTime:
                    analyse.offset = OFFSET_CLOSE
                    #超时后还有持仓,此时如果买一价比平均价高则委托卖出，最多亏损手续费
                    tick = self.getTick(analyse.vtSymbol)
                    if tick.bidPrice1 >= analyse.buyAverPrice:
                        volume = self.roundValue(analyse.positionVolume, analyse.size)
                        if volume > 0:
                            self.writeLog(u'%s合约此时增长次数:%s' %(analyse.increaseCount))
                            self.sell(analyse.vtSymbol, tick.bidPrice1, volume)
                            self.writeLog(u'%s达到设置等待时间，微量上涨，卖出价格:%s,卖出数量:%s' %(analyse.vtSymbol,tick.bidPrice1,volume))
                    else:
                        #否则就挂单，可能长期卖不出去
                        price = analyse.buyAverPrice * (1 + 0.005)
                        newPrice = self.roundValue(price, analyse.priceTick)
                        volume = self.roundValue(analyse.positionVolume, analyse.size)
                        if volume > 0:  
                            self.writeLog(u'%s合约此时增长次数:%s' %(analyse.increaseCount))
                            self.sell(analyse.vtSymbol, newPrice, volume)
                            self.writeLog(u'%s达到设置等待时间，下降，挂单卖出价格:%s,卖出数量:%s' %(analyse.vtSymbol,newPrice,volume)) 
            else:
                pass

    
    #----------------------------------------------------------------------
    def onStop(self):
        """"""
        if self.timer:
            self.timer.stop()
        
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
        
        self.spinVolume = QtWidgets.QDoubleSpinBox()
        self.spinVolume.setMinimum(0.1)
        self.spinVolume.setMaximum(1000000000)
        self.spinVolume.setDecimals(1)
        
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
        self.waitTime.setMaximum(3600)  
        self.waitTime.setValue(600)
  
        Label = QtWidgets.QLabel
        
        grid = QtWidgets.QGridLayout()
        #grid.addWidget(Label(u'代码'), 0, 0)
        #grid.addWidget(self.lineSymbol, 0, 1)
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
        
        return setting
    
    
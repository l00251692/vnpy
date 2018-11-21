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
        self.orderVolume = float(setting['orderVolume'])    # 委托数量
        self.inPer = float(setting['inPer'])/100  # 统计周期,在此周期内判断均价，用于判断增长速率，是否急剧拉升
        self.inStopPer = float(setting['inStopPer'])/100  # 委托买入条件，增长百分比
        self.outPer = float(setting['outPer'])/100  # 委托卖出条件，达到条件就卖出
        self.waitTime = int(setting['waitTime'])  # 委托买入后等待成交时间，没有成交到时间后取消订单
        
        #根据条件查找要监控的合约
        contracts = self.getAllContracts()
        if not contracts:
            self.writeLog(u'%s查询合约失败，无法获得合约列表' %(algo.algoName)) 
            return
        
        
        for tmp in contracts:
            baseCurrency,quoteCurrency = tmp.name.split('/')
            #计价币种相同就加入监控
            if quoteCurrency == self.quoteCurrency: 
                analyse =VtAnalyseData()
                analyse.symbol = tmp.symbol
                analyse.vtSymbol = tmp.vtSymbol
                analyse.exchange = tmp.exchange
                analyse.priceTick = tmp.priceTick
                analyse.size = tmp.size
                analyse.count = 0
                analyse.increaseCount = 0
                analyse.buyAverPrice = 0.0
                analyse.lastPrice  = 0.0
                analyse.buyVolume = 0.0
                analyse.orderVolume = 0.0
                analyse.positionVolume = 0.0
                analyse.offset = OFFSET_OPEN
                self.analyseDict[tmp.vtSymbol] = analyse
                self.getKLineHistory(tmp.vtSymbol, '1day', 5)
                #detector = TimeSeriesAnormalyDetector(0.2, 0.5, 0.6, 0.5, 0.5, 5)
                #self.analyseDict[tmp.vtSymbol] = detector
                self.subscribe(tmp.vtSymbol)
            else:
                pass   
        timer = TaskTimer()
        timer.join_task(taskTimer, [], timing=0)
        timer.start()
        self.paramEvent()
        self.varEvent()
    
    #----------------------------------------------------------------------
    def taskTimer(self):
        self.writeLog(u'定时任务执行,获取最新的交易价格%s') 
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
        
        current = tick.lastPrice
        base = analyse.basePrice
        
        if base == 0:
            return
            
        if (current <= base):
            #decline ,add pubishment mechanisms
            if analyse.positionVolume > 0:
                analyse.increaseCount -= 1
            else:
                analyse.increaseCount -= 1
                if analyse.increaseCount == -10:
                    #持续下跌今天就不再监控，此时为了减少CPU压力
                    self.unsubscribe(vtSymbol)
            return
       
        increase = (current - base)/base
        
        #开仓状态才进行买入
        if increase > self.inPer and increase < self.inStopPer:
            #buy
            print('onTick:%s,current=%s,pre=%s' %(vtSymbol,current,analyse.lastPrice))
            if current > analyse.lastPrice:
                analyse.increaseCount += 1
                
                #注意:初始化analyse.lastPrice为零，第一次肯定满足
                if analyse.increaseCount > 2 and analyse.offset == OFFSET_OPEN:
                    orderVolume = self.orderVolume - analyse.orderVolume
                    if orderVolume > 0:
                        if orderVolume < analyse.size:
                            self.writeLog(u'%s合约买入数量%s，小于合约最小买入数量%s,暂不买入' %(vtSymbol,orderVolume,analyse.size))
                        else:
                            analyse.orderVolume  = analyse.orderVolume + orderVolume
                            #测试注掉实际买入改为虚拟买入，在这里设置持仓，实际因该在订单成交是设置
                            self.buy(vtSymbol, current, orderVolume)
                            self.writeLog(u'%s合约买入委托买入，买入价格:%s,买入数量:%s' %(vtSymbol,current,orderVolume))
            
        analyse.lastPrice = current
                
        if (current - analyse.buyAverPrice)/base >self.outPer:
            #sell
            orderVolume = analyse.positionVolume
            if orderVolume > 0:
                self.sell(vtSymbol, current, orderVolume)
                self.writeLog(u'%s合约买入委托卖出，卖出价格:%s,卖出数量:%s' %(vtSymbol,current,orderVolume))
        
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """deal callback"""
        vtSymbol = trade.vtSymbol
        analyse = self.analyseDict[vtSymbol]
        
        if not analyse:
            self.writeLog(u'%s合约没有查找到分析对象，严重错误.' %(vtSymbol))
            return
        
        if trade.direction == DIRECTION_LONG:
            analyse.buyAverPrice = (analyse.buyAverPrice * analyse.buyVolume + trade.volume * trade.price)/(analyse.buyVolume + trade.volume)
            analyse.buyVolume = analyse.buyVolume + trade.volume
            analyse.positionVolume = analyse.positionVolume + trade.volume
        else:
            analyse.positionVolume = analyse.positionVolume - trade.volume
            if analyse.positionVolume == 0:
                #全部卖出，清空记录，重新监控上涨
                analyse.buyAverPrice = 0.0
                analyse.buyVolume = 0.0
                analyse.orderVolume = 0.0
                analyse.increaseCount = 0
                analyse.count = 0
                analyse.offset = OFFSET_OPEN
             
        analyse.tradeList.append(trade.tradeID)
        
        self.varEvent()
    
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
                        price = tick.bidPrice1 + analyse.priceTick
                        self.sell(analyse.vtSymbol, price, analyse.positionVolume)
                        self.writeLog(u'%s达到设置等待时间，上涨，卖出价格:%s,卖出数量:%s' %(analyse.vtSymbol,price,analyse.positionVolume))
                    else:
                        #否则就挂单，可能长期卖不出去
                        price = analyse.buyAverPrice * (1 + 0.02)
                        self.sell(analyse.vtSymbol, price, analyse.positionVolume)
                        self.writeLog(u'%s达到设置等待时间，下降，卖出价格:%s,卖出数量:%s' %(analyse.vtSymbol,price,analyse.positionVolume))
                    
            else:
                pass
    
        self.varEvent()
    
    #----------------------------------------------------------------------
    def onStop(self):
        """"""
        self.writeLog(u'停止算法')
        self.varEvent()
        
    #----------------------------------------------------------------------
    def varEvent(self):
        """更新变量"""
        d = OrderedDict()
        d[u'算法状态'] = self.active
        d['active'] = self.active
        self.putVarEvent(d)
    
    #----------------------------------------------------------------------
    def paramEvent(self):
        """更新参数"""
        d = OrderedDict()
        d[u'计价币种'] = self.quoteCurrency
        d[u'委托数量'] = self.orderVolume
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
        self.spinVolume.setMinimum(0)
        self.spinVolume.setMaximum(1000000000)
        self.spinVolume.setDecimals(6)
        
        self.quoteCurrency = QtWidgets.QLineEdit()
        
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
        grid.addWidget(Label(u'委托数量'), 1, 0)
        grid.addWidget(self.spinVolume, 1, 1)    
        grid.addWidget(Label(u'开始买入(%)'), 2, 0)
        grid.addWidget(self.inPer, 2, 1)
        grid.addWidget(Label(u'最高买入(%)'), 3, 0)
        grid.addWidget(self.inStopPer, 3, 1)
        grid.addWidget(Label(u'卖出条件(%)'), 4, 0)
        grid.addWidget(self.outPer, 4, 1)
        grid.addWidget(Label(u'观察时间(秒)'), 5, 0)
        grid.addWidget(self.waitTime, 5, 1)
        
        return grid
    
    #----------------------------------------------------------------------
    def getAlgoSetting(self):
        """"""
        setting = OrderedDict()
        setting['templateName'] = TopIncrAlgo.templateName
        setting['quoteCurrency'] = str(self.quoteCurrency.text())
        setting['orderVolume'] = float(self.spinVolume.value())
        setting['inPer'] = float(self.inPer.text())
        setting['inStopPer'] = float(self.inStopPer.text())
        setting['outPer'] = float(self.outPer.text())
        setting['waitTime'] = int(self.waitTime.text())
        
        return setting
    
    
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



########################################################################
class TopIncrAlgo(AlgoTemplate):
    """TOP拉升识别，快速识别拉升套利"""
    
    templateName = u'Top拉升识别委托'

    #----------------------------------------------------------------------
    def __init__(self, engine, setting, algoName):
        """Constructor"""
        super(TopIncrAlgo, self).__init__(engine, setting, algoName)
        
        self.contractList = {}
        self.analyseList = {}
        
        # 参数，强制类型转换，保证从CSV加载的配置正确
        self.quoteCurrency = str(setting['quoteCurrency']).upper()            # 基础币种
        self.orderVolume = float(setting['orderVolume'])    # 委托数量
        self.minPeriod = int(setting['minPeriod'])  # 统计周期,在此周期内判断均价，用于判断增长速率，是否急剧拉升
        self.inPercent = float(setting['inPercent'])  # 委托买入条件，增长百分比
        self.outPercent = float(setting['outPercent'])  # 委托卖出条件，达到条件就卖出
        self.waitTime = int(setting['waitTime'])  # 委托买入后等待成交时间，没有成交到时间后取消订单
        
        self.count = 0              # 定时计数
        self.tradedVolume = 0       # 总成交数量
        
        #根据条件查找要监控的合约
        contracts = self.getAllContracts()
        if not contracts:
            self.writeLog(u'%s查询合约失败，无法获得合约列表' %(algo.algoName)) 
            return

        for tmp in contracts:
            baseCurrency,quoteCurrency = tmp.name.split('/')
            #计价币种相同就加入监控
            if quoteCurrency == self.quoteCurrency:  
                self.getKLineHistory(tmp.vtSymbol, '1day', 5)
                detector = TimeSeriesAnormalyDetector(0.2, 0.5, 0.6, 0.5, 0.5, 5)
                self.analyseList[tmp.vtSymbol] = detector
                self.subscribe(tmp.vtSymbol)
                self.count += 1
            else:
                pass  
        self.writeLog(u'%s个合约进行了订阅' %(self.count))  
        self.paramEvent()
        self.varEvent()
    
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """"""
        #huobiGateway文件对订阅的深度和详细数据进行了封装
        vtSymbol = tick.vtSymbol      
        detector = self.analyseList[vtSymbol]
        
        if not detector:
            return
        preData = detector.preData()
        if not preData:
            preData = [0]
            
        data = [tick.bidPrice1, tick.bidPrice2, tick.askPrice1, tick.askPrice2, tick.lastPrice] 
        score = detector.detect(data)
        topN, total = detector.anormal_rank()
        
        if (topN <3 and total > 10  and tick.lastPrice > preData[4]):
            #迅速拉升
            self.writeLog(u'%s合约执行买入，买入价格为:%s' %(vtSymbol,tick.lastPrice))
            pass
        
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """"""
        self.tradedVolume += trade.volume
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
        
        print ('TopIncrAlgo onHistory: %s'%(vtSymbol))
        
        for d in history.barList:
            time = datetime.fromtimestamp(d['id']/1000)
            topen = d['open']
            print("%s getKlineHistory, time=%s,open=%s" %(symbol, time, topen))
            
    #----------------------------------------------------------------------
    def onTimer(self):
        """"""
        return
        self.count += 1
        if self.count == self.interval:
            self.count = 0
            
            # 全撤委托
            self.cancelAll()
            
            # 获取行情
            tick = self.getTick(self.vtSymbol)
            if not tick:
                return
            
            contract = self.getContract(self.vtSymbol)
            if not contract:
                return
            
            tickSpread = (tick.askPrice1 - tick.bidPrice1) / contract.priceTick
            if tickSpread < self.minTickSpread:
                self.writeLog(u'当前价差为%s个Tick，小于算法设置%s，不执行刷单' %(tickSpread, self.minTickSpread))
                return
            
            midPrice = tick.bidPrice1 + contract.priceTick * int(tickSpread/2)
            
            self.buy(self.vtSymbol, midPrice, self.orderVolume)
            self.sell(self.vtSymbol, midPrice, self.orderVolume)
            
            self.writeLog(u'发出刷单买卖委托，价格：%s，数量：%s' %(midPrice, self.orderVolume))
        
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
        d[u'成交数量'] = self.tradedVolume
        d[u'定时计数'] = self.count
        d['active'] = self.active
        self.putVarEvent(d)
    
    #----------------------------------------------------------------------
    def paramEvent(self):
        """更新参数"""
        d = OrderedDict()
        d[u'计价币种'] = self.quoteCurrency
        d[u'委托数量'] = self.orderVolume
        d[u'统计周期'] = self.minPeriod
        d[u'买入条件'] = self.inPercent 
        d[u'卖出条件'] = self.outPercent
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
        
        self.minPeriod = QtWidgets.QSpinBox()
        self.minPeriod.setMinimum(1)
        self.minPeriod.setMaximum(30)  
        self.minPeriod.setValue(5)
        
        self.inPercent = QtWidgets.QDoubleSpinBox()
        self.inPercent.setMinimum(0)
        self.inPercent.setMaximum(100)
        self.inPercent.setDecimals(1)  
        
        self.outPercent = QtWidgets.QDoubleSpinBox()
        self.outPercent.setMinimum(0)
        self.outPercent.setMaximum(100)
        self.outPercent.setDecimals(1)  
        
        self.waitTime = QtWidgets.QSpinBox()
        self.waitTime.setMinimum(1)
        self.waitTime.setMaximum(30)  
        self.waitTime.setValue(5)        
  
        Label = QtWidgets.QLabel
        
        grid = QtWidgets.QGridLayout()
        #grid.addWidget(Label(u'代码'), 0, 0)
        #grid.addWidget(self.lineSymbol, 0, 1)
        grid.addWidget(Label(u'计价币种'), 0, 0)
        grid.addWidget(self.quoteCurrency, 0, 1)
        grid.addWidget(Label(u'委托数量'), 1, 0)
        grid.addWidget(self.spinVolume, 1, 1)    
        grid.addWidget(Label(u'统计周期(分钟)'), 2, 0)
        grid.addWidget(self.minPeriod, 2, 1)
        grid.addWidget(Label(u'买入条件(%)'), 3, 0)
        grid.addWidget(self.inPercent, 3, 1)
        grid.addWidget(Label(u'卖出条件(%)'), 4, 0)
        grid.addWidget(self.outPercent, 4, 1)
        grid.addWidget(Label(u'等待时间max(分钟)'), 5, 0)
        grid.addWidget(self.waitTime, 5, 1)
        

        
        return grid
    
    #----------------------------------------------------------------------
    def getAlgoSetting(self):
        """"""
        setting = OrderedDict()
        setting['templateName'] = TopIncrAlgo.templateName
        #setting['vtSymbol'] = str(self.lineSymbol.text())
        setting['quoteCurrency'] = str(self.quoteCurrency.text())
        setting['orderVolume'] = float(self.spinVolume.value())
        setting['minPeriod'] = int(self.minPeriod.text())
        setting['inPercent'] = float(self.inPercent.text())
        setting['outPercent'] = float(self.outPercent.text())
        setting['waitTime'] = int(self.waitTime.text())
        
        return setting
    
    
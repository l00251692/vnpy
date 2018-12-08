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
class AutoTradeAlgo(AlgoTemplate):
    """TOP拉升识别，快速识别拉升套利"""
    
    templateName = u'Auto监控自动卖出'

    #----------------------------------------------------------------------
    def __init__(self, engine, setting, algoName):
        """Constructor"""
        super(AutoTradeAlgo, self).__init__(engine, setting, algoName)
        
        self.analyseDict = {}
        
        # 参数，强制类型转换，保证从CSV加载的配置正确
        self.quoteCurrency = str(setting['quoteCurrency']).lower()            # 基础币种
        self.outPer = float(setting['outPer'])/100  # 委托卖出条件，达到条件就卖出
        
        self.writeLog(u'算法启动...请耐心等待')
        result, data = self.qryPositionSync('HUOBI')
      
        if result:
            if data['status'] == 'ok':       
                for d in data['data']['list']:
                    if float(d['balance']) <= 0.0:
                        continue                    
                    analyse = VtAnalyse2Data()
                    analyse.currency = d['currency'].lower()
                    analyse.exchange = 'HUOBI'
                    analyse.vtCurrency = '.'.join([analyse.currency, analyse.exchange])  
                    analyse.symbol = analyse.currency + self.quoteCurrency
                    analyse.vtSymbol = '.'.join([analyse.symbol, analyse.exchange])                    
                    analyse.buyAverPrice = 0.0 
                    analyse.minSellPrice = 0.0
                    analyse.positionVolume = 0.0 
                    analyse.calculateVolume = 0.0
                    analyse.positionVolume += float(d['balance'])
                    analyse.available = analyse.positionVolume
                    if d['type'] == 'frozen':
                        analyse.available = analyse.positionVolume - float(d['balance']) 
                    self.analyseDict[analyse.vtSymbol] = analyse
            else:
                msg = u'错误代码：%s，错误信息：%s' %(data['err-code'], data['err-msg'])
                self.writeLog(u'获取当前账户资产信息失败,请处理:%s' %msg)
                return
        else:
            self.writeLog(u'获取当前账户资产信息失败，请检查处理.')
            return
        
        for key,analyse in self.analyseDict.items():
            #查看成交记录,持有的稳定币本身不监控
            if analyse.currency == self.quoteCurrency:
                continue;
            
            result, data = self.qryTradeSync(analyse.symbol, 'HUOBI')
            if result:
                if data['status'] == 'ok':  
                    data['data'].reverse()         
                    for d in data['data']:
                        tradeID = d['match-id']
                        price = float(d['price'])
                        volume = float(d['filled-amount']) 
                        fees = float(d['filled-fees'])                       
                        
                        if 'buy' in d['type']:
                            if analyse.calculateVolume + (volume -fees) > analyse.available:
                                analyse.minSellPrice = analyse.buyAverPrice * (1 + self.outPer)
                                self.subscribe(analyse.vtSymbol)
                                break;
                            elif analyse.calculateVolume + (volume -fees) == analyse.available:
                                analyse.calculateVolume += (volume - fees)
                                analyse.buyAverPrice = (analyse.buyAverPrice + price * volume)/analyse.calculateVolume                                
                                analyse.minSellPrice = analyse.buyAverPrice * (1 + self.outPer)
                                self.subscribe(analyse.vtSymbol)
                                break;
                            
                            analyse.calculateVolume += (volume - fees)
                            analyse.buyAverPrice = (analyse.buyAverPrice + price * volume)/analyse.calculateVolume
                        else: 
                            if analyse.calculateVolume > volume:
                                analyse.buyAverPrice = (analyse.buyAverPrice * analyse.calculateVolume - price * volume)/(analyse.calculateVolume -volume)
                            analyse.calculateVolume -= volume    
                else:
                    #msg = u'错误代码：%s，错误信息：%s' %(data['err-code'], data['err-msg'])
                    #self.writeLog(u'查找%s交易对的成交订单失败,忽略此交易对:%s' %(analyse.symbol, msg))
                    continue
            else:
                continue
   
        self.paramEvent()
        self.varEvent()
    
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """"""
        #huobiGateway文件对订阅的深度和详细数据进行了封装
        vtSymbol = tick.vtSymbol      
        analyse = self.analyseDict[vtSymbol]
        
        if not analyse:
            return
        
        if analyse.minSellPrice == 0 or analyse.available <= 0:
            return
        
        current = tick.lastPrice
        
        if current > analyse.minSellPrice:
            contract = self.getContract(analyse.vtSymbol)
            if not contract:
                self.writeLog(u'%s合约查找失败，无法卖出' %analyse.vtSymbol)
            orderVolume = self.roundValue(analyse.positionVolume, contract.size)
            if orderVolume > 0:
                #挂单卖一
                price = max(current, tick.bidPrice1)
                self.sell(analyse.vtSymbol, price, orderVolume)
                self.writeLog(u'%s合约买入委托卖出，卖出价格:%s,卖出数量:%s,minPrice=%s' %(analyse.vtSymbol,price,orderVolume,analyse.minSellPrice))
                analyse.available = 0
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """"""
        pass

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
        d[u'卖出条件'] = self.outPer
        self.putParamEvent(d)


########################################################################
class AutoTradeWidget(AlgoWidget):
    """"""
    
    #----------------------------------------------------------------------
    def __init__(self, algoEngine, parent=None):
        """Constructor"""
        super(AutoTradeWidget, self).__init__(algoEngine, parent)
        
        self.templateName = AutoTradeAlgo.templateName
        
    #----------------------------------------------------------------------
    def initAlgoLayout(self):
        """"""
        self.lineSymbol = QtWidgets.QLineEdit()
        
        self.quoteCurrency = QtWidgets.QLineEdit()
           
        self.outPer = QtWidgets.QDoubleSpinBox()
        self.outPer.setMinimum(0)
        self.outPer.setMaximum(100)
        self.outPer.setDecimals(1)
        
        Label = QtWidgets.QLabel
        
        grid = QtWidgets.QGridLayout()
        grid.addWidget(Label(u'计价币种'), 0, 0)
        grid.addWidget(self.quoteCurrency, 0, 1)
        grid.addWidget(Label(u'卖出条件(%)'), 1, 0)
        grid.addWidget(self.outPer, 1, 1)
        
        return grid
    
    #----------------------------------------------------------------------
    def getAlgoSetting(self):
        """"""
        setting = OrderedDict()
        setting['templateName'] = AutoTradeAlgo.templateName
        setting['quoteCurrency'] = str(self.quoteCurrency.text())
        setting['outPer'] = float(self.outPer.text())

        
        return setting
    
    
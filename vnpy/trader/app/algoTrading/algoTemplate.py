# encoding: UTF-8

from __future__ import division
from datetime import datetime

from vnpy.trader.vtConstant import STATUS_NOTTRADED, STATUS_PARTTRADED, STATUS_UNKNOWN


# 活动委托状态
STATUS_ACTIVE = [STATUS_NOTTRADED, STATUS_PARTTRADED, STATUS_UNKNOWN]


########################################################################
class AlgoTemplate(object):
    """算法模板"""
    templateName = 'AlgoTemplate'
    
    timestamp = ''
    count = 0
    
    @classmethod
    #----------------------------------------------------------------------
    def new(cls, engine, setting):
        """创建新对象"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        if timestamp != cls.timestamp:
            cls.timestamp = timestamp
            cls.count = 0
        else:
            cls.count += 1
            
        algoName = '_'.join([cls.templateName, cls.timestamp, str(cls.count)])
        algo = cls(engine, setting, algoName)
        return algo

    #----------------------------------------------------------------------
    def __init__(self, engine, setting, algoName):
        """Constructor"""
        self.engine = engine
        self.active = True
        self.algoName = algoName
        self.activeOrderDict = {}  # vtOrderID:order
    
    #----------------------------------------------------------------------
    def updateTick(self, tick):
        """"""
        if not self.active:
            return
        
        self.onTick(tick)
    
    #----------------------------------------------------------------------
    def updateTrade(self, trade):
        """"""
        if not self.active:
            return
        
        self.onTrade(trade)
	
    #----------------------------------------------------------------------
    def updatePosition(self, position):
	""""""
	if not self.active:
	    return

	self.onPosition(position)	
    
    #----------------------------------------------------------------------
    def updateOrder(self, order):
        """"""
        if not self.active:
            return
        
        # 活动委托需要缓存
        if order.status in STATUS_ACTIVE:
            self.activeOrderDict[order.vtOrderID] = order
        # 结束委托需要移除
        elif order.vtOrderID in self.activeOrderDict:
            del self.activeOrderDict[order.vtOrderID]
        
        self.onOrder(order)
    
    #----------------------------------------------------------------------
    def updateTimer(self):
        """"""
        if not self.active:
            return
        
        self.onTimer()
	
    #----------------------------------------------------------------------
    def updateHistory(self, history):
	""""""
	if not self.active:
	    return

	self.onHistory(history)	
        
    #----------------------------------------------------------------------
    def stop(self):
        """"""
        self.active = False
        self.cancelAll()
        
        self.onStop()
        
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """"""
        pass
    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """"""
        pass
    
    #----------------------------------------------------------------------
    def onPosition(self, position):
	""""""
	pass    
    
    #----------------------------------------------------------------------
    def onOrder(self, order):
        """"""
        pass
    
    #----------------------------------------------------------------------
    def onTimer(self):
        """"""
        pass
    
    #----------------------------------------------------------------------
    def onStop(self):
        """"""
        pass
    
    #----------------------------------------------------------------------
    def subscribe(self, vtSymbol):
        """"""
        self.engine.subscribe(self, vtSymbol)
	
    #----------------------------------------------------------------------
    def commitSubscribe(self, gatewayName):
	""""""
	self.engine.commitSubscribe(gatewayName)
	
    #----------------------------------------------------------------------
    def queryConnectEnabled(self, gatewayName):
	""""""
	return self.engine.queryConnectEnabled(gatewayName)	    
	
    #----------------------------------------------------------------------
    def addSymbolsMonitor(self, vtSymbol):
	""""""
	self.engine.addSymbolsMonitor(vtSymbol)	
	
    #----------------------------------------------------------------------
    def delSymbolsMonitor(self, vtSymbol):
	""""""
	self.engine.delSymbolsMonitor(vtSymbol)		
	
    #----------------------------------------------------------------------
    def unsubscribe(self, vtSymbol):
	""""""
	self.engine.unsubscribe(self, vtSymbol)	
    
    #----------------------------------------------------------------------
    def buy(self, vtSymbol, price, volume, priceType=None, offset=None):
        """"""
        return self.engine.buy(self, vtSymbol, price, volume, priceType, offset)
    
    #----------------------------------------------------------------------
    def sell(self, vtSymbol, price, volume, priceType=None, offset=None):
        """"""
        return self.engine.sell(self, vtSymbol, price, volume, priceType, offset)
    
    #----------------------------------------------------------------------
    def cancelOrder(self, vtOrderID):
        """"""
        self.engine.cancelOrder(self, vtOrderID)
    
    #----------------------------------------------------------------------
    def cancelAll(self):
        """"""
        if not self.activeOrderDict:
            return False
        
        for order in self.activeOrderDict.values():
            self.cancelOrder(order.vtOrderID)
        return True
    
    #----------------------------------------------------------------------
    def getTick(self, vtSymbol):
        """"""
        return self.engine.getTick(self, vtSymbol) 
   
    #----------------------------------------------------------------------
    def getContract(self, vtSymbol):
        """"""
        return self.engine.getContract(self, vtSymbol)  
    
    #----------------------------------------------------------------------
    def getAllContracts(self):
        """查询所有合约"""
        return self.engine.getAllContracts(self)
	
    #----------------------------------------------------------------------
    def getKLineHistory(self, vtSymbol, period, size, startTime = 0, endTime = 0):
	"""查询K线回调"""
	return self.engine.getKLineHistory(vtSymbol, period, size, startTime, endTime)
    
    #----------------------------------------------------------------------
    def qryPositionSync(self, gatewayName):
	""""""
	return self.engine.qryPositionSync(gatewayName)
    
    #----------------------------------------------------------------------
    def qryTradeSync(self, symbol, gatewayName):
	""""""
	return self.engine.qryTradeSync(symbol, gatewayName)
    
    #----------------------------------------------------------------------
    def roundValue(self, value, change):
        """标准化价格或者数量"""
	"""修改为四舍五不入"""
        if not change:
            return value
        
        n = value / change
        v = round(n, 0) * change
	
	if v > value:
	    v = v - change
	
	#round(3,0)=3.0作为数量给火币会报错,需要返回3
	if change >= 1:
	    v = int(v)

	return v	 
    #----------------------------------------------------------------------
    def putVarEvent(self, d):
        """更新变量"""
        d['active'] = self.active
        self.engine.putVarEvent(self, d)
        
    #----------------------------------------------------------------------
    def putParamEvent(self, d):
        """更新参数"""
        self.engine.putParamEvent(self, d)
	
    #----------------------------------------------------------------------
    def saveTopIncrData(self, data):
	""""""
	self.engine.saveTopIncrData(data)
	
    #----------------------------------------------------------------------
    def loadTopIncrData(self, key):
	""""""
	self.engine.loadTopIncrData(key)
    
    #----------------------------------------------------------------------
    def writeLog(self, content):
        """输出日志"""
        self.engine.writeLog(content, self)
        
        
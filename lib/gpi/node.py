#    Copyright (C) 2014  Dignity Health
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    NO CLINICAL USE.  THE SOFTWARE IS NOT INTENDED FOR COMMERCIAL PURPOSES
#    AND SHOULD BE USED ONLY FOR NON-COMMERCIAL RESEARCH PURPOSES.  THE
#    SOFTWARE MAY NOT IN ANY EVENT BE USED FOR ANY CLINICAL OR DIAGNOSTIC
#    PURPOSES.  YOU ACKNOWLEDGE AND AGREE THAT THE SOFTWARE IS NOT INTENDED FOR
#    USE IN ANY HIGH RISK OR STRICT LIABILITY ACTIVITY, INCLUDING BUT NOT
#    LIMITED TO LIFE SUPPORT OR EMERGENCY MEDICAL OPERATIONS OR USES.  LICENSOR
#    MAKES NO WARRANTY AND HAS NOR LIABILITY ARISING FROM ANY USE OF THE
#    SOFTWARE IN ANY HIGH RISK OR STRICT LIABILITY ACTIVITIES.
#
#    The code in this file was modifed/derived from the elasticnodes.py
#    example with the license:
#############################################################################
##
## Copyright (C) 2010 Riverbank Computing Limited.
## Copyright (C) 2010 Nokia Corporation and/or its subsidiary(-ies).
## All rights reserved.
##
## This file is part of the examples of PyQt.
##
## $QT_BEGIN_LICENSE:BSD$
## You may use this file under the terms of the BSD license as follows:
##
## "Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions are
## met:
##   * Redistributions of source code must retain the above copyright
##     notice, this list of conditions and the following disclaimer.
##   * Redistributions in binary form must reproduce the above copyright
##     notice, this list of conditions and the following disclaimer in
##     the documentation and/or other materials provided with the
##     distribution.
##   * Neither the name of Nokia Corporation and its Subsidiary(-ies) nor
##     the names of its contributors may be used to endorse or promote
##     products derived from this software without specific prior written
##     permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
## A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
## OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
## SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
## LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
## DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
## THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
## (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
## OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
## $QT_END_LICENSE$
##
#############################################################################

import os
import sys
import copy
import math
import inspect
import traceback
import subprocess
import numpy as np


# gpi
import gpi
from gpi import QtCore, QtGui
from .defaultTypes import GPIDefaultType
from .defines import NodeTYPE, GPI_APPLOOP, REQUIRED
from .defines import GPI_WIDGET_EVENT, GPI_PORT_EVENT, GPI_INIT_EVENT, GPI_REQUEUE_EVENT
from .defines import printMouseEvent, getKeyboardModifiers, stw
from .defines import GetHumanReadable_bytes, GetHumanReadable_time
from .logger import manager
from .port import InPort, OutPort
from .stateMachine import GPI_FSM, GPIState
from .functor import GPIFunctor
from .sysspecs import Specs

# start logger for this module
log = manager.getLogger(__name__)

# Timer Pack
# GUI updates often need to be prodded at some interval for a duration, and
# then shutdown.  This seems to require 2 timers, one for interval, one for ON
# duration.
class TimerPack(object):

    def __init__(self):
        self._interval = QtCore.QTimer()
        self._ON = QtCore.QTimer()
        self._ON.setSingleShot(True)
        self._ON.timeout.connect(self._interval.stop)

    def setTimeoutSlot_interval(self, f):
        self._interval.timeout.connect(f)

    def setTimeoutSlot_ON(self, f):
        self._ON.timeout.connect(f)

    def setInterval(self, t):
        self._interval.setInterval(t)

    def setDuration(self, t):
        self._ON.setInterval(t)

    def isActive(self):
        return self._interval.isActive()

    def start(self):
        self._interval.start()
        self._ON.start()


# Event Manager
# Stores new events (without duplicates) in a timely manner.
class EventManager(object):

    def __init__(self):
        self._wdg_events = set()  # holds wdg names
        self._port_events = set()  # port names
        self._init_event = False  # bool
        self._requeue_event = False  # bool

    def addWidgetEvent(self, e):
        self._wdg_events.add(e)

    def addPortEvent(self, e):
        self._port_events.add(e)

    def setInitEvent(self):
        self._init_event = True

    def setRequeueEvent(self):
        self._requeue_event = True

    @property
    def widget(self):
        return self._wdg_events

    @property
    def port(self):
        return self._port_events

    @property
    def init(self):
        return self._init_event

    @property
    def requeue(self):
        return self._requeue_event

    @property
    def events(self):
        o = {}
        o[GPI_WIDGET_EVENT] = self._wdg_events
        o[GPI_PORT_EVENT] = self._port_events
        o[GPI_INIT_EVENT] = self._init_event
        o[GPI_REQUEUE_EVENT] = self._requeue_event
        return o

    def __str__(self):
        msg = 'widgets: '+str(self._wdg_events)+'\n'
        msg += 'ports: '+str(self._port_events)+'\n'
        msg += 'init: '+str(self._init_event)+'\n'
        msg += 'requeue: '+str(self._requeue_event)
        return msg

class NodeEvent(object):
    def __init__(self):
        self._status = None


class NodeSignalMediator(QtCore.QObject):
    # http://kedeligdata.blogspot.com/2010/01/pyqt-emitting-events-from-non-
    # qobject.html
    _switchSig = gpi.Signal(str)
    _forceUpdate = gpi.Signal()
    _curState = gpi.Signal(str)

    def __init__(self):
        super(NodeSignalMediator, self).__init__()


class Node(QtGui.QGraphicsItem):
    Type = NodeTYPE

    # These signals are being patched in so that the inner workings of the node
    # do not need to be abstracted from the QGraphicsItem() since it is not a
    # QObject().  This is just a stepping stone for migrating to a proper
    # solution.
    def _switchSig():
        def fget(self):
            return self._mediator._switchSig
        return locals()
    _switchSig = property(**_switchSig())

    def _forceUpdate():
        def fget(self):
            return self._mediator._forceUpdate
        return locals()
    _forceUpdate = property(**_forceUpdate())

    def _curState():
        def fget(self):
            return self._mediator._curState
        return locals()
    _curState = property(**_curState())

    def __init__(self, CanvasBackend, nodeCatItem=None, nodeIF=None, nodeIFscroll=None, nodeMenuClass=None):
        super(Node, self).__init__()

        self._mediator = NodeSignalMediator()

        # keep a ref for info
        self.item = nodeCatItem

        # During re-instantiation (from .net file) this is
        # the old id, if the node is new then its the current id.
        self._id = None
        self.setID()
        self._ext_filename = None

        self.nodeCompute_thread = None
        self._computeDuration = []

        self.initStateMachine()

        self.graph = CanvasBackend
        self.inportList = []
        self.outportList = []
        self.newPos = QtCore.QPointF()

        self.setFlag(QtGui.QGraphicsItem.ItemIsMovable)
        self.setFlag(QtGui.QGraphicsItem.ItemIsSelectable)
        self.setFlag(QtGui.QGraphicsItem.ItemSendsGeometryChanges)
        self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        self.setZValue(2)

        # event status
        self._event_type = None  # {type:title} # deprecated
        self._events = EventManager()  # event obj to replace _event_type
        self._events_handoff = None
        self._event_pending = False
        self._node_disabled = False
        self._requeue = False
        self._markedForDeletion = False

        # node name
        self.name = "Node"
        self._hierarchal_level = -1
        self.title_font = QtGui.QFont(u"times", 14)
        self.progress_font = QtGui.QFont(u"times", 8)

        self._progress_done = TimerPack()
        self._progress_done.setTimeoutSlot_interval(self.update)
        self._progress_done.setTimeoutSlot_ON(self.prepareGeometryChange)
        self._progress_done.setTimeoutSlot_ON(self.update)
        self._progress_done.setInterval(100)  # msec
        self._progress_done.setDuration(300)  # done duration (when 100% is shown)
        self._progress_was_on = False
        self._progress_recalculate = 0
        self._progress_recalculate2 = 0
        self._progress_recalculate3 = 0

        self._prog_thresh = 1  # sec

        # right side display width
        self._extra_right = 0

        # progress timer
        self._progress_timer = QtCore.QTimer()
        self._progress_timer.timeout.connect(self.update)
        self._progress_timer.setInterval(100)  # msec, redraw

        # RELOAD
        # reload linger and fade-out timers
        self._reload_timer = QtCore.QTimer()
        self._reload_timer.setSingleShot(True)
        self._reload_timer.timeout.connect(self.reloadDone)
        self._reload_timer.setInterval(2000) # msec, linger

        # get a menu instance
        if nodeCatItem:
            self._moduleName = nodeCatItem.name

            self._nodeIF = None  # must exist so that it can be
                                 # recursively checked by nodeMenuClass
            self._nodeIF = nodeCatItem.description()(self)
            self._nodeIF.modifyWdg.connect(self.modifyWdg)

            # get module description filename
            self._ext_filename = nodeCatItem.editable_path

            # make widget menus scrollable
            self._nodeIF_scrollArea = QtGui.QScrollArea()
            self._nodeIF_scrollArea.setWidget(self._nodeIF)
            self._nodeIF_scrollArea.setWidgetResizable(True)
            self._scroll_grip = QtGui.QSizeGrip(self._nodeIF)
            self._nodeIF_scrollArea.setCornerWidget(self._scroll_grip)
            self._nodeIF_scrollArea.setGeometry(50, 50, 1000, 2000)

        # old-style constructor (deprecate)
        elif nodeMenuClass:
            self._moduleName = nodeMenuClass.__module__.split('_GPI')[0]
            if self._moduleName == '__main__':
                self._moduleName = "Node"
            self._nodeIF = None  # must exist so that it can be
                                # recursively checked by nodeMenuClass
            self._nodeIF = nodeMenuClass(self)
            self._nodeIF.modifyWdg.connect(self.modifyWdg)

            # get module description filename
            self._ext_filename = inspect.getfile(nodeMenuClass)
            self._ext_filename = os.path.splitext(self._ext_filename)[0] + '.py'

            # make widget menus scrollable
            self._nodeIF_scrollArea = QtGui.QScrollArea()
            self._nodeIF_scrollArea.setWidget(self._nodeIF)
            self._nodeIF_scrollArea.setWidgetResizable(True)
            self._nodeIF_scrollArea.setGeometry(50, 50, 1000, 2000)

        else: # assume nodeIF and nodeIFscroll
            self._nodeIF = nodeIF
            self._nodeIF_scrollArea = nodeIFscroll

        self._menuHasRaised = False

        if hasattr(self._nodeIF, 'updateTitle'):
            self._nodeIF.updateTitle()

        self._curState.connect(self._nodeIF.setStatus_sys)

        self.setAcceptHoverEvents(True)
        self.beingHovered = False
        self.updateToolTips()

        # make sure the node is fully loaded before starting
        self._machine.start(self._idleState)

        # process initUI return codes
        try:
            if hasattr(self._nodeIF, 'initUI_return'):
                ret = self._nodeIF.initUI_return()
                if (ret is None) or (ret == 0):
                    # success
                    pass
                elif ret > 0:
                    self._machine.next('init_warn')
                elif ret < 0:
                    self._machine.next('init_error')

        except:
            log.warn('initUI() retcode handling skipped. '+str(self.item.fullpath))

    def loadNodeIFSettings(self, s):
        self._nodeIF.loadSettings(s)

    def getNodeDefinitionPath(self):
        return self._ext_filename

    def setDeleteFlag(self, val):
        self._markedForDeletion = val

    def isMarkedForDeletion(self):
        return self._markedForDeletion

    def displayReloaded(self):
        self._reload_timer.start()
        self._extra_right = 25
        self.update()

    def reloadDone(self):
        self._extra_right = 0
        self.prepareGeometryChange() # this is required to clear the msg
        self.update()

    def initStateMachine(self):  # NODE
        # Set up intial state graph.
        self._machine = GPI_FSM('NODE')
        self._switchSig.connect(self._machine.next)

        # node states
        self._idleState = GPIState('idle', self.idleRun, self._machine)
        self._chkInPortsState = GPIState('chkInPorts', self.chkInPortsRun, self._machine)
        self._computeState = GPIState('compute', self.computeRun, self._machine)
        self._post_compState = GPIState('post_compute', self.post_computeRun, self._machine)
        self._errorState = GPIState('error', self.errorRun, self._machine)
        self._warningState = GPIState('warning', self.warningRun, self._machine)
        self._disabledState = GPIState('disabled', self.disabledRun, self._machine)

        # make state graph
        # idle
        self._idleState.addTransition('check', self._chkInPortsState)
        self._idleState.addTransition('disable', self._disabledState)
        self._idleState.addTransition('init_error', self._errorState)
        self._idleState.addTransition('init_warn', self._warningState)  # should this exist?

        # chkInPorts
        self._chkInPortsState.addTransition('compute', self._computeState)
        self._chkInPortsState.addTransition('ignore', self._idleState)
        self._chkInPortsState.addTransition('warning', self._warningState)
        self._chkInPortsState.addTransition('error', self._errorState)
        self._chkInPortsState.addTransition('disable', self._disabledState)

        # compute
        self._computeState.addTransition('error', self._errorState)
        self._computeState.addTransition('next', self._post_compState)
        self._computeState.addTransition('disable', self._disabledState)

        # post_compute
        self._post_compState.addTransition('finished', self._idleState)
        self._post_compState.addTransition('warning', self._warningState)
        self._post_compState.addTransition('error', self._errorState)
        self._post_compState.addTransition('disable', self._disabledState)

        # warning
        self._warningState.addTransition('check', self._chkInPortsState)
        self._warningState.addTransition('disable', self._disabledState)

        # error
        #self._errorState.addTransition('check', self._chkInPortsState)
        self._errorState.addTransition('disable', self._disabledState)

        # disabled
        self._disabledState.addTransition('enable', self._idleState)

    def start(self):  # NODE
        if self.inIdleState():
            log.debug("NODE(" + self.name + "): emit switchSig")
            self._switchSig.emit('check')  # get out of idle
        elif self.inWarningState():
            log.debug("NODE(" + self.name + "): FROM WARNING STATE: emit switchSig")
            self._switchSig.emit('check')  # get out of warning

        # should we allow moving from error state???
        #elif self.inErrorState():
        #    log.debug("NODE(" + self.name + "): FROM ERROR STATE: emit switchSig")
        #    self._switchSig.emit('check')  # get out of error

        else:
            log.error("NODE(" + self.name + "): Can't start node outside of idleState, skipping...")
            log.error(" ->current state: " + str(self.getCurStateName()))

    # Function executed upon state change:
    def idleRun(self, sig):
        self.printCurState()
        self._curState.emit('Idle ('+str(sig)+')')
        self.forceUpdate_NodeUI()
        if sig == 'finished' or sig == 'ignore':  # from post_compute or failed check
            # before allowing new UI signals to be processed, require that the last signal
            # was succesfully processed. -This significantly cuts down the amount of wdgEvents() emitted
            # and prevents recursion limit errors.
            self._nodeIF.blockWdgSignals(False)  # allow new UI signals to trigger
            # re-enter processing state don't go to processing if change is
            # from 'disabled' or 'init' states
            self.graph._switchSig.emit('next')

    def chkInPortsRun(self, sig):
        self.printCurState()
        self._curState.emit('Check ('+str(sig)+')')
        try:
            if self.inPortsAreValid():
                log.debug(" ->compute")
                self._switchSig.emit('compute')
            else:
                log.debug(" ->ignore")
                self._switchSig.emit('ignore')
        except:
            log.error("chkInPortsRun(): Failed")
            #log.error(sys.exc_info())
            log.error(traceback.format_exc())
            log.error(" ->error")
            self._switchSig.emit('error')

    # computeRun() support
    def nextSigEmit(self):
        self._switchSig.emit('next')

    def errorSigEmit(self):
        self._switchSig.emit('error')

    def computeRun(self, sig):
        self.printCurState()
        self._curState.emit('Compute ('+str(sig)+')')
        try:
            self.forceUpdate_NodeUI()
            self.resetOutportStatus()  # changes color, allows 'change' to be determined

            # setup a new functor for either GPI_THREAD, GPI_PROCESS, or GPI_APPLOOP
            #   -QThreads have to be trashed anyway (not sure why, but they'll eventually
            #    segfault).
            self.nodeCompute_thread = GPIFunctor(self)
            self.nodeCompute_thread.finished.connect(self.nextSigEmit)  # -> post_computeRun()
            self.nodeCompute_thread.terminated.connect(self.errorSigEmit)

            self._progress_was_on = False
            self._progress_timer.start()
            self.prepareGeometryChange()  # tell scene to update
            self.nodeCompute_thread.start()

        except:
            log.error("computeRun(): Failed")
            log.error(traceback.format_exc())
            self._switchSig.emit('error')

    def post_computeRun(self, sig):
        self.printCurState()
        self._curState.emit('Post Compute ('+str(sig)+')')
        try:
            self._nodeIF.post_compute_widget_update()
            self.setWidgetOutports()
            self.updateToolTips()  # for ports
            self.updateToolTip()  # for node

            retcode = self.nodeCompute_thread.returnCode()
            # retcode: None: Terminated
            #             0: SUCCESS
            #            >0: WARNING -> Yellow
            #            <0: FAILURE -> Red
            if retcode < 0 or None:
                self._switchSig.emit('error')
            elif retcode > 0:
                self._switchSig.emit('warning')
            else:
                log.info("post compute SUCCESS, nextSig")
                self._switchSig.emit('finished')  # go to idle

            # Don't remove the thread!!!, over successive executions the same thread
            # address seems to get used and for some unidentifiable reason, the
            # last thread reference will delete THIS reference before post_computeRun()
            # can process the returnCode().
            #self.nodeCompute_thread = None

        except:
            log.error("post_computeRun(): Failed\n"+str(traceback.format_exc()))
            self._switchSig.emit('error')

        self._progress_timer.stop()
        if self._progress_was_on:
            self._progress_done.start()

    def errorRun(self, sig):
        self.printCurState()
        self.graph._switchSig.emit('pause')  # move canvas to a paused state to let users fix the problem
        self._curState.emit('Error ('+str(sig)+')')
        self.forceUpdate_NodeUI()

    def warningRun(self, sig):
        self.printCurState()
        self._curState.emit('Warning ('+str(sig)+')')
        self.forceUpdate_NodeUI()

    def disabledRun(self, sig):
        self._curState.emit('Disabled ('+str(sig)+')')
        self.printCurState()

    # State Checking:
    def getCurState(self):
        return self._machine.curState
        # return self._machine.configuration()

    def getCurStateName(self):
        '''return state names in a list of strings'''
        return self._machine.curStateName

    def printCurState(self):
        if manager.isDebug():
            log.debug("---------------------- Current Node("+self.name+") State(s):" + self.getCurStateName())

    def inIdleState(self):
        if self._idleState is self.getCurState():
            return True
        return False

    def waitUntilIdle(self):
        # while not self.inIdleState():
            QtGui.QApplication.processEvents()  # allow gui to update

    def inErrorState(self):
        if self._errorState is self.getCurState():
            return True
        return False

    def inWarningState(self):
        if self._warningState is self.getCurState():
            return True
        return False

    def isProcessingEvent(self):
        return (not self.inIdleState()) \
            and (not self.inWarningState()) \
            and (not self.inErrorState()) \
            and (not self.inDisabledState())

    def setDisabledState(self, val):
        if val is True:
            self._machine.next('disable')
            # self._switchSig.emit('disable')
        elif val is False:
            self._machine.next('enable')
            # self._switchSig.emit('enable')

    def inDisabledState(self):
        if self._disabledState is self.getCurState():
            return True
        return False

    def progressON(self):
        wt = self.maxWallTime()
        # if there is no walltime then don't est progress
        if wt and self.nodeCompute_thread:
            # only do progress bars if the node time is more than a second
            if (wt > self._prog_thresh) and (self.nodeCompute_thread.curTime() > self._prog_thresh):
                return True
        return False

    def setEventStatus(self, val):
        '''None: to clear event status.
        {GPI_PORT_EVENT:'title'}: for the event type and port name.
        {GPI_WIDGET_EVENT:'title'}: for the event type and widget name.
        {GPI_INIT_EVENT:None}: if the node is freshly added.
        {GPI_REQUEUE_EVENT:None}: if the node was automatically requeued.
        '''
        if val is not None:
            self._event_type = val  # keep last event
            self._event_pending = True

            self.appendEvent(val)

        else:
            self._event_pending = False
            # the queue and delete functions set this to none
            # so do the handoff at this point to make it available
            # to the user.
            self._events_handoff = self._events
            self._events = EventManager()  # make a new one

    def appendEvent(self, val):
        # translate to new obj
        if GPI_WIDGET_EVENT in val:
            self._events.addWidgetEvent(val[GPI_WIDGET_EVENT])
        if GPI_PORT_EVENT in val:
            # TODO: for some reason, events are being added to _nodeIF at close
            # so check for valid _nodIF function before using.
            # -its b/c nodes are being deleted, which is causing more events.
            # -this hack takes care of it for now.
            if hasattr(self._nodeIF, 'getWidgetNames'):
                # re-map widget-port events to widget events.
                if val[GPI_PORT_EVENT] in self._nodeIF.getWidgetNames():
                    self._events.addWidgetEvent(val[GPI_PORT_EVENT])
                else:
                    self._events.addPortEvent(val[GPI_PORT_EVENT])
        if GPI_INIT_EVENT in val:
            self._events.setInitEvent()
        if GPI_REQUEUE_EVENT in val:
            self._events.setRequeueEvent()

    def hasEventPending(self):
        return self._event_pending

    def getPendingEvent(self):
        '''Return copy of event to protect orig.'''
        return copy.deepcopy(self._event_type)

    def getPendingEvents(self):
        '''Return copy of event to protect orig.'''
        return copy.deepcopy(self._events_handoff)

    def getModuleName(self):
        return self._moduleName

    def setReQueue(self, val=False):  # NODE
        # At the end of a nodeQueue, these tasked are checked for
        # more events.
        self._requeue = val

    def modifyWdg(self, title, kwargs):  # NODE
        if self._nodeIF:  # not deleted
            self._nodeIF.modifyWidget_direct(str(title), **kwargs)

    def updateToolTips(self):
        for port in self.getPorts():
            port.updateToolTip()

    def getPortByID(self, pID):
        for port in self.getPorts():
            if port.getID() == pID:
                return port
        log.error("getPortByID(): failed to find port id: " + str(pID))

    def getPorts(self):
        return self.inportList + self.outportList

    def getCyclicPorts(self):
        plist = []
        for port in self.inportList:
            if port.allowsCyclicConn():
                plist.append(port)
        return plist

    def getNonCyclicPorts(self):
        plist = []
        for port in self.getPorts():
            if not port.allowsCyclicConn():
                plist.append(port)
        return plist

    def getInPortByNumOrTitle(self, pnumORtitle):
        return self.getPortByNumOrTitle(pnumORtitle, self.inportList)

    def getOutPortByNumOrTitle(self, pnumORtitle):
        return self.getPortByNumOrTitle(pnumORtitle, self.outportList)

    def getPortByNumOrTitle(self, pnumORtitle, portList=None):
        if portList is None:
            portList = self.getPorts()
        if type(pnumORtitle) is int:
            if (pnumORtitle < 0) or (pnumORtitle >= len(portList)):
                log.error("getPortByNumOrTitle (from Node): target out of port range: \'" +stw(pnumORtitle) +"\'")
                return
            src = portList[pnumORtitle]
        elif type(pnumORtitle) is str:
            src = None
            cnt = 0
            for port in portList:
                if port.portTitle == pnumORtitle:
                    src = port
                    pnumORtitle = cnt
                cnt += 1
            if src is None:
                log.error("getPortByNumOrTitle(): failed to find port: \'" + stw(pnumORtitle)+"\'")
                return
        else:
            log.critical("getPortByNumOrTitle(): ERROR: port identifier must be either int or str")
            return

        return src

    def getInPort(self, pnumORtitle):
        return self.getPortByNumOrTitle(pnumORtitle, self.inportList)

    def getOutPort(self, pnumORtitle):
        return self.getPortByNumOrTitle(pnumORtitle, self.outportList)

    def getPos(self):
        return [self.scenePos().x(), self.scenePos().y()]

    def getSettings(self):  # NODE SETTINGS
        '''list all settings required to re-instantiate this node
        '''
        s = {}
        if self.item:  # macro nodes won't have this item
            s['key'] = self.item.key()  # library lookup key
        if self.curWallTime():  # if the node hasn't been run, then there is no timing
            s['walltime'] = str(self.curWallTime())  # in sec
        s['avgwalltime'] = str(self.avgWallTime())
        s['stdwalltime'] = str(self.stdWallTime())
        s['id'] = self.getID()  # unique canvas id
        s['pos'] = self.getPos()
        s['name'] = self.getModuleName()
        s['widget_settings'] = copy.deepcopy(self._nodeIF.getSettings())
        s['ports'] = []
        for port in self.getPorts():
            s['ports'].append(copy.deepcopy(port.getSettings()))
        return s

    def getWidgetAndPortNames(self):
        o = []
        for p in self.getPorts():
            o.append(p.getName())
        for w in self._nodeIF.getWidgets():
            o.append(str(w.title()))
        return o

    def setID(self, value=None):
        if value is None:
            self._id = id(self)  # this will always be unique
        else:
            self._id = value

    def getID(self):
        return self._id

    def detachSelf(self):
        '''Remove all upstream and downstream connections'''
        # inports
        for port in self.inportList:
            self.detachPortByRef(port)
        # outports
        for port in self.outportList:
            self.detachPortByRef(port)

    def removePorts(self):
        '''Remove all connections, then delete the port objects'''
        self.detachSelf()

        for port in self.inportList:
            if port.scene():
                self.graph.scene().removeItem(port)
        del self.inportList[:]

        for port in self.outportList:
            if port.scene():
                self.graph.scene().removeItem(port)
        del self.outportList[:]

    def detachPortByRef(self, port):
        edges = list(port.edgeList)  # since edgeList is modified by detachSelf
        for edge in edges:
            edge.detachSelf()
            if edge.scene():
                self.graph.scene().removeItem(edge)
            # del edge

    def removePortByRef(self, port):
        self.detachPortByRef(port)
        try:
            self.inportList.remove(port)
        except:
            try:
                self.outportList.remove(port)
            except:
                log.critical("Port not found in either inportList or outportList.")
        if port.scene():
            self.graph.scene().removeItem(port)

    def removeMenu(self):
        # close widgets
        if self._nodeIF: # macro safe
            for parm in self._nodeIF.parmList:
                try:
                    if parm.parent() is self._nodeIF:  # not sure if this protects against
                        # c++ wrapper already deleted error
                        parm.setParent(None)
                        parm.close()
                except:
                    log.error(str(inspect.currentframe().f_back.f_lineno)+" parm has likely been deleted.  Skipping...")
            # close menu
            self._nodeIF.close()
            self._nodeIF = None
        if self._nodeIF_scrollArea:
            self._nodeIF_scrollArea = None

    def getParmList(self):
        return self._nodeIF.parmList

    def deleteComputeThread(self):
        if self.nodeCompute_thread:  # it is currently running
            self.nodeCompute_thread.blockSignals(True)
            if self.nodeCompute_thread.isRunning():
                log.debug("deleteComputeThread(): Node(" + self.name + \
                    "): Thread termination executed.")
                self.nodeCompute_thread.terminate()  # die hard
            self.nodeCompute_thread = None
            # not sure if deleting is the right way
            #del self.nodeCompute_thread

    def readyForDeletion(self):
        self.setDeleteFlag(True)
        # Removes edges, ports, and menu before its removed from the scene
        self.setDisabledState(True)
        self.setEventStatus(None)
        self.removeMenu()
        self.removePorts()
        self.deleteComputeThread()

#    def hoverEnterEvent(self, event):
#        self.beingHovered = True
#        self.update()
#
#    def hoverLeaveEvent(self, event):
#        self.beingHovered = False
#        self.update()

    def appendWallTime(self, time):
        '''Only keep the last 100 wall times.
        '''
        self._computeDuration.append(time)
        if len(self._computeDuration) > 100:
            self._computeDuration.pop(0)

    def curWallTime(self):
        if len(self._computeDuration):
            return self._computeDuration[-1]

    def maxWallTime(self):
        # get the most recent time over 'thresh'
        if len(self._computeDuration):
            x = np.array(self._computeDuration)
            x = x[x > self._prog_thresh]
            if len(x) > 0:
                return x[-1]
            #return max(self._computeDuration)

    def avgWallTime(self):
        if len(self._computeDuration):
            return sum(self._computeDuration)/len(self._computeDuration)

    def stdWallTime(self):
        if len(self._computeDuration):
            avg = self.avgWallTime()  # a little wastefull
            return math.sqrt(sum( [ (x-avg)**2 for x in self._computeDuration ] )/len(self._computeDuration))

    def portMem(self):
        # a byte count of all outport memory being held
        bytes_held = 0
        for port in self.outportList:

            # numpy arrays have a direct byte count
            if hasattr(port.data, 'nbytes'):
                bytes_held += port.data.nbytes  

            # try to get an estimate of the object w/ sys
            else:
                bytes_held += sys.getsizeof(port.data)

        return bytes_held

    def updateToolTip(self):  # NODE

        bytes_held = self.portMem()

        if Specs.TOTAL_PHYMEM() == 0:
            pct_physmem = ""
        else:
            pct_physmem = ", %.*f%s RAM" % (1, float(
                100.0 * bytes_held / Specs.TOTAL_PHYMEM()), "%")

        # compute duration might not exist if node dies/fails to load.
        try:
            tip = 'Wall Time: ' + GetHumanReadable_time(self._computeDuration[-1]) + "\n"
        except:
            tip = ''

        if len(self._computeDuration):
            avg = self.avgWallTime()
            std = self.stdWallTime()
            tip += u'\u03BC = ' + GetHumanReadable_time(avg) 
            tip += u', \u03C3 = ' + GetHumanReadable_time(std) 
            tip += u', n = ' + str(len(self._computeDuration)) + '\n'

        tip += 'Outport Mem: ' + GetHumanReadable_bytes(
            bytes_held) + pct_physmem
        self.setToolTip(tip)

    def setHierarchalLevel(self, level):
        self._hierarchal_level = level

    def getHierarchalLevel(self):
        return self._hierarchal_level

    def resetHierarchalLevel(self):
        self._hierarchal_level = -1

    def menu(self):
        '''raises node menu.'''
        if not self._menuHasRaised:
            self._nodeIF_scrollArea.resize(self._nodeIF.sizeHint())
            self._menuHasRaised = True
        self._nodeIF_scrollArea.show()
        self._nodeIF_scrollArea.raise_()
        self._nodeIF.activateWindow()

    def closemenu(self):
        '''closes node menu.'''
        if self._nodeIF_scrollArea:
            self._nodeIF_scrollArea.close()
            self._menuHasRaised = False

    def getModuleCompute(self):
        return self._nodeIF.compute

    def getModuleValidate(self):
        return self._nodeIF.validate

    def getNodeLabel(self):
        return self._nodeIF.label

    def forceUpdate_NodeUI(self):
        self._forceUpdate.emit()
        self.update()
        # only run this if execType is an APPLOOP
        if self._nodeIF.execType() == GPI_APPLOOP:
            QtGui.QApplication.processEvents()  # allow gui to update

    def execType(self):
        return self._nodeIF.execType()

    def inPortsAreValid(self):
        # check that all required ports have data
        # and that the data matches the requested type
        dontRunFlag = False
        for inport in self.inportList:
            if inport.getUpstreamData() is None:
                if inport.isREQUIRED():
                    # skip compute routine and cleanup
                    # don't send downstream events
                    log.debug("nodeCompute(): inport is required, but empty, skipping compute()")
                    dontRunFlag = True
            else:
                # check that the data match the port description
                if not inport.incomingDataTypeMatches():
                    # disconnect the port since the data, now doesn't match
                    # or throw an error? Not sure which is better.
                    edge = inport.edgeList[0]
                    edge.detachSelf()
                    if edge.scene():
                        self.graph.scene().removeItem(edge)

                    log.debug("nodeCompute(): incoming data doesn't match, skipping compute()")
                    dontRunFlag = True
                else:  # there IS data and it DOES match:
                    # set widget data if necessary
                    if inport.isWidgetPort():
                        # print "nodeCompute(): "+inport.menuWidget.getTitle() + \
                        #    " value is set to: " + str(inport.getUpstreamData())
                        inport.menuWidget.setValueQuietly(
                            inport.getUpstreamData())
        return (not dontRunFlag)

    def setWidgetOutports(self):
        # send events for widget ports
        for port in self.outportList:
            if port.isWidgetPort():
                if port.setWidgetData():
                    port.setDownstreamEvents()
                    port.update()

    def resetOutportStatus(self):
        for port in self.outportList:
            port.setDataCalled(False)
            port.update()

    def setData(self, pnumORtitle, data):
        '''Set output data, determine port status, and send downstream events'''
        port = self.getOutPort(pnumORtitle)
        port.setData(data)
        if port.dataHasChanged():
            port.setDownstreamEvents()
        port.update()
        # allow gui update so port status can be seen
        # QtGui.QApplication.processEvents()

    def isTopNode(self):
        cnt = 0
        for port in self.getPorts():
            if isinstance(port, InPort):
                cnt += len(port.edges())
        if cnt == 0:
            return True
        else:
            return False

    def getConnectionTuples(self):
        '''For each port (in and out) on this node list the connected nodes as
        a tuple indicating (src, sink) relationship.
        '''
        c = []
        for port in self.getPorts():
            c += port.getConnectionTuples()
        return c

    def getNonCyclicConnectionTuples(self):
        '''For each port (in and out) on this node list the connected nodes as
        a tuple indicating (src, sink) relationship.
        '''
        c = []
        for port in self.getPorts():
            c += port.getNonCyclicConnectionTuples()
        return c

    def edges(self):
        edges = []
        for port in self.getPorts():
            for edge in port.edges():
                edges.append(edge)
        return(edges)

    def setName(self, name):
        self.name = name
        self.update()  # update node appearance
        if self._nodeIF is not None:  # update node menu
            self._nodeIF.updateTitle()

    def getName(self):
        return self.name

    def getNameFromItem(self):
        return self.item.name

    def getFullPath(self):
        return self.item.fullpath

    def refreshName(self):
        '''Name based on node level and pending event status'''
        self.update()

    def titleExists(self, title):
        for port in self.getPorts():
            if port.portTitle == title:
                return True
        # print type(self)
        if self._nodeIF:
            for wdg in self._nodeIF.parmList:
                if wdg.getTitle() == title:
                    return True
        return False

    # Parse the extTypes dict held by the graph
    # to get an instance of the requested GPIType.
    def findGPIType(self, ptype):
        if self.graph:
            typ, req = self.graph._library.getType(ptype)
            if not req:
                log.warn(str(self._moduleName)+' NODE: Requested port-type: \''+str(ptype)+'\' not found.  Using \'PASS\' instead.')
            return typ
        else:  # this is just in case the node is being instantiated as a dummy
            return GPIDefaultType()

    def addInPort(self, title=None, ptype=None, obligation=REQUIRED, menuWidget=None, cyclic=False, **kwargs):  # NODE

        # check if title is used (but not for wdg ports,
        # they are already checked).
        if self.titleExists(title) and (menuWidget is None):
            log.error("addInPort(): Port title \'" + str(title) \
                + "\' is already in use! Aborting.")
            return

        # Parse kwargs for InPort and GPIType args.
        # Then send the appropriate args to GPIType() and InPort()
        # constructors respectively.
        # If no type can be found (including basic py-types), then
        # use the GPIDefaultType for a PASS port.
        type_cls = self.findGPIType(ptype)
        type_cls.setTypeParms(**kwargs)

        portNum = len(self.inportList)
        port = InPort(self, self.graph, title, portNum,
                      intype=type_cls, obligation=obligation, menuWidget=menuWidget, cyclic=cyclic)
        port.setParentItem(self)
        port.setPosByPortNum(portNum)
        self.inportList.append(port)

    def addOutPort(self, title=None, ptype=None, obligation=REQUIRED, menuWidget=None, **kwargs):  # NODE

        # check if title is used (but not for wdg ports,
        # they are already checked).
        if self.titleExists(title) and (menuWidget is None):
            log.error("addOutPort(): Port title \'" + str(title) \
                + "\' is already in use! Aborting.")
            return

        # Parse kwargs for OutPort and GPIType args.
        # Then send the appropriate args to GPIType() and OutPort()
        # constructors respectively.
        # If no type can be found (including basic py-types), then
        # use the GPIDefaultType for a PASS port.
        type_cls = self.findGPIType(ptype)
        type_cls.setTypeParms(**kwargs)

        portNum = len(self.outportList)
        port = OutPort(self, self.graph, title, portNum,
                       intype=type_cls, obligation=obligation, menuWidget=menuWidget)
        port.setParentItem(self)
        port.setPosByPortNum(portNum)
        self.outportList.append(port)

    def type(self):
        return Node.Type

    def calculateForces(self):
        if not self.scene() or self.scene().mouseGrabberItem() is self or self.isTopNode():
            self.newPos = self.pos()
            return

        # Sum up all forces pushing this item away.
        xvel = 0.0
        yvel = 0.0
        for item in self.scene().items():
            if not isinstance(item, Node):
                continue

            # don't let unattached nodes exert force
            if len(item.edges()) == 0:
                continue

            # get node distance
            line = QtCore.QLineF(self.mapFromItem(
                item, 0, 0), QtCore.QPointF(0, 0))
            dx = line.dx()
            dy = line.dy()
            l = 2.0 * (dx * dx + dy * dy)
            if l > 0:
                xvel += (dx * 150.0) / l
                yvel += (dy * 150.0) / l

        # Now subtract all forces pulling items together.
        weight = (len(self.edges()) + 1) * 5.0
        for edge in self.edges():
            if edge.sourceNode() is self:
                pos = self.mapFromItem(edge.destNode(), 0, 0)
            else:
                pos = self.mapFromItem(edge.sourceNode(), 0, 0)
            xvel += pos.x() / weight
            yvel += pos.y() / weight

        # downward force
        yvel += 0.01

        # friction
        if QtCore.qAbs(xvel) < 0.1 and QtCore.qAbs(yvel) < 0.1:
            xvel = yvel = 0.0

        sceneRect = self.scene().sceneRect()
        self.newPos = self.pos() + QtCore.QPointF(xvel, yvel)
        self.newPos.setX(min(max(
            self.newPos.x(), sceneRect.left() + 10), sceneRect.right() - 10))
        self.newPos.setY(min(max(
            self.newPos.y(), sceneRect.top() + 10), sceneRect.bottom() - 10))

    def advance(self):
        if self.newPos == self.pos():
            return False

        self.setPos(self.newPos)
        return True

    def boundingRect(self):
        adjust = 2.0
        w = self.getNodeWidth() + self.getProgressWidth() + self.getExtraWidth()
        return QtCore.QRectF((-10 - adjust), (-10 - adjust), (w + adjust), (23 + adjust))

    def getTitleWidth(self):
        '''Determine how long the module box is.'''
        buf = self.name
        if self._nodeIF:
            if self._nodeIF.label != '':
                buf += ": " + self._nodeIF.label
        fm = QtGui.QFontMetricsF(self.title_font)
        bw = fm.width(buf) + 11.0
        bh = fm.height()
        return (bw, bh)

    def getMaxPortWidth(self):
        '''Determine how long the module box is.'''
        l = max(len(self.inportList), len(self.outportList))
        # from addInPort(): -8+8*portNum
        return l * 8.0 + 4.0

    def getNodeWidth(self):
        return max(self.getMaxPortWidth(), self.getTitleWidth()[0])

    def getProgressWidth(self):
        w = 23
        conf = self.getCurState()
        if (self._computeState is conf) and self.progressON():
            return w 
        elif self._progress_done.isActive() and self._progress_was_on:
            return w
        return 0

    def getExtraWidth(self):
        '''for adding info displays to the right of the node.
        '''
        return self._extra_right

    def shape(self):
        path = QtGui.QPainterPath()
        w = self.getNodeWidth() + self.getProgressWidth() + self.getExtraWidth()
        path.addRect(-10, -10, w, 20)
        return path

    def paint(self, painter, option, widget):  # NODE
        # painter is a QPainter object

        w = self.getNodeWidth()
        # h = self.getTitleWidth()[1]

        # draw shadow
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtCore.Qt.darkGray)
        painter.drawRoundedRect(-8, -8, w, 20, 3, 3)

        # choose module color
        gradient = QtGui.QRadialGradient(-10, -10, 40)
        conf = self.getCurState()
        if self._computeState is conf:
            gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).lighter(70))
            gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.darkGray).lighter(70))

        elif (option.state & QtGui.QStyle.State_Sunken) or (self._errorState is conf):
            gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.darkRed).lighter(150))
            gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.red).lighter(150))

        elif self._warningState is conf:
            gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.yellow).lighter(180))
            gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.darkYellow).lighter(180))

        else:
            gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).lighter(150))
            gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.darkGray).lighter(150))

        # draw module box (apply color)
        painter.setBrush(QtGui.QBrush(gradient))
        if self.beingHovered or self.isSelected():
            painter.setPen(QtGui.QPen(QtCore.Qt.red, 1))
        else:
            painter.setPen(QtGui.QPen(QtCore.Qt.black, 0))
        painter.drawRoundedRect(-10, -10, w, 20, 3, 3)

        # title
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 0))
        painter.setFont(self.title_font)
    
        # label
        buf = self.name
        if self._nodeIF:
            if self._nodeIF.label != '':
                buf += ": " + self._nodeIF.label
        painter.drawText(-5, -9, w, 20, (QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter), unicode(buf))

        # reloaded disp
        if self._reload_timer.isActive() and not self.progressON():
            self.drawReload(painter)

        # progress disp
        if (self._computeState is conf) and self.progressON():

            wt = self.maxWallTime()
            pdone = self.nodeCompute_thread.curTime()/wt
            self._progress_was_on = True

            # normal counter
            if pdone < 1:
                self.drawProgress(painter, pdone)

            # recalculate
            else:
                self.drawRecalculating(painter)

        # force it to show 100% for a little longer
        elif self._progress_done.isActive() and self._progress_was_on:
            # clock circle
            pdone = 1
            self.drawProgress(painter, pdone)


    def drawProgress(self, painter, pdone):
        # color
        #painter.setPen(QtGui.QPen(QtCore.Qt.black, 0.25))
        painter.setPen(QtGui.QPen(QtCore.Qt.darkGreen, 0.25))

        # clock circle
        rect = QtCore.QRectF(-8.0+self.getNodeWidth(), -10, 20.0, 20.0)
        startAngle = 90 * 16
        spanAngle = -16 * 360 * pdone
        painter.drawArc(rect, startAngle, spanAngle)

        # pdone text
        painter.setFont(self.progress_font)
        buf = str(int(pdone*100))
        buf += '%'
        painter.drawText(-7+self.getNodeWidth(), -9, 20, 20, (QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter), unicode(buf))

    def drawReload(self, painter):
        # color
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 0.25))

        # clock circle
        rect = QtCore.QRectF(-6.0+self.getNodeWidth(), -7, 15.0, 15.0)
        startAngle = 180 * 16
        spanAngle = -16 * 270
        painter.drawArc(rect, startAngle, spanAngle)

        w = self.getNodeWidth() - 2
        h = 8
        self._arrow = [[w, h], [w+3.5, h-3.0], [w+3.5, h+3]]
        self._arrowShape = QtGui.QPolygonF()
        for i in self._arrow:
            self._arrowShape.append(QtCore.QPointF(i[0], i[1]))

        painter.setPen(QtGui.QPen(QtCore.Qt.black, 0))
        painter.drawPolygon(self._arrowShape)


    def drawRecalculating(self, painter):
        # color
        #painter.setPen(QtGui.QPen(QtCore.Qt.black, 0.25))
        painter.setPen(QtGui.QPen(QtCore.Qt.darkGreen, 0.25))

        # arcs 1
        rect = QtCore.QRectF(-8.0+self.getNodeWidth(), -10, 20.0, 20.0)
        startAngle = (( 0 - self._progress_recalculate) % 360) * 16 
        spanAngle  = 90 * 16
        painter.drawArc(rect, startAngle, spanAngle)

        startAngle = ((180 - self._progress_recalculate) % 360) * 16 
        spanAngle  = 90 * 16
        painter.drawArc(rect, startAngle, spanAngle)

        self._progress_recalculate = (self._progress_recalculate + 13) % 360

        # arcs 2 - inner
        if False:
            painter.setPen(QtGui.QPen(QtCore.Qt.red, 0.25))
            fugde = 2
            rect = QtCore.QRectF(-8.0+self.getNodeWidth()+fugde, -10+fugde, 20.0-fugde*2, 20.0-fugde*2)
            startAngle = (( 0 - self._progress_recalculate2) % 360) * 16 
            spanAngle  = 90 * 16
            painter.drawArc(rect, startAngle, spanAngle)

            startAngle = ((180 - self._progress_recalculate2) % 360) * 16 
            spanAngle  = 90 * 16
            painter.drawArc(rect, startAngle, spanAngle)

            self._progress_recalculate2 = (self._progress_recalculate2 + 11) % 360

        # arcs 3 - inner inner
        if False:
            painter.setPen(QtGui.QPen(QtCore.Qt.darkGreen, 0.25))
            fugde = 5
            rect = QtCore.QRectF(-8.0+self.getNodeWidth()+fugde, -10+fugde, 20.0-fugde*2, 20.0-fugde*2)
            startAngle = (( 0 - self._progress_recalculate3) % 360) * 16 
            spanAngle  = 90 * 16
            painter.drawArc(rect, startAngle, spanAngle)

            startAngle = ((180 - self._progress_recalculate3) % 360) * 16 
            spanAngle  = 90 * 16
            painter.drawArc(rect, startAngle, spanAngle)

            self._progress_recalculate3 = (self._progress_recalculate3 + 7) % 360

    def itemChange(self, change, value):
        if change == QtGui.QGraphicsItem.ItemPositionHasChanged:
            for port in self.getPorts():
                port.updateEdges()
            self.graph.itemMoved()  # charge-rep
            self.graph.viewAndSceneForcedUpdate()

        return super(Node, self).itemChange(change, value)

    def mousePressEvent(self, event):  # NODE
        printMouseEvent(event)
        modifiers = getKeyboardModifiers()

        self.update()  # update node color
        modmidbutton_event = (event.button() == QtCore.Qt.LeftButton
                              and modifiers == QtCore.Qt.AltModifier)
        if event.button() == QtCore.Qt.MidButton or modmidbutton_event:
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton:
            event.accept()  # this has to accept to be moved
        elif event.button() == QtCore.Qt.RightButton:
            event.accept()
        else:
            event.ignore()
        super(Node, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # NODE
        printMouseEvent(event)
        modifiers = getKeyboardModifiers()

        self.update()
        modrightbutton_event = ((event.button() == QtCore.Qt.RightButton)
                              and (modifiers == QtCore.Qt.ControlModifier))
        if event.button() == QtCore.Qt.MidButton:
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton:
            event.accept()  # this has to accept to be moved
        elif modrightbutton_event:

            # OSX users set their launchctl associated file prefs.
            if Specs.inOSX():
                if self.getNodeDefinitionPath():
                    #subprocess.call(["open " + self.getNodeDefinitionPath()], shell=True)
                    subprocess.Popen("open " + self.getNodeDefinitionPath(), shell=True)
                else:
                    log.warn('No external module definition found, aborting...')

            # Linux users set their editor choice
            # TODO: this should be moved to config
            elif Specs.inLinux():
                editor = 'gedit'
                if os.environ.has_key("EDITOR"):
                    editor = os.environ["EDITOR"]

                if self.getNodeDefinitionPath():
                    subprocess.Popen(editor + " " + self.getNodeDefinitionPath(), shell=True)
                else:
                    log.warn('No external module definition file (.py) found, aborting...')

            else:
                log.warn('The Quick-Edit feature is not available for this OS, aborting...')

        elif event.button() == QtCore.Qt.RightButton:
            event.accept()
            self.menu()
            self.graph.scene().makeOnlyTheseNodesSelected([self])
        else:
            event.ignore()
        super(Node, self).mouseReleaseEvent(event)

    # def mouseDoubleClickEvent(self, event):
    #    print "double-clicked a node"
    #    event.accept()



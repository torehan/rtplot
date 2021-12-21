#!/usr/bin/env python

from threading import Thread
from ctypes import alignment
import PySimpleGUI as sg
from random import randint
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, FigureCanvasAgg
from matplotlib.figure import Figure
import matplotlib.animation as animation
import matplotlib.pyplot as plt

import serial
import numpy as np
import numpy_ringbuffer as rb
import time
import json
from re import S, sub

import codecs

from serial.serialutil import SerialException


# Yet another usage of MatPlotLib with animations.
class rtplot:
    def __init__(self, serialPort='/dev/ttyUSB0', serialBaud=38400, plotLength=100):
        self.port = serialPort
        self.baud = serialBaud
        self.plotMaxLength = 1000
        self.plotLength = 100
        self.plotData = {}
        self.data =[]
        self.isSerialThreadRun = True
        self.isGuiRun = True    
        self.isReceiving = False
        self.isLogging = False
        self.isSerialConnected = None
        self.thread = None
        self.dataCounter = 0
        self.plotFilter = []
        self.logFilename = np.string_('')
        self.logFile = None
        self.logOutput = rb.RingBuffer(capacity = 1024, dtype = (np.string_,1024))

    def camel_case(s):
        s = sub(r"(_|-)+", " ", s).title().replace(" ", "")
        return ''.join([s[0].lower(), s[1:]])

    def openSerialConnection(self):
        print('Trying to connect to: ' + str(self.port) + ' at ' + str(self.baud) + ' BAUD.')
        try:
            self.serialConnection = serial.Serial(self.port, self.baud, timeout=4)
            print('Connected to ' + str(self.port) + ' at ' + str(self.baud) + ' BAUD.')
            return True
        except SerialException:
            self.isSerialConnected = False
            print('Failed to connect with ' + str(self.port) + ' at ' + str(self.baud) + ' BAUD.')  
            return False
            
    
    def startSerialThread(self):
        if self.thread == None:
            if self.openSerialConnection():
                self.isSerialThreadRun = True
                self.thread = Thread(target=self.startSerialThreadFunc,daemon=True)
                self.thread.start()
                # Block till we start receiving values
                while self.isReceiving != True:
                    time.sleep(0.1)

    def validateJSON(self, jsonData, dictData):
        try:
            dictData.update(json.loads(jsonData))
        except ValueError as err:
            return False
        return True

    def startSerialThreadFunc(self):    # retrieve data
        # time.sleep(1.0)  # give some buffer time for retrieving data
        self.serialConnection.reset_input_buffer()
            # self.serialConnection.readinto(self.rawData)
            # if (self.rawData)
        while (self.isSerialThreadRun):            
            while(not (self.serialConnection.in_waiting < 250)):
                try: 
                    # print(self.serialConnection.in_waiting)
                    self.rawData = self.serialConnection.read_until(b'}')
                    # print(self.rawData)
                    # print ('\n')
                    reader = codecs.getreader('utf-8')
                    try: 
                        self.rawData = self.rawData.decode('utf-8').replace("'",'"')
                        tmpJSON = {}
                        logOutput = ''
                        # print(self.rawData)
                        # print ("\n")            
                        if (self.validateJSON(self.rawData, tmpJSON)):
                            for key in tmpJSON:
                                if key in self.plotData:
                                    self.plotData[key].append(tmpJSON[key])
                                else:
                                    self.plotData[key] = [tmpJSON[key]]

                                if self.isLogging:
                                    if 'results' in key:
                                        logOutput = logOutput + '{:<16.8f}'.format(tmpJSON[key])
                                    else:
                                        logOutput = logOutput + '{:<16}'.format(tmpJSON[key])

                                while (len(self.plotData[key]) > self.plotLength):
                                    self.plotData[key].pop(0)

                            logOutput = logOutput+'\n'
                            if self.isLogging:                           
                                self.logOutput.append(np.array(logOutput))
                            
                        self.isReceiving = True
                    except UnicodeDecodeError:
                        print('could not parse the data')
                        self.serialConnection.reset_input_buffer()
                except serial.SerialException:
                    print('Failed to read from ' + str(self.port) + ' at ' + str(self.baud) + ' BAUD.')                    
                    self.closeSerialConnection()

    def closeSerialConnection(self):
        self.isSerialConnected = False
        self.serialConnection.close()

    def stopSerialThread(self):
        self.isSerialThreadRun = False
        self.thread.join()
        self.thread = None
        self.closeSerialConnection()
        print('Disconnected...')

def draw_figure(canvas, figure, loc=(0, 0)):
    figure_canvas_agg = FigureCanvasTkAgg(figure, canvas)
    figure_canvas_agg.draw()
    figure_canvas_agg.get_tk_widget().pack(side='top', fill='both', expand=1)
    return figure_canvas_agg

def main():

    sth = rtplot('COM10', 115200)

    sth.plotFilter = []
    sth.startSerialThread()
    time.sleep(2)


    plotInterval = 50 # in ms
    isRunning = True
    NUM_DATAPOINTS = 10000
    # define the form layout
    layoutTitle = [
        [sg.Multiline('Please add title. It will be used as name for log file.', size=(58, 1), key = 'title', justification='left', font='Helvetica 14')]
    ]
    layoutGraph = [
        [sg.Canvas(size=(640, 480), key='-CANVAS-', pad = (20,25))]
    ]
    
    layoutGraphElements = []

    if not layoutGraphElements:
        for key in sth.plotData:
            if "results" in key:
                cb = [sg.Checkbox(key+':', enable_events=True, size = (10,1), font='Helvetica 14', pad = ((5, 5), (25, 5)), tooltip = 'Select to add to plot', default=False, key='-PLOT-'+key+'-'), sg.T('value', pad = ((5, 5), (25, 5)), font = 'Helvetica 14', key = 'valueText'+key.capitalize())]
                layoutGraphElements.append(cb)

    layoutControls = [
        [sg.Text('Data points',size = (10,1), font='Helvetica 14', pad = ((5, 5), (20, 5))), sg.Slider(range=(10, 500), default_value=40,  pad = ((5, 5), (20, 5)), size=(50, 10), orientation='h', key='-SLIDER-DATAPOINTS-')],
        [sg.Text('Timeout', size = (10,1), font='Helvetica 14', pad = (5, 5)),sg.Slider(range=(10, 500), default_value=40, size=(50, 10), pad = (5, 5),orientation='h', key='-SLIDER-TIMEOUT-')],              
        [sg.Button('Start', size=(10, 1), font='Helvetica 14',  pad = (5, 30), bind_return_key=True, disabled = True),sg.Button('Stop', size=(10, 1), font='Helvetica 14',  pad = (5, 30), bind_return_key=True, disabled = False), sg.Button('Log', size=(10, 1),  pad = (5, 30), font='Helvetica 14', bind_return_key=True, disabled = False), sg.Button('Exit', size=(10, 1), pad=(50, 30), font='Helvetica 14')],
        [],                    
        [],
    ]

    layout = layoutTitle + [[
        sg.Column(layoutGraph, element_justification='c' ),
        sg.Column(layoutGraphElements + layoutControls, element_justification='l' )
    ]]
    # create the form and show it without the plot
    window = sg.Window('rtplot', layout, finalize=True)

    canvas_elem = window['-CANVAS-']
    canvas = canvas_elem.TKCanvas

    # draw the initial plot in the window
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.set_xlabel("Time [us]")
    ax.set_ylabel("[unitless]")     
    ax.set_ylim([0, 16384])    
    ax.grid()
    fig_agg = draw_figure(canvas, fig)
    xData = []
    yData = []
    sth.isGuiRun = True
    guiTimeout = 250
    while (sth.isGuiRun):
        event, values = window.read(timeout=guiTimeout)

        if event == sg.WIN_CLOSED or event in ('Exit', None):
            sth.isGuiRun = False
            break
        elif event.startswith('Start'):
            ax.cla()                    # clear the subplot
            sth.startSerialThread()
            window['Start'].update(disabled = True)
            window['Stop'].update(disabled = False)
        elif event.startswith('Stop'):
            sth.stopSerialThread()
            window['Stop'].update(disabled = True)
            window['Start'].update(disabled = False)

        elif event.startswith('Log'):
            if not sth.isLogging:
                sth.isLogging = True
                window['Log'].update(button_color='green')
                window['title'].update(disabled = True)
                datetimestr = np.datetime_as_string(np.datetime64("now"), unit='s')
                datetimestr = datetimestr.replace(':','')
                datetimestr = datetimestr.replace('-','')
                datetimestr = datetimestr.replace('T','')

                if not 'Please' in values['title']:
                    title = values['title']
                    sth.logFilename = np.char.add(np.array(values['title'].replace(' ', '_')+'_'),np.array(datetimestr))
                else:
                    sth.logFilename = np.char.add(np.array('log_'),np.array(datetimestr))

                sth.logFile =  open(np.array2string(sth.logFilename).replace("'",'')+'.txt',"a")
                header = ''
                for pd in sth.plotData:
                    header = header + '{:<16}'.format(pd)

                sth.logFile.write(header+'\n')   
                sth.logFile.close()

                
            else:
                window['Log'].update(button_color = sg.theme_button_color())

                sth.isLogging = False
                window['title'].update(disabled = False)
                sth.logFile.close()

        elif event.startswith('-PLOT'):
            for key in sth.plotData:
                if event.startswith('-PLOT-'+key+'-'):
                    if window['-PLOT-'+key+'-'].get():
                        sth.plotFilter.append(key)
                    else:
                        sth.plotFilter.remove(key)

        else:

            if sth.thread == None:
                window['Start'].update(disabled = False)
                window['Stop'].update(disabled = True)


            if bool(sth.plotData):
                guiTimeout = int(values['-SLIDER-TIMEOUT-'])
                sth.plotLength = int(values['-SLIDER-DATAPOINTS-']) # draw this many data points (on next line)

                ax.cla()                    # clear the subplot
                ax.grid()                   # draw the grid
                for pd in sth.plotData:
                    if pd != 'time' and 'results' in pd:
                        window['valueText' + pd.capitalize()].update(sth.plotData[pd][-1])                                    
                for pf in sth.plotFilter:
                    ax.plot(sth.plotData['time'], sth.plotData[pf], label = pf)

                if sth.isLogging:
                    sth.logFile =  open(np.array2string(sth.logFilename).replace("'",'')+'.txt',"a")
                    while(sth.logOutput._right_index - sth.logOutput._left_index > 10):
                        sth.logFile.write(sth.logOutput.pop().decode('UTF-8'))
                    sth.logFile.close()

                ax.set_xlabel("Time [us]")
                ax.set_ylabel("[unitless]")                    
                ax.legend()
                ylim = ax.get_ylim()
                ax.set_ylim([0, ylim[1]*1.15])    
                fig_agg.draw()



    window.close()
    if (sth.thread != None):
        sth.closeSerialConnection()            
    sth.logFile.close()

    exit(69)

if __name__ == '__main__':
    main()
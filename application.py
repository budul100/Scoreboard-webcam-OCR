# coding: utf8

from PySide import QtCore, QtGui
from PySide.QtCore import *
from PySide.QtGui import *
import sys
import time

from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory, listenWS
from twisted.internet import reactor
from twisted.python import log
from twisted.web.server import Site
from twisted.web.static import File

import json
import serial
import os
import urllib2
import webbrowser
import unicodecsv
import glob

import numpy
from cv2 import * # OpenCV imports
import psutil # CPU usage
import subprocess # ssocr command line calling
import re # Integers only from ssocr output


if getattr(sys, 'frozen', False):
    _applicationPath = os.path.dirname(sys.executable)
elif __file__:
    _applicationPath = os.path.dirname(__file__)

_settingsFilePath = os.path.join(_applicationPath, 'settings.ini')
_athleteDataFilePath = os.path.join(_applicationPath, 'athlete_data.csv')
_ssocrFilePath = os.path.join(_applicationPath, 'ssocr')
_GCcacheImageFilePath = os.path.join(_applicationPath, '_game_clock.jpg')
_SCcacheImageFilePath = os.path.join(_applicationPath, '_shot_clock.jpg')
_GCssocrProcessedFilePath = os.path.join(_applicationPath, '_GC_ssocr_processed.jpg')
_SCssocrProcessedFilePath = os.path.join(_applicationPath, '_SC_ssocr_processed.jpg')
_clock1FilePath = os.path.join(_applicationPath, 'clock_1.jpg')
_clock2FilePath = os.path.join(_applicationPath, 'clock_2.jpg')
_clock3FilePath = os.path.join(_applicationPath, 'clock_3.jpg')
_clock4FilePath = os.path.join(_applicationPath, 'clock_4.jpg')
_awayScoreFilePath = os.path.join(_applicationPath, '_away_score.jpg')
_homeScoreFilePath = os.path.join(_applicationPath, '_home_score.jpg')

print "ssocr path: " + _ssocrFilePath
print "Cache image path: " + _GCcacheImageFilePath

GroupBoxStyleSheet = u"QGroupBox { border: 1px solid #AAAAAA;margin-top: 12px;} QGroupBox::title {top: -5px;left: 10px;}"

class MainWindow(QtGui.QMainWindow):
	def __init__(self, parent=None):
		super(MainWindow, self).__init__(parent)

		######## QSettings #########
		self.qsettings = QSettings(_settingsFilePath, QSettings.IniFormat)
		self.qsettings.setFallbacksEnabled(False)

		######## ACTIONS ###########
		exitItem = QtGui.QAction('Exit', self)
		exitItem.setStatusTip('Exit application...')
		exitItem.triggered.connect(self.close)

		self.openChromaKeyDisplay = QtGui.QAction('Open Key Output for Vision Mixer', self)
		self.openChromaKeyDisplay.setStatusTip('Open chroma-key output display for the vision mixer...')
		self.openChromaKeyDisplay.triggered.connect(lambda: webbrowser.open_new("http://localhost:8080/"))
		######## END ACTIONS ###########


		menubar = self.menuBar()
		fileMenu = menubar.addMenu('&File')
		fileMenu.addAction(self.openChromaKeyDisplay)
		fileMenu.addSeparator()
		fileMenu.addAction(exitItem)


		self.main_widget = Window(self)
		self.setCentralWidget(self.main_widget)
		self.statusBar()
		self.setWindowTitle('Basketball OCR and Scoreboard Control')
		self.resize(300,400)
		self.show()


class Window(QtGui.QWidget):
	def __init__(self, parent):
		super(Window, self).__init__(parent)
		grid = QtGui.QGridLayout()
		self.qsettings = QSettings(_settingsFilePath, QSettings.IniFormat)
		self.qsettings.setFallbacksEnabled(False)

		self.updateScoreboard = QtGui.QPushButton("Update")
		self.updateScoreboard.clicked.connect(self.sendCommandToBrowser)

		self.teamAImagePath = QtGui.QLineEdit(u"")
		self.teamAColor = QtGui.QLineEdit(u"")
		self.teamAName = QtGui.QLineEdit(u"")
		#self.teamASelector = QtGui.QComboBox(self)
		self.teamBImagePath = QtGui.QLineEdit(u"")
		self.teamBName = QtGui.QLineEdit(u"")
		self.teamBColor = QtGui.QLineEdit(u"")
		#self.teamBSelector = QtGui.QComboBox(self)

		self.tickerRadioGroup = QtGui.QButtonGroup()
		self.tickerTextRadio = QtGui.QRadioButton("Text")
		self.tickerStatsRadio = QtGui.QRadioButton("Player Stats")
		self.tickerTextLineEdit = QtGui.QLineEdit(u"")
		self.tickerTeamSelector = QtGui.QComboBox(self)
		self.tickerPlayerSelector = QtGui.QComboBox(self)
		self.selectedPlayerMetadata = ''


		self.GCOCRCoordinates = {
			"clock_1": [QtGui.QLabel("Clock M1"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLineEdit(u"")],
			"clock_2": [QtGui.QLabel("Clock M2"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLineEdit(u"")],
			"clock_3": [QtGui.QLabel("Clock S1"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLineEdit(u"")],
			"clock_4": [QtGui.QLabel("Clock S2"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLineEdit(u"")],
			"home_score": [QtGui.QLabel("Home Score"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLineEdit(u"")],
			"away_score": [QtGui.QLabel("Away Score"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLineEdit(u"")],
			"colon_top": [QtGui.QLabel("Colon Top"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLineEdit(u"")],
			"blackout": [QtGui.QLabel("Blackout"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLineEdit(u"")]
		}
		self.ssocrArguments = QtGui.QLineEdit(self.qsettings.value("ssocrArguments", "crop 0 0 450 200 mirror horiz shear 10 mirror horiz gray_stretch 100 254 invert remove_isolated -T "))
		self.videoCaptureIndex = QtGui.QLineEdit(self.qsettings.value("videoCaptureIndex", '0'))
		self.waitKey = QtGui.QLineEdit(self.qsettings.value("waitKey", '300'))
		self.startOCRButton = QtGui.QPushButton("Start OCR")
		self.startOCRButton.clicked.connect(self.init_GCOCRWorker)
		self.terminateOCRButton = QtGui.QPushButton("Stop OCR")
		self.terminateOCRButton.clicked.connect(self.terminate_GCOCRWorker)

		self.SCOCRCoordinates = {
			"clock_1": [QtGui.QLabel("Clock 1"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLabel(u"")],
			"clock_2": [QtGui.QLabel("Clock 2"), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLineEdit(u""), QtGui.QLabel("0"), QtGui.QLabel("0"), QtGui.QLabel(u"")]
		}
		self.SCssocrArguments = QtGui.QLineEdit(self.qsettings.value("SCssocrArguments", "crop 0 0 450 200 mirror horiz shear 10 mirror horiz gray_stretch 100 254 invert remove_isolated -T "))
		self.SCvideoCaptureIndex = QtGui.QLineEdit(self.qsettings.value("SCvideoCaptureIndex", '0'))
		self.SCwaitKey = QtGui.QLineEdit(self.qsettings.value("SCwaitKey", '300'))
		self.startSCOCRButton = QtGui.QPushButton("Start OCR")
		self.startSCOCRButton.clicked.connect(self.init_SCOCRWorker)
		self.terminateSCOCRButton = QtGui.QPushButton("Stop OCR")
		self.terminateSCOCRButton.clicked.connect(self.terminate_SCOCRWorker)



		self.CPUpercentage = QtGui.QLabel("0 %")

		self.onAirStatsComboBoxes = [QtGui.QComboBox(self), QtGui.QComboBox(self), QtGui.QComboBox(self), QtGui.QComboBox(self), QtGui.QComboBox(self)]
		self.tickerTeamSelector.currentIndexChanged.connect(self.populatePlayersSelector)
		self.initializeStatisticsSelectors() # Populate self.tickerTeamSelector and self.onAirStatsComboBoxes
		self.initializeOCRCoordinatesList()
		self.initializeSC_OCRCoordinatesList()

		grid.addWidget(self.createTeamNameGroup(), 0, 0, 2, 1) # MUST BE HERE, initializes all QObject lists
		grid.addWidget(self.createTickerGraphicGroup(), 2, 0, 2, 1) # MUST BE HERE, initializes all QObject lists
		grid.addWidget(self.createStatSelectorGroup(), 4, 0, 2, 1) # MUST BE HERE, initializes all QObject lists
		grid.addWidget(self.createGC_OCR_Group(), 0, 1, 4, 1) # MUST BE HERE, initializes all QObject lists
		grid.addWidget(self.createSC_OCR_Group(), 0, 2, 2, 1) # MUST BE HERE, initializes all QObject lists
		grid.addWidget(self.createGC_SSOCR_Group(), 4, 1, 1, 1) # MUST BE HERE, initializes all QObject lists
		grid.addWidget(self.createSC_SSOCR_Group(), 2, 2, 1, 1) # MUST BE HERE, initializes all QObject lists
		grid.addWidget(self.createDebugGroup(), 6, 1, 1, 1) # MUST BE HERE, initializes all QObject lists
		grid.addWidget(self.updateScoreboard, 6, 0, 1, 1) # MUST BE HERE, initializes all QObject lists
		
		self.init_WebSocketsWorker() # Start ws:// server at port 9000
		#self.init_OCRWorker() # Start OpenCV, open webcam

		grid.setColumnStretch(0,5)
		grid.setColumnStretch(1,100)

		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(10)
		self.setLayout(grid)

	def initializeOCRCoordinatesList(self):
		_loadedGCOCRCoordinates = self.qsettings.value("OCRcoordinates")

		for key, param in self.GCOCRCoordinates.iteritems():
			for index, qobj in enumerate(param):
				qobj.setText(_loadedGCOCRCoordinates[key][index])

	def initializeSC_OCRCoordinatesList(self):
		_loadedSCOCRCoordinates = self.qsettings.value("SCOCRcoordinates")

		for key, param in self.SCOCRCoordinates.iteritems():
			for index, qobj in enumerate(param):
				qobj.setText(_loadedSCOCRCoordinates[key][index])

	def sendCommandToBrowser(self):
		msg = {
			'ticker': '',
			'guest': { 'name': '',
						'imagePath': '',
						'color': ''
			},
			'home': { 'name': '',
						'imagePath': '',
						'color': ''
			}
		}

		#msg['guest']['name'] = self.teamASelector.currentText()
		msg['guest']['name'] = self.teamAName.text()
		msg['guest']['imagePath'] = self.teamAImagePath.text()
		msg['guest']['color'] = self.teamAColor.text()
		#msg['home']['name'] = self.teamBSelector.currentText()
		msg['home']['name'] = self.teamBName.text()
		msg['home']['imagePath'] = self.teamBImagePath.text()
		msg['home']['color'] = self.teamBColor.text()


		if self.tickerRadioGroup.checkedId() == 0:
			msg["ticker"] = self.tickerTextLineEdit.text()

		if self.tickerRadioGroup.checkedId() == 1: # Player stats selected
			file_object = open('athlete_data.csv', 'rU')
			reader = unicodecsv.reader(file_object , delimiter=',', dialect='excel')

			statIndexes = []
			hrow = reader.next()

			for x, comboBox in enumerate(self.onAirStatsComboBoxes):
				try:
					index = hrow.index(self.onAirStatsComboBoxes[x].currentText())
				except ValueError: # No stat selected ("-")
					index = -1
				statIndexes.append({'index': index, 'statName': self.onAirStatsComboBoxes[x].currentText()})

			for row in reader:
				if(row[2] == self.tickerPlayerSelector.currentText()):
					for x in statIndexes:
						x["statText"] = row[x["index"]]

			msg["ticker"] = self.tickerTeamSelector.currentText() + " " + self.tickerPlayerSelector.currentText() + " - "
			for stat in statIndexes:
				if(stat["index"] != -1):
					msg["ticker"] += stat["statName"] + " " + stat["statText"] + " "

			file_object.close() # Close opened CSV file

		self.webSocketsWorker.send(json.dumps(msg));

	def sendRealTimeCommandToBrowser(self, recognizedDigits):
		msg_game = {
			"clock": recognizedDigits['clock'],
			"shot_clock": '',
			"quarter": recognizedDigits['quarter'],
			"possesion": ''
		}
		msg_guest = {
			"score": recognizedDigits['away_score'],
			"fouls": recognizedDigits['away_fouls']
		}
		msg_home = {
			"score": recognizedDigits['home_score'],
			"fouls": recognizedDigits['home_fouls']
		}

		packet = {
			"game": msg_game,
			"guest": msg_guest,
			"home": msg_home
		}

		self.webSocketsWorker.send(json.dumps(packet))

	def initializeStatisticsSelectors(self):
		file_object = open(_athleteDataFilePath, 'rU')
		reader = unicodecsv.reader(file_object , delimiter=',', dialect='excel')
		hrow = reader.next()

		unique_teams = []
		for row in reader:
			try:
				unique_teams.index(row[1])
			except ValueError: # If error is raised, means its not in unique list
				unique_teams.append(row[1])
				self.tickerTeamSelector.addItem(row[1])
				#self.teamASelector.addItem(row[1])
				#self.teamBSelector.addItem(row[1])

		for x, comboBox in enumerate(self.onAirStatsComboBoxes):
			self.onAirStatsComboBoxes[x].addItem("-")


		for header in hrow: # For loop through column headers
			for x, comboBox in enumerate(self.onAirStatsComboBoxes):
				self.onAirStatsComboBoxes[x].addItem(header)



		file_object.close()

	def populatePlayersSelector(self):
		file_object = open(_athleteDataFilePath, 'rU')
		reader = unicodecsv.reader(file_object , delimiter=',', dialect='excel')
		hrow = reader.next()

		self.tickerPlayerSelector.clear() # Empty team ComboBox

		for row in reader:
			if(row[1] == self.tickerTeamSelector.currentText()):
				self.tickerPlayerSelector.addItem(row[2]) # Add name to player selector comboBox

		file_object.close()

	def init_WebSocketsWorker(self):
		self.webSocketsWorker = WebSocketsWorker()
		self.webSocketsWorker.error.connect(self.close)
		self.webSocketsWorker.start()# Call to start WebSockets server

	def init_GCOCRWorker(self):
		self.GCOCRWorker = GCOCRWorker(self.returnOCRCoordinatesList(), self.ssocrArguments.text(), self.waitKey.text(), self.videoCaptureIndex.text())
		self.GCOCRWorker.error.connect(self.close)
		self.GCOCRWorker.recognizedDigits.connect(self.GCOCRhandler)
		self.GCOCRWorker.processedFrameFlag.connect(lambda: self.CPUpercentage.setText('CPU: ' + str(psutil.cpu_percent()) + "%"))
		self.GCOCRWorker.start() # Call to start OCR openCV thread

	def init_SCOCRWorker(self):
		self.SCOCRWorker = SCOCRWorker(self.returnSCOCRCoordinatesList(), self.SCssocrArguments.text(), self.SCwaitKey.text(), self.SCvideoCaptureIndex.text())
		self.SCOCRWorker.error.connect(self.close)
		self.SCOCRWorker.recognizedDigits.connect(self.SCOCRhandler)
		self.SCOCRWorker.processedFrameFlag.connect(lambda: self.CPUpercentage.setText('CPU: ' + str(psutil.cpu_percent()) + "%"))
		self.SCOCRWorker.start() # Call to start OCR openCV thread

	def terminate_GCOCRWorker(self):
		self.GCOCRWorker.kill()
		del(self.GCOCRWorker)

	def terminate_SCOCRWorker(self):
		self.SCOCRWorker.kill()
		del(self.SCOCRWorker)

	def GCOCRhandler(self, rx): # Receives [str(clock_1), str(clock_2), str(clock_3), str(clock_4), str(home_score), str(away_score), formatted_clock]
		print rx
		self.GCOCRCoordinates["clock_1"][7].setText(rx[0])
		self.GCOCRCoordinates["clock_2"][7].setText(rx[1])
		self.GCOCRCoordinates["clock_3"][7].setText(rx[2])
		self.GCOCRCoordinates["clock_4"][7].setText(rx[3])
		self.GCOCRCoordinates["home_score"][7].setText(rx[4])
		self.GCOCRCoordinates["away_score"][7].setText(rx[5])
	
	def SCOCRhandler(self, digitList): # Receives [self.digitL, self.digitR] from SCOCRWorker
		print digitList
		self.SCOCRCoordinates["clock_1"][7].setText(digitList[0])
		self.SCOCRCoordinates["clock_2"][7].setText(digitList[1])

	def returnOCRCoordinatesList(self): # Returns 1:1 copy of self.GCOCRCoordinates without QObjects
		response = {
			"clock_1": ["", "", "", "", "", "", "", ""],
			"clock_2": ["", "", "", "", "", "", "", ""],
			"clock_3": ["", "", "", "", "", "", "", ""],
			"clock_4": ["", "", "", "", "", "", "", ""],
			"home_score": ["", "", "", "", "", "", "", ""],
			"away_score": ["", "", "", "", "", "", "", ""],
			"colon_top": ["", "", "", "", "", "", "", ""],
			"blackout": ["", "", "", "", "", "", "", ""]
		}
		for key, param in self.GCOCRCoordinates.iteritems():
			for index, qobj in enumerate(param):
				response[key][index] = qobj.text()

		return response

	def returnSCOCRCoordinatesList(self): # Returns 1:1 copy of self.GCOCRCoordinates without QObjects
		response = {
			"clock_1": ["", "", "", "", "", "", "", ""],
			"clock_2": ["", "", "", "", "", "", "", ""]
		}
		for key, param in self.SCOCRCoordinates.iteritems():
			for index, qobj in enumerate(param):
				response[key][index] = qobj.text()

		return response
		
	def createTickerGraphicGroup(self):
		groupBox = QtGui.QGroupBox("Ticker")
		groupBox.setStyleSheet(GroupBoxStyleSheet)

		self.tickerRadioGroup.setExclusive(True)
		self.tickerRadioGroup.addButton(self.tickerTextRadio, 0)
		self.tickerRadioGroup.addButton(self.tickerStatsRadio, 1)
		self.tickerRadioGroup.button(0).setChecked(True)

		grid = QtGui.QGridLayout()
		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(10)
		grid.addWidget(self.tickerTextRadio, 0, 0)
		grid.addWidget(self.tickerTextLineEdit, 1, 0, 1, 2)
		grid.addWidget(self.tickerStatsRadio, 2, 0)
		grid.addWidget(self.tickerTeamSelector, 3, 0)
		grid.addWidget(self.tickerPlayerSelector, 3, 1)

		groupBox.setLayout(grid)
		return groupBox

	def createStatSelectorGroup(self):
		groupBox = QtGui.QGroupBox("On Air Statistics")
		groupBox.setStyleSheet(GroupBoxStyleSheet)

		grid = QtGui.QGridLayout()
		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(5)

		for x, comboBox in enumerate(self.onAirStatsComboBoxes):
			grid.addWidget(QtGui.QLabel(str(x+1) + ":"), x, 0)
			grid.addWidget(self.onAirStatsComboBoxes[x], x, 1)

		grid.setColumnStretch(0,5)
		grid.setColumnStretch(1,100)
		groupBox.setLayout(grid)
		return groupBox

	def createTeamNameGroup(self):
		groupBox = QtGui.QGroupBox("Teams")
		groupBox.setStyleSheet(GroupBoxStyleSheet)

		grid = QtGui.QGridLayout()
		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(5)

		grid.addWidget(QtGui.QLabel("Name"), 0, 1)
		grid.addWidget(QtGui.QLabel("Image URL"), 0, 2)
		grid.addWidget(QtGui.QLabel("Color #Hex "), 0, 3)
		grid.addWidget(QtGui.QLabel("Guest"), 1, 0)
		#grid.addWidget(self.teamASelector, 1, 1)
		grid.addWidget(self.teamAName, 1, 1)
		grid.addWidget(self.teamAImagePath, 1, 2)
		grid.addWidget(self.teamAColor, 1, 3)
		grid.addWidget(QtGui.QLabel("Home"), 2, 0)
		#grid.addWidget(self.teamBSelector, 2, 1)
		grid.addWidget(self.teamBName, 2, 1)
		grid.addWidget(self.teamBImagePath, 2, 2)
		grid.addWidget(self.teamBColor, 2, 3)

		grid.setColumnStretch(0,5)
		grid.setColumnStretch(1,100)
		groupBox.setLayout(grid)
		return groupBox

	def widthHeightAutoFiller(self): # Calculates width and height, then saves to settings.ini file
		for key, value in self.GCOCRCoordinates.iteritems():
			tl_X = int('0' + value[1].text()) # '0' to avoid int('') empty string error
			tl_Y = int('0' + value[2].text())
			br_X = int('0' + value[3].text())
			br_Y = int('0' + value[4].text())
			value[5].setText(str(br_X - tl_X))
			value[6].setText(str(br_Y - tl_Y))

		for key, value in self.SCOCRCoordinates.iteritems():
			tl_X = int('0' + value[1].text()) # '0' to avoid int('') empty string error
			tl_Y = int('0' + value[2].text())
			br_X = int('0' + value[3].text())
			br_Y = int('0' + value[4].text())
			value[5].setText(str(br_X - tl_X))
			value[6].setText(str(br_Y - tl_Y))

		self.qsettings.setValue("SCOCRcoordinates", self.returnSCOCRCoordinatesList())
		self.qsettings.setValue("OCRcoordinates", self.returnOCRCoordinatesList())
		self.qsettings.setValue("ssocrArguments", self.ssocrArguments.text())
		self.qsettings.setValue("waitKey", self.waitKey.text())
		self.qsettings.setValue("videoCaptureIndex", self.videoCaptureIndex.text())
		self.qsettings.setValue("SCssocrArguments", self.SCssocrArguments.text())
		self.qsettings.setValue("SCwaitKey", self.SCwaitKey.text())
		self.qsettings.setValue("SCvideoCaptureIndex", self.SCvideoCaptureIndex.text())

		try:
			self.GCOCRWorker.importOCRCoordinates(self.returnOCRCoordinatesList())
			self.GCOCRWorker.ssocrArguments = self.ssocrArguments.text()
			self.GCOCRWorker.waitKey = self.waitKey.text()
		except:
			pass
		try:
			self.SCOCRWorker.importOCRCoordinates(self.returnSCOCRCoordinatesList())
			self.SCOCRWorker.ssocrArguments = self.SCssocrArguments.text()
			self.SCOCRWorker.waitKey = self.SCwaitKey.text()
		except:
			pass

	def createGC_OCR_Group(self):
		groupBox = QtGui.QGroupBox("Game Clock OCR")
		groupBox.setStyleSheet(GroupBoxStyleSheet)

		grid = QtGui.QGridLayout()
		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(5)

		_tlLabel = QtGui.QLabel("Top-Left")
		_brLabel = QtGui.QLabel("Bottom-Right")
		_tlLabel.setAlignment(Qt.AlignCenter)
		_brLabel.setAlignment(Qt.AlignCenter)
		grid.addWidget(_tlLabel, 0, 1, 1, 2)
		grid.addWidget(_brLabel, 0, 3, 1, 2)

		grid.addWidget(QtGui.QLabel(""), 1, 0)
		grid.addWidget(QtGui.QLabel("X"), 1, 1)
		grid.addWidget(QtGui.QLabel("Y"), 1, 2)
		grid.addWidget(QtGui.QLabel("X"), 1, 3)
		grid.addWidget(QtGui.QLabel("Y"), 1, 4)
		grid.addWidget(QtGui.QLabel("Width"), 1, 5)
		grid.addWidget(QtGui.QLabel("Height"), 1,6)
		grid.addWidget(QtGui.QLabel("Manual"), 1,7)

		for key, param in self.GCOCRCoordinates.iteritems(): # Right justify parameter QLabels
			param[0].setAlignment(Qt.AlignRight)
			param[1].setValidator(QIntValidator()) # Require integer pixel input
			param[2].setValidator(QIntValidator())
			param[3].setValidator(QIntValidator())
			param[4].setValidator(QIntValidator())
			param[1].setMaxLength(3) # Set 3 digit maximum for pixel coordinates
			param[2].setMaxLength(3)
			param[3].setMaxLength(3)
			param[4].setMaxLength(3)
			param[1].editingFinished.connect(self.widthHeightAutoFiller) # On change in X or Y, update width + height
			param[2].editingFinished.connect(self.widthHeightAutoFiller)
			param[3].editingFinished.connect(self.widthHeightAutoFiller)
			param[4].editingFinished.connect(self.widthHeightAutoFiller)
			param[7].editingFinished.connect(self.widthHeightAutoFiller)
			param[5].setAlignment(Qt.AlignCenter)
			param[6].setAlignment(Qt.AlignCenter)



		for index, qobj in enumerate(self.GCOCRCoordinates["clock_1"]):
			grid.addWidget(qobj, 2, index)
		for index, qobj in enumerate(self.GCOCRCoordinates["clock_2"]):
			grid.addWidget(qobj, 3, index)
		for index, qobj in enumerate(self.GCOCRCoordinates["clock_3"]):
			grid.addWidget(qobj, 4, index)
		for index, qobj in enumerate(self.GCOCRCoordinates["clock_4"]):
			grid.addWidget(qobj, 5, index)
		for index, qobj in enumerate(self.GCOCRCoordinates["home_score"]):
			grid.addWidget(qobj, 7, index)
		for index, qobj in enumerate(self.GCOCRCoordinates["away_score"]):
			grid.addWidget(qobj, 8, index)
		for index, qobj in enumerate(self.GCOCRCoordinates["colon_top"]):
			grid.addWidget(qobj, 10, index)
		for index, qobj in enumerate(self.GCOCRCoordinates["blackout"]):
			grid.addWidget(qobj, 11, index)


		grid.setColumnMinimumWidth(1, 30)
		grid.setColumnMinimumWidth(2, 30)
		grid.setColumnMinimumWidth(3, 30)
		grid.setColumnMinimumWidth(4, 30)

		groupBox.setLayout(grid)
		return groupBox

	def createGC_SSOCR_Group(self):
		groupBox = QtGui.QGroupBox("Game Clock Parameters")
		groupBox.setStyleSheet(GroupBoxStyleSheet)

		grid = QtGui.QGridLayout()
		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(5)

		grid.addWidget(QtGui.QLabel("SSOCR Arguments"), 0, 0, 1, 3)
		grid.addWidget(QtGui.QLabel("WaitKey"), 2, 0)
		grid.addWidget(QtGui.QLabel("Webcam Index"), 2, 1)
		grid.addWidget(self.ssocrArguments, 1, 0, 1, 4)
		grid.addWidget(self.waitKey, 3, 0)
		grid.addWidget(self.videoCaptureIndex, 3, 1)
		grid.addWidget(self.startOCRButton, 3, 2)
		grid.addWidget(self.terminateOCRButton, 3, 3)

		self.ssocrArguments.editingFinished.connect(self.widthHeightAutoFiller)
		self.waitKey.editingFinished.connect(self.widthHeightAutoFiller)
		self.videoCaptureIndex.editingFinished.connect(self.widthHeightAutoFiller)

		grid.setColumnStretch(0,50)
		grid.setColumnStretch(1,25)
		grid.setColumnStretch(2,25)
		groupBox.setLayout(grid)
		return groupBox

	def createSC_OCR_Group(self):
		groupBox = QtGui.QGroupBox("Shot Clock OCR")
		groupBox.setStyleSheet(GroupBoxStyleSheet)

		grid = QtGui.QGridLayout()
		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(5)

		_tlLabel = QtGui.QLabel("Top-Left")
		_brLabel = QtGui.QLabel("Bottom-Right")
		_tlLabel.setAlignment(Qt.AlignCenter)
		_brLabel.setAlignment(Qt.AlignCenter)
		grid.addWidget(_tlLabel, 0, 1, 1, 2)
		grid.addWidget(_brLabel, 0, 3, 1, 2)

		grid.addWidget(QtGui.QLabel(""), 1, 0)
		grid.addWidget(QtGui.QLabel("X"), 1, 1)
		grid.addWidget(QtGui.QLabel("Y"), 1, 2)
		grid.addWidget(QtGui.QLabel("X"), 1, 3)
		grid.addWidget(QtGui.QLabel("Y"), 1, 4)
		grid.addWidget(QtGui.QLabel("Width"), 1, 5)
		grid.addWidget(QtGui.QLabel("Height"), 1,6)
		grid.addWidget(QtGui.QLabel("Recognized"), 1,7)

		for key, param in self.SCOCRCoordinates.iteritems(): # Right justify parameter QLabels
			param[0].setAlignment(Qt.AlignRight)
			param[1].setValidator(QIntValidator()) # Require integer pixel input
			param[2].setValidator(QIntValidator())
			param[3].setValidator(QIntValidator())
			param[4].setValidator(QIntValidator())
			param[1].setMaxLength(3) # Set 3 digit maximum for pixel coordinates
			param[2].setMaxLength(3)
			param[3].setMaxLength(3)
			param[4].setMaxLength(3)
			param[1].editingFinished.connect(self.widthHeightAutoFiller) # On change in X or Y, update width + height
			param[2].editingFinished.connect(self.widthHeightAutoFiller)
			param[3].editingFinished.connect(self.widthHeightAutoFiller)
			param[4].editingFinished.connect(self.widthHeightAutoFiller)
			param[5].setAlignment(Qt.AlignCenter)
			param[6].setAlignment(Qt.AlignCenter)



		for index, qobj in enumerate(self.SCOCRCoordinates["clock_1"]):
			grid.addWidget(qobj, 2, index)
		for index, qobj in enumerate(self.SCOCRCoordinates["clock_2"]):
			grid.addWidget(qobj, 3, index)


		grid.setColumnMinimumWidth(1, 30)
		grid.setColumnMinimumWidth(2, 30)
		grid.setColumnMinimumWidth(3, 30)
		grid.setColumnMinimumWidth(4, 30)

		groupBox.setLayout(grid)
		return groupBox


	def createSC_SSOCR_Group(self):
		groupBox = QtGui.QGroupBox("Shot Clock Parameters")
		groupBox.setStyleSheet(GroupBoxStyleSheet)

		grid = QtGui.QGridLayout()
		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(5)

		grid.addWidget(QtGui.QLabel("SSOCR Arguments"), 0, 0, 1, 3)
		grid.addWidget(QtGui.QLabel("WaitKey"), 2, 0)
		grid.addWidget(QtGui.QLabel("Webcam Index"), 2, 1)
		grid.addWidget(self.SCssocrArguments, 1, 0, 1, 4)
		grid.addWidget(self.SCwaitKey, 3, 0)
		grid.addWidget(self.SCvideoCaptureIndex, 3, 1)
		grid.addWidget(self.startSCOCRButton, 3, 2)
		grid.addWidget(self.terminateSCOCRButton, 3, 3)

		self.SCssocrArguments.editingFinished.connect(self.widthHeightAutoFiller)
		self.SCwaitKey.editingFinished.connect(self.widthHeightAutoFiller)
		self.SCvideoCaptureIndex.editingFinished.connect(self.widthHeightAutoFiller)

		grid.setColumnStretch(0,50)
		grid.setColumnStretch(1,25)
		grid.setColumnStretch(2,25)
		groupBox.setLayout(grid)
		return groupBox




	def createDebugGroup(self):
		groupBox = QtGui.QGroupBox("Debug")
		groupBox.setStyleSheet(GroupBoxStyleSheet)

		grid = QtGui.QGridLayout()
		grid.setHorizontalSpacing(10)
		grid.setVerticalSpacing(5)

		grid.addWidget(self.CPUpercentage, 0, 0)
		#grid.addWidget(self.terminateOCRButton, 0, 1)

		groupBox.setLayout(grid)
		return groupBox




class WebSocketsWorker(QtCore.QThread):
	updateProgress = QtCore.Signal(list)
	error = QtCore.Signal(str)
	socket_opened = QtCore.Signal(int)

	class BroadcastServerProtocol(WebSocketServerProtocol):
		def onOpen(self):
			self.factory.register(self)

		def onMessage(self, payload, isBinary):
			if not isBinary:
				msg = "{} from {}".format(payload.decode('utf8'), self.peer)
				self.factory.broadcast(msg)

		def connectionLost(self, reason):
			WebSocketServerProtocol.connectionLost(self, reason)
			self.factory.unregister(self)

	class BroadcastServerFactory(WebSocketServerFactory):
		def __init__(self, url, debug=False, debugCodePaths=False):
			WebSocketServerFactory.__init__(self, url, debug=debug, debugCodePaths=debugCodePaths)
			self.clients = []
			self.tickcount = 0
			#self.tick()

		def tick(self):
			self.tickcount += 1
			self.broadcast("tick %d from server" % self.tickcount)
			reactor.callLater(0.5, self.tick)

		def register(self, client):
			if client not in self.clients:
				print("registered client {}".format(client.peer))
				self.clients.append(client)

		def unregister(self, client):
			if client in self.clients:
				print("unregistered client {}".format(client.peer))
				self.clients.remove(client)

		def broadcast(self, msg):
			#print("broadcasting message '{}' ..".format(msg))
			for c in self.clients:
				c.sendMessage(msg.encode('utf8'))
				#print("message {} sent to {}".format(msg, c.peer))

		def returnClients(self):
			return
			#for c in self.clients:
				#print(c.peer)


	def __init__(self):
		QtCore.QThread.__init__(self)
		self.factory = self.BroadcastServerFactory("ws://localhost:9000", debug=False, debugCodePaths=False)

	def run(self):
		self.factory.protocol = self.BroadcastServerProtocol
		try:
			listenWS(self.factory)
		except:
			self.error.emit("Fail")
		webdir = File(_applicationPath)
		webdir.indexNames = ['index.php', 'index.html']
		web = Site(webdir)
		try:
			reactor.listenTCP(8080, web)
			self.socket_opened.emit(1)
		except: 
			self.error.emit("Fail")
		reactor.run(installSignalHandlers=0)

	def send(self, data):
		reactor.callFromThread(self.factory.broadcast, data)
		self.updateProgress.emit([self.factory.returnClients()])

class GCOCRWorker(QtCore.QThread):
	error = QtCore.Signal(int)
	recognizedDigits = QtCore.Signal(list)

	colonMean = QtCore.Signal(str)
	processedFrameFlag = QtCore.Signal(int)


	def __init__(self, OCRCoordinatesList, ssocrArguments, waitKey, videoCaptureIndex):
		QtCore.QThread.__init__(self)

		self.ssocrArguments = ssocrArguments
		self.waitKey = waitKey
		self.coords = OCRCoordinatesList
		self.videoCaptureIndex = videoCaptureIndex
		self._allowedNextDigits = {
			"clock_1": [9, 0, 1, 2, 3, 4, 5, 6, 7, 8], 
			"clock_2": [9, 0, 1, 2, 3, 4, 5, 6, 7, 8], 
			"clock_3": [5, 0, 1, 2, 3, 4, 5, 6, 7, 8], 
			"clock_4": [9, 0, 1, 2, 3, 4, 5, 6, 7, 8]
			}
		self.FIFO_clocks = {
			"clock_1": [0, 0, 0], 
			"clock_2": [0, 0, 0], 
			"clock_3": [0, 0, 0], 
			"clock_4": [0, 0, 0]
			}
		self.FIFO_scores = {
			"home": [0, 0, 0, 0, 0, 0, 0], 
			"away": [0, 0, 0, 0, 0, 0, 0]
			}

		self.previousDigit = {
			"clock_1": 0, 
			"clock_2": 0, 
			"clock_3": 0, 
			"clock_4": 0
			}

		self.mouse_coordinates = [0, 0]
		self.cam = None # VideoCapture object, created in run()

	def mouse_hover_coordinates(self, event, x, y, flags, param):
		if event == EVENT_MOUSEMOVE:
			self.mouse_coordinates = [x, y]

	def importOCRCoordinates(self, OCRCoordinatesList):
		self.coords = OCRCoordinatesList

	def cleanInt(self, dirtyInteger, numDigits):
		return int(str('00' + re.sub("[^0-9]", "", dirtyInteger))[-numDigits:])

	def kill(self):
		destroyAllWindows()
		self.terminate()

	def run(self):
		print "GCOCRWorker QThread successfully opened."

		try:
			self.cam = VideoCapture(int(self.videoCaptureIndex))   # 0 -> index of camera
			#self.cam = VideoCapture('test_images/test_video_flip.mov')   # 0 -> index of camera
			
			print "Webcam native resolution: ",
			print self.cam.get(cv.CV_CAP_PROP_FRAME_WIDTH), self.cam.get(cv.CV_CAP_PROP_FRAME_HEIGHT)

			self.cam.set(cv.CV_CAP_PROP_FRAME_WIDTH, 640)
			self.cam.set(cv.CV_CAP_PROP_FRAME_HEIGHT, 480)

			namedWindow("GC OCR Webcam", CV_WINDOW_AUTOSIZE)
			namedWindow("GC SSOCR", CV_WINDOW_AUTOSIZE)
			moveWindow("GC OCR Webcam", 0, 10)
			moveWindow("GC SSOCR", 600, 10)
			setMouseCallback("GC SSOCR", self.mouse_hover_coordinates)

			while True:
				#img = imread('test_images/tpe_gym_test.jpg'); success = True
				success, img = self.cam.read()

				if success:
					##### SAVE GRABBED WEBCAM IMAGE WITH BLACKOUT OVERLAY ######
					rectangle(img, (int('0' + self.coords["blackout"][1]), int('0' + self.coords["blackout"][2])), (int('0' + self.coords["blackout"][3]), int('0' + self.coords["blackout"][4])), (0,0,0), -1)
					imwrite(_GCcacheImageFilePath, img)
					imshow("GC OCR Webcam", img)

					##### RUN PRELIMINARY IMAGE PROCESSING #####
					_command = _ssocrFilePath + ' ' + self.ssocrArguments + ' ' + _GCcacheImageFilePath + ' -p -o ' + _GCssocrProcessedFilePath
					preprocessing = subprocess.Popen(_command, stdout=subprocess.PIPE, shell=True)

					##### SHOW PRELIMINARY PROCESSED IMAGE WITH BOUNDING BOXES, X, Y #####
					ssocr_img = imread(_GCssocrProcessedFilePath)
					putText(ssocr_img, str(self.mouse_coordinates[0]) + ", " + str(self.mouse_coordinates[1]), (5, 15), FONT_ITALIC, 0.4, (0,0,0))
					rectangle(ssocr_img, (int('0' + self.coords["clock_1"][1]), int('0' + self.coords["clock_1"][2])), (int('0' + self.coords["clock_1"][3]), int('0' + self.coords["clock_1"][4])), (0,0,255), 1)
					rectangle(ssocr_img, (int('0' + self.coords["clock_2"][1]), int('0' + self.coords["clock_2"][2])), (int('0' + self.coords["clock_2"][3]), int('0' + self.coords["clock_2"][4])), (0,0,255), 1)
					rectangle(ssocr_img, (int('0' + self.coords["clock_3"][1]), int('0' + self.coords["clock_3"][2])), (int('0' + self.coords["clock_3"][3]), int('0' + self.coords["clock_3"][4])), (0,0,255), 1)
					rectangle(ssocr_img, (int('0' + self.coords["clock_4"][1]), int('0' + self.coords["clock_4"][2])), (int('0' + self.coords["clock_4"][3]), int('0' + self.coords["clock_4"][4])), (0,0,255), 1)
					rectangle(ssocr_img, (int('0' + self.coords["home_score"][1]), int('0' + self.coords["home_score"][2])), (int('0' + self.coords["home_score"][3]), int('0' + self.coords["home_score"][4])), (0,0,255), 1)
					rectangle(ssocr_img, (int('0' + self.coords["away_score"][1]), int('0' + self.coords["away_score"][2])), (int('0' + self.coords["away_score"][3]), int('0' + self.coords["away_score"][4])), (0,0,255), 1)
					rectangle(ssocr_img, (int('0' + self.coords["colon_top"][1]), int('0' + self.coords["colon_top"][2])), (int('0' + self.coords["colon_top"][3]), int('0' + self.coords["colon_top"][4])), (0,0,255), 1)
					imshow("GC SSOCR", ssocr_img)

					##### RECOGNIZE INDIVIDUAL CLOCK DIGITS, SHOW IN WINDOWS #####
					_command = _ssocrFilePath + ' crop ' + self.coords["clock_1"][1] + ' ' + self.coords["clock_1"][2] + ' ' + self.coords["clock_1"][5] + ' ' + self.coords["clock_1"][6] + ' ' + _GCssocrProcessedFilePath + ' -d -1 --debug-image=' + _clock1FilePath
					_clock_1 = subprocess.Popen(_command, stdout=subprocess.PIPE, shell=True)
					_command = _ssocrFilePath + ' crop ' + self.coords["clock_2"][1] + ' ' + self.coords["clock_2"][2] + ' ' + self.coords["clock_2"][5] + ' ' + self.coords["clock_2"][6] + ' ' + _GCssocrProcessedFilePath + ' -d -1 --debug-image=' + _clock2FilePath
					_clock_2 = subprocess.Popen(_command, stdout=subprocess.PIPE, shell=True)
					_command = _ssocrFilePath + ' crop ' + self.coords["clock_3"][1] + ' ' + self.coords["clock_3"][2] + ' ' + self.coords["clock_3"][5] + ' ' + self.coords["clock_3"][6] + ' ' + _GCssocrProcessedFilePath + ' -d -1 --debug-image=' + _clock3FilePath
					_clock_3 = subprocess.Popen(_command, stdout=subprocess.PIPE, shell=True)
					_command = _ssocrFilePath + ' crop ' + self.coords["clock_4"][1] + ' ' + self.coords["clock_4"][2] + ' ' + self.coords["clock_4"][5] + ' ' + self.coords["clock_4"][6] + ' ' + _GCssocrProcessedFilePath + ' -d -1 --debug-image=' + _clock4FilePath
					_clock_4 = subprocess.Popen(_command, stdout=subprocess.PIPE, shell=True)
					_command = _ssocrFilePath + ' crop ' + self.coords["home_score"][1] + ' ' + self.coords["home_score"][2] + ' ' + self.coords["home_score"][5] + ' ' + self.coords["home_score"][6] + ' ' + _GCssocrProcessedFilePath + ' -d -1 --debug-image=' + _homeScoreFilePath
					_home_score = subprocess.Popen(_command, stdout=subprocess.PIPE, shell=True)
					_command = _ssocrFilePath + ' crop ' + self.coords["away_score"][1] + ' ' + self.coords["away_score"][2] + ' ' + self.coords["away_score"][5] + ' ' + self.coords["away_score"][6] + ' ' + _GCssocrProcessedFilePath + ' -d -1 --debug-image=' + _awayScoreFilePath
					_away_score = subprocess.Popen(_command, stdout=subprocess.PIPE, shell=True)

					clock_1 = self.cleanInt(_clock_1.stdout.read(), 1)
					clock_2 = self.cleanInt(_clock_2.stdout.read(), 1)
					clock_3 = self.cleanInt(_clock_3.stdout.read(), 1)
					clock_4 = self.cleanInt(_clock_4.stdout.read(), 1)
					home_score = self.cleanInt(_home_score.stdout.read(), 3)
					away_score = self.cleanInt(_away_score.stdout.read(), 3)

					##### FILTER ALGORITHM #####
					print "Raw:\t\t", clock_1, clock_2, clock_3, clock_4, home_score, away_score

					self.FIFO_clocks['clock_1'].append(clock_1)
					self.FIFO_clocks['clock_1'].pop(0)
					self.FIFO_clocks['clock_2'].append(clock_2)
					self.FIFO_clocks['clock_2'].pop(0)
					self.FIFO_clocks['clock_3'].append(clock_3)
					self.FIFO_clocks['clock_3'].pop(0)
					self.FIFO_clocks['clock_4'].append(clock_4)
					self.FIFO_clocks['clock_4'].pop(0)
					self.FIFO_scores['home'].append(home_score)
					self.FIFO_scores['home'].pop(0)
					self.FIFO_scores['away'].append(away_score)
					self.FIFO_scores['away'].pop(0)

					print "Clock 1 FIFO:", self.FIFO_clocks['clock_1']
					print "Clock 2 FIFO:", self.FIFO_clocks['clock_2']
					print "Clock 3 FIFO:", self.FIFO_clocks['clock_3']
					print "Clock 4 FIFO:", self.FIFO_clocks['clock_4']
					print "Score Home FIFO:", self.FIFO_scores['home']
					print "Score Away FIFO:", self.FIFO_scores['away']


					if(self.FIFO_clocks['clock_1'][2] == self._allowedNextDigits["clock_1"][self.FIFO_clocks['clock_1'][1]]):
						clock_1 = self.FIFO_clocks['clock_1'][2]
					else: clock_1 = sorted(self.FIFO_clocks['clock_1'], key=self.FIFO_clocks['clock_1'].count)[-1]

					if(self.FIFO_clocks['clock_2'][2] == self._allowedNextDigits["clock_2"][self.FIFO_clocks['clock_2'][1]]):
						clock_2 = self.FIFO_clocks['clock_2'][2]
					else: clock_2 = sorted(self.FIFO_clocks['clock_2'], key=self.FIFO_clocks['clock_2'].count)[-1]

					if(self.FIFO_clocks['clock_3'][2] == self._allowedNextDigits["clock_3"][self.FIFO_clocks['clock_3'][1]]):
						clock_3 = self.FIFO_clocks['clock_3'][2]
					else: clock_3 = sorted(self.FIFO_clocks['clock_3'], key=self.FIFO_clocks['clock_3'].count)[-1]

					if(self.FIFO_clocks['clock_4'][2] == self._allowedNextDigits["clock_4"][self.FIFO_clocks['clock_4'][1]]):
						clock_4 = self.FIFO_clocks['clock_4'][2]
					else: clock_4 = sorted(self.FIFO_clocks['clock_4'], key=self.FIFO_clocks['clock_4'].count)[-1]

					home_score = sorted(self.FIFO_scores['home'], key=self.FIFO_scores['home'].count)[-1]
					away_score = sorted(self.FIFO_scores['away'], key=self.FIFO_scores['away'].count)[-1]

					print "Filtered:\t", clock_1, clock_2, clock_3, clock_4, home_score, away_score

					##### COLON PROCESSING #####
					colon_top_cropped = ssocr_img[int('0' + self.coords["colon_top"][2]):int('0' + self.coords["colon_top"][4]), int('0' + self.coords["colon_top"][1]):int('0' + self.coords["colon_top"][3])]

					##### TEXTUAL FORMATTING ######
					_minutes = str(int('0' + str(clock_1) + str(clock_2)))
					_seconds = str(int('0' + str(clock_3) + str(clock_4)))
					if(len(_seconds) == 1): _seconds = '0' + _seconds
					formatted_clock = _minutes + ":" + _seconds
					
					print formatted_clock
					print ""
					waitKey(int(self.waitKey))
			 		self.processedFrameFlag.emit(1)
			 		self.colonMean.emit(str(int(mean(threshold(colon_top_cropped, 100, 255, THRESH_BINARY)[1])[1])))
			 		self.recognizedDigits.emit([str(clock_1), str(clock_2), str(clock_3), str(clock_4), str(home_score), str(away_score), formatted_clock])

		except:
			self.error.emit(1)



class SCOCRWorker(QtCore.QThread):
	error = QtCore.Signal(int)
	recognizedDigits = QtCore.Signal(list)
	processedFrameFlag = QtCore.Signal(int)

	def __init__(self, OCRCoordinatesList, ssocrArguments, waitKey, videoCaptureIndex):
		QtCore.QThread.__init__(self)

		self.ssocrArguments = ssocrArguments
		self.waitKey = waitKey
		self.coords = OCRCoordinatesList
		self.videoCaptureIndex = videoCaptureIndex
		self.mouse_coordinates = [0, 0]
		self.referenceDigits = None
		self.cam = None # VideoCapture object, created in run()
		
		self.loadReferenceMatrices()
		self.digitL = ''
		self.digitR = ''


	def mouse_hover_coordinates(self, event, x, y, flags, param):
		if event == EVENT_MOUSEMOVE:
			self.mouse_coordinates = [x, y]

	def loadReferenceMatrices(self):
		self.referenceDigits = [
		[imread(os.path.join(_applicationPath, 'ref_digits/0A.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/1A.png'), 0), imread(os.path.join(_applicationPath, 'ref_digits/1B.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/2A.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/3A.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/4A.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/5A.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/6A.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/7A.png'), 0), imread(os.path.join(_applicationPath, 'ref_digits/7B.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/8A.png'), 0)],
		[imread(os.path.join(_applicationPath, 'ref_digits/9A.png'), 0)]
		]

	def importOCRCoordinates(self, OCRCoordinatesList):
		self.coords = OCRCoordinatesList

	def kill(self):
		self.terminate()

	def run(self):
		try:
			self.cam = VideoCapture(int(self.videoCaptureIndex))   # 0 -> index of camera
			#self.cam = VideoCapture('test_images/shot_clock_test.mov')   # 0 -> index of camera
			
			print "Webcam native resolution: ",
			print self.cam.get(cv.CV_CAP_PROP_FRAME_WIDTH), self.cam.get(cv.CV_CAP_PROP_FRAME_HEIGHT)

			self.cam.set(cv.CV_CAP_PROP_FRAME_WIDTH, 320)
			self.cam.set(cv.CV_CAP_PROP_FRAME_HEIGHT, 240)

			namedWindow("Shot Clock OCR Webcam", CV_WINDOW_AUTOSIZE)
			namedWindow("Shot Clock SSOCR", CV_WINDOW_AUTOSIZE)
			namedWindow("Digit 1", CV_WINDOW_AUTOSIZE)
			namedWindow("Digit 2", CV_WINDOW_AUTOSIZE)

			moveWindow("Shot Clock OCR Webcam", 0, 10)
			moveWindow("Shot Clock SSOCR", 800, 0)
			moveWindow("Digit 1", 600, 0)
			moveWindow("Digit 2", 660, 0)

			setMouseCallback("Shot Clock SSOCR", self.mouse_hover_coordinates)

			while True:
				success, img = self.cam.read()

				if success:
					##### SAVE GRABBED WEBCAM IMAGE ######
					imwrite(_SCcacheImageFilePath, img)
					imshow("Shot Clock OCR Webcam", img)

					##### RUN PRELIMINARY IMAGE PROCESSING #####
					_command = _ssocrFilePath + ' ' + self.ssocrArguments + ' ' + _SCcacheImageFilePath + ' -p -o ' + _SCssocrProcessedFilePath
					preprocessing = subprocess.Popen(_command, stdout=subprocess.PIPE, shell=True)

					##### SHOW PRELIMINARY PROCESSED IMAGE WITH BOUNDING BOXES, X, Y #####
					ssocr_img = imread(_SCssocrProcessedFilePath)
					putText(ssocr_img, str(self.mouse_coordinates[0]) + ", " + str(self.mouse_coordinates[1]), (5, 15), FONT_ITALIC, 0.4, (0,0,0))
					rectangle(ssocr_img, (int('0' + self.coords["clock_1"][1]), int('0' + self.coords["clock_1"][2])), (int('0' + self.coords["clock_1"][3]), int('0' + self.coords["clock_1"][4])), (0,0,255), 1)
					rectangle(ssocr_img, (int('0' + self.coords["clock_2"][1]), int('0' + self.coords["clock_2"][2])), (int('0' + self.coords["clock_2"][3]), int('0' + self.coords["clock_2"][4])), (0,0,255), 1)
					imshow("Shot Clock SSOCR", ssocr_img)


					##### CROP IMAGES TO BOUNDING BOX #####
					clock_1 = ssocr_img[int('0' + self.coords["clock_1"][2]):int('0' + self.coords["clock_1"][4]), int('0' + self.coords["clock_1"][1]):int('0' + self.coords["clock_1"][3])]
					clock_2 = ssocr_img[int('0' + self.coords["clock_2"][2]):int('0' + self.coords["clock_2"][4]), int('0' + self.coords["clock_2"][1]):int('0' + self.coords["clock_2"][3])]

					##### RESIZE WITH NEAREST NEIGHBOR, then CONVERT TO GRAYSCALE, then THRESHOLD to 0/255 #####
					ret, _clock_1_resized = threshold(cvtColor(resize(clock_1, (5, 7), 1, 1, INTER_NEAREST), cv.CV_BGR2GRAY), 127, 255, THRESH_BINARY)
					ret, _clock_2_resized = threshold(cvtColor(resize(clock_2, (5, 7), 1, 1, INTER_NEAREST), cv.CV_BGR2GRAY), 127, 255, THRESH_BINARY)

					##### SHOW PROCESSED IMAGES #####
					imshow("Digit 1", resize(_clock_1_resized, (50, 70), 1, 1, INTER_NEAREST))
					imshow("Digit 2", resize(_clock_2_resized, (50, 70), 1, 1, INTER_NEAREST))

					##### COMPARE MATRICES TO REFERENCE DIGITS #####
					for index, ref_digits in enumerate(self.referenceDigits):
						for digit in ref_digits:
							if((_clock_1_resized == digit).all()): # If match any digit in reference
								self.digitL = index
							if((_clock_2_resized == digit).all()):
								self.digitR = index


					waitKey(int(self.waitKey))
			 		self.processedFrameFlag.emit(1)
			 		self.recognizedDigits.emit([str(self.digitL), str(self.digitR)])



		except:
			self.error.emit(1)





if __name__ == '__main__':
	app = QtGui.QApplication(sys.argv)
	ex = MainWindow()
	sys.exit(app.exec_())

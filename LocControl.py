import json
import os
import sys
from datetime import timedelta, datetime
from itertools import count
from math import log10, floor, ceil, isnan, isinf
from time import sleep

from PyQt5.QtChart import QChart, QLineSeries, QChartView, QLogValueAxis, QValueAxis, QDateTimeAxis
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QPointF
from PyQt5.QtGui import QIntValidator, QPainter, QColor
from PyQt5.QtWidgets import QApplication, QCheckBox, QStackedWidget, QGridLayout, QMessageBox, QGroupBox, QRadioButton,\
    QLabel, QLineEdit, QPushButton, QTabWidget, QWidget, QFormLayout, QFileDialog, QHBoxLayout, QVBoxLayout
import moosegesture
from numpy import logspace, linspace

from Board import Board, QuitNow, PortDisconnectedError
from CustomWidgets import ComboBox, QHBoxLayoutWithError
from Fluidics import FluidicsGroup


class TerminalLabel(QLabel):  # label above graphs
    def __init__(self, *__args):
        super().__init__(*__args)
        self.sizePolicy().setRetainSizeWhenHidden(True)
        self.setAlignment(Qt.AlignHCenter)

    def toggle_visibility(self):
        self.setVisible(self.isHidden())


class ChartView(QChartView):
    axes_update_signal = pyqtSignal(float, float, float, float, name='axes_update')

    def setEnabled(self, enable):
        super().setEnabled(enable)
        self.__enabled = enable
        self.chart.setEnabled(enable)
        self.chart.setOpacity(1 if enable else 0.3)
        self.__update_x_axis()

    def __init__(self, *__args):
        super().__init__(*__args)

        self.__enabled = True

        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QColor(233, 228, 223))

        self.magnitude_series = QLineSeries()
        self.phase_series = QLineSeries()
        self.phase_series.setColor(QColor(213, 58, 61))

        self.chart = QChart()
        self.chart.setContentsMargins(0, -20, 0, -20)
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.setBackgroundRoundness(0)
        self.chart.setBackgroundVisible(False)
        self.chart.legend().hide()
        self.chart.addSeries(self.magnitude_series)
        self.chart.addSeries(self.phase_series)
        tf = self.chart.titleFont()
        tf.setPointSize(14)
        self.chart.setTitleFont(tf)

        self.f_axis = QLogValueAxis()
        self.f_axis.setTitleText('Frequency (Hz)')
        self.f_axis.setLabelFormat('%i')
        self.f_axis.setRange(1000, 100000)

        self.t_axis = QDateTimeAxis()
        self.t_axis.setTitleText('Time')

        self.m_axis = QValueAxis()
        self.m_axis.setTitleText('Magnitude (Ω)')

        self.p_axis = QValueAxis()
        self.p_axis.setTitleText('Phase (deg)')

        axes_title_font = self.f_axis.titleFont()
        axes_title_font.setPointSize(7.9)
        axes_title_font.setBold(True)
        self.f_axis.setTitleFont(axes_title_font)
        self.t_axis.setTitleFont(axes_title_font)
        self.m_axis.setTitleFont(axes_title_font)
        self.p_axis.setTitleFont(axes_title_font)

        axes_labels_font = self.f_axis.labelsFont()
        axes_labels_font.setPointSize(8)
        self.f_axis.setLabelsFont(axes_labels_font)
        self.t_axis.setLabelsFont(axes_labels_font)
        self.m_axis.setLabelsFont(axes_labels_font)
        self.p_axis.setLabelsFont(axes_labels_font)

        self.m_axis.setLabelsColor(self.magnitude_series.color())
        self.p_axis.setLabelsColor(self.phase_series.color())

        self.setChart(self.chart)

        self.chart.addAxis(self.m_axis, Qt.AlignLeft)
        self.magnitude_series.attachAxis(self.m_axis)

        self.chart.addAxis(self.p_axis, Qt.AlignRight)
        self.phase_series.attachAxis(self.p_axis)

        self.data = {}

        self.__update_x_axis()

        x_axis_group.time_radio.toggled.connect(self.__update_x_axis)

        self.__magnitude_frequency = None
        # noinspection PyUnresolvedReferences
        log_group.magnitude_combo.currentIndexChanged.connect(self.__update_magnitude_frequency)

        self.__phase_frequency = None
        # noinspection PyUnresolvedReferences
        log_group.phase_combo.currentIndexChanged.connect(self.__update_phase_frequency)

    def __update_magnitude_frequency(self, index):
        if self.__enabled and index != -1 and self.__magnitude_frequency != log_group.magnitude_combo.currentData():
            self.__refresh_data(True)

    def __update_phase_frequency(self, index):
        if self.__enabled and index != -1 and self.__phase_frequency != log_group.phase_combo.currentData():
            self.__refresh_data(True)

    def __update_x_axis(self):
        if not self.__enabled:
            return

        axis_to_add = self.f_axis if x_axis_group.frequency_radio.isChecked() else self.t_axis
        axis_to_remove = self.t_axis if x_axis_group.frequency_radio.isChecked() else self.f_axis

        if axis_to_remove in self.chart.axes():
            self.magnitude_series.detachAxis(axis_to_remove)
            self.phase_series.detachAxis(axis_to_remove)
            self.chart.removeAxis(axis_to_remove)

        if axis_to_add not in self.chart.axes():
            self.chart.addAxis(axis_to_add, Qt.AlignBottom)
            self.magnitude_series.attachAxis(axis_to_add)
            self.phase_series.attachAxis(axis_to_add)

        self.m_axis.setLabelFormat('%i')
        self.m_axis.setRange(0, 10000)
        self.m_axis.setTickCount(6)
        self.p_axis.setLabelFormat('%i')
        self.p_axis.setRange(-90, 90)

        self.__refresh_data(True)

    def update_y_axes(self, magnitude_min, magnitude_max, magnitude_ticks, phase_min, phase_max, phase_ticks):
        self.m_axis.setRange(magnitude_min, magnitude_max)
        self.m_axis.setTickCount(magnitude_ticks)
        self.p_axis.setRange(phase_min, phase_max)
        self.p_axis.setTickCount(phase_ticks)

    def __clear(self, title):
        self.chart.setTitle(title)
        self.magnitude_series.clear()
        self.phase_series.clear()
        self.m_axis.setLabelsVisible(False)
        self.p_axis.setLabelsVisible(False)
        self.axes_update_signal.emit(float('NaN'), float('NaN'), float('NaN'), float('NaN'))

    def __refresh_data(self, clear=True):
        magnitude_minimum = float('+inf')
        magnitude_maximum = float('-inf')
        phase_minimum = float('+inf')
        phase_maximum = float('-inf')
        self.m_axis.setLabelsVisible(True)
        self.p_axis.setLabelsVisible(True)
        if x_axis_group.frequency_radio.isChecked():
            if len(self.data) == 0:
                self.__clear('NO DATA')
            else:
                self.chart.setTitle('')
                self.magnitude_series.clear()
                self.phase_series.clear()
                connected = False
                for frequency, (magnitude, phase) in sorted(self.data[sorted(self.data.keys())[-1]].items()):
                    if magnitude < 10000:
                        connected = True
                    self.magnitude_series.append(frequency, magnitude)
                    self.phase_series.append(frequency, phase)
                    magnitude_minimum = min(magnitude_minimum, magnitude)
                    magnitude_maximum = max(magnitude_maximum, magnitude)
                    phase_minimum = min(phase_minimum, phase)
                    phase_maximum = max(phase_maximum, phase)

                if connected:
                    self.axes_update_signal.emit(magnitude_minimum, magnitude_maximum, phase_minimum, phase_maximum)
                else:
                    self.__clear('DISCONNECTED')
        else:
            self.__magnitude_frequency = log_group.magnitude_combo.currentData()
            self.__phase_frequency = log_group.phase_combo.currentData()

            times = []
            for time in self.data.keys():
                if self.data[time].keys() & {self.__magnitude_frequency, self.__phase_frequency}:
                    times.append(time)
            times.sort()

            if len(times) == 0:
                self.__clear('NO DATA')
                self.t_axis.setLabelsVisible(False)
            else:
                self.chart.setTitle('')
                self.t_axis.setLabelsVisible(True)

                connected = False
                for time in times:
                    try:
                        magnitude = self.data[time][self.__magnitude_frequency][0]
                        phase = self.data[time][self.__phase_frequency][1]
                    except KeyError:
                        print('No magnitude/phase data to plot for {0}/{1} Hz at {2}'.format(
                            self.__magnitude_frequency,
                            self.__phase_frequency,
                            time,
                            file=sys.stderr
                        ))
                        continue

                    magnitude_minimum = min(magnitude_minimum, magnitude)
                    magnitude_maximum = max(magnitude_maximum, magnitude)
                    phase_minimum = min(phase_minimum, phase)
                    phase_maximum = max(phase_maximum, phase)

                    if magnitude < 10000:
                        connected = True

                # time axis ticks
                if times[-1] - times[0] < timedelta(hours=6):
                    self.t_axis.setFormat('hh:mm')
                    self.t_axis.setTitleText('Time (hh:mm UTC)')
                    if times[-1] - times[0] < timedelta(minutes=5):
                        period = timedelta(minutes=1)
                    elif times[-1] - times[0] < timedelta(minutes=10):
                        period = timedelta(minutes=2)
                    elif times[-1] - times[0] < timedelta(hours=1):
                        period = timedelta(minutes=10)
                    else:
                        period = timedelta(hours=1)
                elif times[-1] - times[0] < timedelta(days=1):
                    self.t_axis.setFormat('hh')
                    self.t_axis.setTitleText('Time (hour UTC)')
                    if times[-1] - times[0] < timedelta(hours=12):
                        period = timedelta(hours=1)
                    else:
                        period = timedelta(hours=2)
                else:
                    period = timedelta(days=1)
                    self.t_axis.setFormat('dd')
                    self.t_axis.setTitleText('Time (day)')

                # if only one time point found, stretch it so it shows on graph
                if len(times) == 1:
                    fake_time = times[-1] + timedelta(seconds=(1 if times[-1].second < 30 else -1))
                    self.data[fake_time] = self.data[times[-1]]
                    times = list(sorted([times[-1], fake_time]))

                    self.t_axis.setRange(times[0], times[1])
                    self.t_axis.setTickCount(3)
                else:
                    axis_start = times[0] - (times[0] - datetime.min) % period
                    axis_stop = times[-1] + (datetime.min - times[-1]) % period

                    self.t_axis.setTickCount(int((axis_stop - axis_start) / period) + 1)
                    self.t_axis.setRange(axis_start, axis_stop)

                    # just append the latest time if the axes aren't being cleared
                    if not clear:
                        times = [times[-1]]

                if clear:
                    self.magnitude_series.clear()
                    self.phase_series.clear()

                chart_pixel_width = self.chart.plotArea().width()/self.devicePixelRatioF()
                if len(times) > chart_pixel_width:
                    times = [times[int(i)] for i in linspace(0, len(times)-1, chart_pixel_width)]

                self.magnitude_series.append(
                    QPointF(time.timestamp() * 1000, self.data[time][self.__magnitude_frequency][0]) for time in times)
                self.phase_series.append(QPointF(
                    time.timestamp() * 1000,
                    self.data[time][self.__phase_frequency][1]
                ) for time in times)

                if connected:
                    self.axes_update_signal.emit(magnitude_minimum, magnitude_maximum, phase_minimum, phase_maximum)
                else:
                    # TODO: add gaps for disconnections
                    self.__clear('DISCONNECTED')

    def add_data(self, time, results):
        self.data[time] = results
        self.__refresh_data(False)


class ChannelWidget(QGroupBox):  # pairs of graphs
    axes_update_signal = pyqtSignal(int, bool, float, float, float, float, name='axes_update')

    def __init__(self, channel):
        super().__init__('Channel {0}'.format(channel))
        self.__channel = channel
        self.setAlignment(Qt.AlignHCenter)
        self.setCheckable(True)
        self.setChecked(True)

        # initialise graphs
        self.impedance_graph = ChartView()
        self.reference_graph = ChartView()

        self.impedance_graph.axes_update_signal.connect(self.__axes_update_impedance)
        self.reference_graph.axes_update_signal.connect(self.__axes_update_reference)

        self.impedance_label = TerminalLabel('Impedance')
        self.reference_label = TerminalLabel('Reference')

        layout = QGridLayout()
        # noinspection PyArgumentList
        layout.addWidget(self.impedance_label, 0, 0)
        # noinspection PyArgumentList
        layout.addWidget(self.reference_label, 0, 1)
        # noinspection PyArgumentList,PyTypeChecker
        layout.addWidget(self.impedance_graph, 1, 0)
        # noinspection PyArgumentList,PyTypeChecker
        layout.addWidget(self.reference_graph, 1, 1)

        self.toggled.connect(self.impedance_graph.setEnabled)
        self.toggled.connect(self.reference_graph.setEnabled)
        self.setLayout(layout)

    def show_labels(self):
        self.impedance_label.show()
        self.reference_label.show()

    def parent_toggled(self, enabled):
        # noinspection PyUnresolvedReferences
        self.toggled.emit(enabled and self.isChecked())

    def __axes_update_impedance(self, magnitude_min, magnitude_max, phase_min, phase_max):
        self.axes_update_signal.emit(self.__channel, False, magnitude_min, magnitude_max, phase_min, phase_max)

    def __axes_update_reference(self, magnitude_min, magnitude_max, phase_min, phase_max):
        self.axes_update_signal.emit(self.__channel, True, magnitude_min, magnitude_max, phase_min, phase_max)

    def update_y_axes(self, magnitude_min, magnitude_max, magnitude_ticks, phase_min, phase_max, phase_ticks):
        self.impedance_graph.update_y_axes(
            magnitude_min, magnitude_max, magnitude_ticks, phase_min, phase_max, phase_ticks
        )
        self.reference_graph.update_y_axes(
            magnitude_min, magnitude_max, magnitude_ticks, phase_min, phase_max, phase_ticks
        )


class SmallScreenGraph(QWidget):
    __graph = None

    def paintEvent(self, a0) -> None:
        if self.__graph is None:
            super().paintEvent(a0)
        else:
            # noinspection PyTypeChecker
            painter = QPainter(self)
            self.__graph.render(painter)

    def setGraph(self, graph):
        self.__graph = graph
        self.repaint()


class SmallScreenWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.graph = SmallScreenGraph()
        self.swipe_label = QLabel('swipe ↕ to change port, ↔ to change channel')
        self.timer_label = QLabel('Next sweep in 00:00:00')
        self.terminal_label = QLabel('Name goes here')
        font = self.swipe_label.font()
        font.setPointSize(44)
        self.swipe_label.setFont(font)
        self.terminal_label.setFont(font)
        self.timer_label.setFont(font)

        self.swipe_label.setAlignment(Qt.AlignHCenter)
        self.terminal_label.setAlignment(Qt.AlignHCenter)
        self.timer_label.setAlignment(Qt.AlignHCenter)

        self.graph.setSizePolicy(self.sizePolicy().Expanding, self.sizePolicy().Expanding)
        layout = QVBoxLayout()
        layout.addWidget(self.swipe_label)
        layout.addWidget(self.timer_label)
        layout.addWidget(self.terminal_label)
        layout.addWidget(self.graph)
        self.setLayout(layout)

        self.__terminal = None

    @property
    def current_terminal(self):
        return self.__terminal

    def setGraph(self, graph, board, terminal):
        self.graph.setGraph(graph)
        self.terminal_label.setText('BOARD {0} PORT {1} CHANNEL {2} {3}'.format(
            board,
            terminal.port,
            terminal.channel,
            'REFERENCE' if terminal.is_reference else 'IMPEDANCE'
        ))
        self.__terminal = terminal

    def setTimer(self, time):
        self.timer_label.setText('Next sweep in: ' + time)


class PortTab(QGroupBox):  # tab of 16 graphs
    def __init__(self):
        super().__init__('Enabled')

        self.setCheckable(True)
        layout = QGridLayout()

        self.__axes = {
            'magnitude_min': [float('NaN') for _ in range(16)],
            'magnitude_max': [float('NaN') for _ in range(16)],
            'phase_min': [float('NaN') for _ in range(16)],
            'phase_max': [float('NaN') for _ in range(16)],
        }

        # store my ChannelWidgets
        self.channels = {}
        for channel in range(1, 9):
            self.channels[channel] = ChannelWidget(channel)
            self.channels[channel].axes_update_signal.connect(self.__axes_update)
            self.toggled.connect(self.channels[channel].parent_toggled)
            # noinspection PyArgumentList
            layout.addWidget(self.channels[channel], (channel - 1) // 2, (channel - 1) % 2)

        self.setLayout(layout)

    def __iter__(self):  # make iterable, return iterator over my ChannelWidgets
        return iter(self.channels.values())

    def show_channel_labels(self):
        for channel in self:
            channel.show_labels()

    def __axes_update(self, channel, is_reference, magnitude_min, magnitude_max, phase_min, phase_max):
        index = (channel - 1) * 2 + (1 if is_reference else 0)

        self.__axes['magnitude_min'][index] = magnitude_min
        self.__axes['magnitude_max'][index] = magnitude_max
        self.__axes['phase_min'][index] = phase_min
        self.__axes['phase_max'][index] = phase_max

        try:
            magnitude_min = min(x for x in self.__axes['magnitude_min'] if not isnan(x) and not isinf(x))
            magnitude_max = max(x for x in self.__axes['magnitude_max'] if not isnan(x) and not isinf(x))
            phase_min = min(x for x in self.__axes['phase_min'] if not isnan(x) and not isinf(x))
            phase_max = max(x for x in self.__axes['phase_max'] if not isnan(x) and not isinf(x))
        except ValueError:
            magnitude_min = 0
            magnitude_max = 10000
            phase_min = -90
            phase_max = 90

        if magnitude_min < 0:
            magnitude_min = 0
        if magnitude_max > 10000:
            magnitude_max = 10000
        if phase_min < -90:
            phase_min = -90
        if phase_max > 90:
            phase_max = 90

        ticks = [
            1.0,
            5.0,
            7.5,
            10.0,
            15.0,
            20.0,
            30.0,
            40.0,
            50.0,
            75.0,
            100.0,
            150.0,
            200.0,
            300.0,
            400.0,
            500.0,
            750.0,
            1000.0,
            1500.0,
            2000.0,
        ]

        magnitude_ticks = 6
        for tick in ticks:
            minimum = floor(magnitude_min / tick) * tick
            maximum = (ceil(magnitude_max / tick) * tick)
            magnitude_ticks = (maximum - minimum) / tick + 1
            if magnitude_ticks < 7:
                if tick == ticks[0]:
                    while magnitude_ticks < 4:
                        minimum -= tick
                        maximum += tick
                        magnitude_ticks = (maximum - minimum) / tick + 1
                magnitude_min = minimum
                magnitude_max = maximum
                break

        phase_ticks = 6
        for tick in ticks:
            minimum = floor(phase_min / tick) * tick
            maximum = (ceil(phase_max / tick) * tick)
            phase_ticks = (maximum - minimum) / tick + 1
            if phase_ticks < 7:
                if tick == ticks[0]:
                    while phase_ticks < 4:
                        minimum -= tick
                        maximum += tick
                        phase_ticks = (maximum - minimum) / tick + 1
                phase_min = minimum
                phase_max = maximum
                break

        for channel in self:
            channel.update_y_axes(magnitude_min, magnitude_max, magnitude_ticks, phase_min, phase_max, phase_ticks)

    def add_data(self, terminal, time, results):
        if terminal.is_reference:
            chart_view = self.channels[terminal.channel].reference_graph
        else:
            chart_view = self.channels[terminal.channel].impedance_graph

        chart_view.add_data(time, results)


class BoardTab(QStackedWidget):  # tab of port tabs
    def __init__(self, board: Board, small_screen, parent=None):
        super().__init__(parent)
        self.__board = board
        self.__tab_widget = QTabWidget(parent)

        # store my PortTabs
        self.port_tabs = {}
        for port in range(1, 5):
            self.port_tabs[port] = PortTab()
            self.__tab_widget.addTab(self.port_tabs[port], 'Port {0}'.format(port))

        self.ss_widget = SmallScreenWidget()
        self.__small_screen = False
        schedule_group.sig_timer_updated.connect(self.ss_widget.setTimer)

        self.addWidget(self.__tab_widget)
        self.addWidget(self.ss_widget)

        self.__swipe_points = None

        self.set_small_screen(small_screen)

    def __iter__(self):  # make iterable, return iterator over my PortTabs
        return iter([self.__tab_widget.widget(i) for i in range(self.count())])

    def show_channel_labels(self):
        for port in self:
            port.show_channel_labels()

    def select(self, terminal):  # select board and terminal WITHOUT MUTEX!
        self.blink(False)
        self.board().select()
        self.board().mux.select(terminal)
        self.blink(True, terminal)

    def blink(self, blink, terminal=None):  # enable or disable blinking one or all labels
        for terminal in (self.enabled_terminals() if terminal is None else [terminal]):
            if terminal.is_reference:
                label = self.port_tabs[terminal.port].channels[terminal.channel].reference_label
            else:
                label = self.port_tabs[terminal.port].channels[terminal.channel].impedance_label

            if blink:
                blink_timer.timeout.connect(label.toggle_visibility)
                for enabled_terminal in self.enabled_terminals():
                    if enabled_terminal.port == terminal.port:
                        if terminal == enabled_terminal:
                            self.show_terminal(terminal)
                        break
            else:
                try:
                    blink_timer.timeout.disconnect(label.toggle_visibility)
                except TypeError:
                    pass
                label.show()

    # def event(self, e):
    #     if e.type() == QEvent.Gesture:
    #         print(e)
    #         print(e.gesture())
    #         print(e.gesture(Qt.SwipeGesture))
    #         return True
    #     else:
    #         return super().event(e)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.__swipe_points = []

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        if self.__swipe_points is not None:
            self.__swipe_points.append((event.x(), event.y()))

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self.__swipe_points is not None:
            strokes = moosegesture.getGesture(self.__swipe_points)
            gestures = moosegesture.findClosestMatchingGesture(strokes, ['U', 'D', 'L', 'R'])
            if gestures is not None and len(gestures) == 1:
                gesture = gestures[0][0]
                enabled_terminals = self.enabled_terminals()
                ports = list({terminal.port for terminal in enabled_terminals})
                if gesture == 'L':
                    for terminal_index in range(len(enabled_terminals)):
                        if enabled_terminals[terminal_index] == self.ss_widget.current_terminal:
                            self.show_terminal(enabled_terminals[(terminal_index+1) % len(enabled_terminals)])
                            break
                elif gesture == 'R':
                    for terminal_index in range(len(enabled_terminals)):
                        if enabled_terminals[terminal_index] == self.ss_widget.current_terminal:
                            self.show_terminal(enabled_terminals[(terminal_index-1) % len(enabled_terminals)])
                            break
                elif len(ports) > 1:
                    current_port_index = 0
                    for port_index in range(len(ports)):
                        if ports[port_index] == self.ss_widget.current_terminal.port:
                            current_port_index = port_index

                    if gesture == 'U':
                        new_port = ports[(current_port_index+1) % len(ports)]
                    else:  # gesture == 'D'
                        new_port = ports[(current_port_index-1) % len(ports)]

                    for terminal in enabled_terminals:
                        if terminal.port == new_port:
                            self.show_terminal(terminal)
                            break

    def enabled_terminals(self):  # return list of enabled terminals across all enabled ports
        terminals = []
        for port in self.__board.mux:
            for channel in port:
                for terminal in channel:
                    if self.port_tabs[terminal.port].isChecked():
                        if self.port_tabs[terminal.port].channels[terminal.channel].isChecked():
                            terminals.append(terminal)
        return terminals

    def board(self):
        return self.__board

    # noinspection SpellCheckingInspection,PyUnusedLocal
    def new_data(self, time, terminal, results: dict, raw_results: dict = None):
        self.blink(False, terminal)

        # REVERT: result printing
        # real = self.board().real
        # imag = self.board().imag
        # magnitudes = self.board().magnitudes
        #
        # frequencies, impedances, phases = [], [], []
        # for frequency, (impedance, phase) in sorted(results.items()):
        #     frequencies.append(frequency)
        #     impedances.append(impedance)
        #     phases.append(phase)
        #
        # print('Got {0} samples from board {1} port {2} channel {3} terminal {4}'.format(
        #     len(results),
        #     self.__board.address(),
        #     terminal.port,
        #     terminal.channel,
        #     'reference' if terminal.is_reference else 'impedance'
        # ))
        #
        # print('f = ', end='')
        # print(frequencies, end=';\n')
        # print('i = ', end='')
        # print(impedances, end=';\n')
        # print('p = ', end='')
        # print(phases, end=';\n')
        # print('re = ', end='')
        # print(real, end=';\n')
        # print('im = ', end='')
        # print(imag, end=';\n')
        # print('m = ', end='')
        # print(magnitudes, end=';\n')

        log_filename = '/board{0}_port{1}_channel{2}_{3}'.format(
            self.board().address(),
            terminal.port,
            terminal.channel,
            'reference' if terminal.is_reference else 'impedance'
        )

        log_directory = log_group.directory_field.text()
        log_file_path = log_directory + log_filename
        if not os.path.exists(log_file_path):
            if not os.path.exists(log_directory):
                os.makedirs(log_directory, exist_ok=True)
            with open(log_file_path, 'a+') as log_file:
                log_file.write('Board: {0}\n'.format(self.board().address()))
                log_file.write('Port: {0}\n'.format(terminal.port))
                log_file.write('Channel: {0}\n'.format(terminal.channel))
                log_file.write('{0} terminal\n'.format('Reference' if terminal.is_reference else 'Impedance'))
                log_file.write('\n')
                log_file.write('Time Initiated (UTC)\tFrequency (Hz)\tMagnitude (Ω)\tPhase (°)\n')

        with open(log_file_path, 'a+') as log_file:
            for frequency, (impedance, phase) in sorted(results.items()):
                log_file.write('{0}\t{1: <8g}\t{2: <8g}\t{3:+g}\n'.format(
                    time.strftime('%Y-%m-%d %H:%M'),
                    frequency,
                    float('{:.4g}'.format(impedance)),
                    phase,
                ))
            log_file.write('\n')

        log_directory += '/Single Frequency'
        log_file_path = log_directory + log_filename
        if not os.path.exists(log_file_path):
            if not os.path.exists(log_directory):
                os.makedirs(log_directory, exist_ok=True)
            with open(log_file_path, 'a+') as log_file:
                log_file.write('Board: {0}\n'.format(self.board().address()))
                log_file.write('Port: {0}\n'.format(terminal.port))
                log_file.write('Channel: {0}\n'.format(terminal.channel))
                log_file.write('{0} terminal\n'.format('Reference' if terminal.is_reference else 'Impedance'))
                log_file.write('\n')
                log_file.write('                    \t\tMagnitude\t\t\t  Phase\n')
                log_file.write('Time Initiated (UTC)\tFrequency (Hz)\tValue (Ω)\tFrequency (Hz)\tValue (°)\n')

        try:
            with open(log_file_path, 'a+') as log_file:
                log_file.write('{0}\t{1: <8g}\t{2: <8g}\t{3: <8g}\t{4:+g}\n'.format(
                    time.strftime('%Y-%m-%d %H:%M'),
                    log_group.magnitude_combo.currentData(),
                    float('{:.4g}'.format(results[log_group.magnitude_combo.currentData()][0])),
                    log_group.phase_combo.currentData(),
                    results[log_group.phase_combo.currentData()][1]
                ))
        except KeyError:
            print('Failed to find data at frequency {0} or {1}'.format(
                log_group.magnitude_combo.currentData(),
                log_group.phase_combo.currentData()
            ),
                file=sys.stderr
            )

        # REVERT: raw data save
        # if raw_results is not None:
        #     raw_log_filename = log_group.directory_field.text() + '/.board{0}_port{1}_channel{2}_{3}'.format(
        #         self.board().address(),
        #         terminal.port,
        #         terminal.channel,
        #         'reference' if terminal.is_reference else 'impedance'
        #         )
        #     with open(raw_log_filename, 'a+') as log_file:
        #         log_file.write('{0}\t'.format(time.strftime('%Y-%m-%d %H:%M')))
        #         json.dump(raw_results, log_file)
        #         log_file.write('\n')

        self.port_tabs[terminal.port].add_data(terminal, time, results)
        self.show_terminal(terminal)

    def show_terminal(self, terminal):
        self.__tab_widget.setCurrentIndex(terminal.port-1)
        if self.__small_screen:
            channel = self.port_tabs[terminal.port].channels[terminal.channel]
            self.ss_widget.setGraph(
                channel.reference_graph if terminal.is_reference else channel.impedance_graph,
                self.__board.address(),
                terminal
            )

    def set_small_screen(self, small_screen):
        self.__small_screen = small_screen
        if small_screen:
            self.show_terminal(Board.Mux.Port.Channel.Terminal(self.__tab_widget.currentIndex()+1, 1, False))
            self.setCurrentIndex(1)
        else:
            self.setCurrentIndex(0)


# noinspection SpellCheckingInspection
class BoardTabManager(QTabWidget):
    __small_screen = False
    sig_small_screen = pyqtSignal(bool, name='small_screen')

    def mouseDoubleClickEvent(self, a0) -> None:
        app.setOverrideCursor(Qt.WaitCursor)
        self.__small_screen = not self.__small_screen
        self.sig_small_screen.emit(self.__small_screen)
        for board_tab in self:
            board_tab.set_small_screen(self.__small_screen)

        self.setStyleSheet('QTabBar {font-size: 28px} QTabBar::tab {height: 80px}' if self.__small_screen else '')

        app.restoreOverrideCursor()

    def show_channel_labels(self):
        for board in self:
            board.show_channel_labels()

    def update_tabs(self, boards):
        for i in range(self.count() - 1, -1, -1):
            if self.widget(i).board().address() not in [board.address() for board in boards]:
                self.removeTab(i)

        for board in boards:
            if board.address() not in [self.widget(i).board().address() for i in range(self.count())]:
                i = self.count()
                for i in range(self.count()):
                    if board.address() < self.widget(i).board().address():
                        break
                    elif i == self.count() - 1:
                        i += 1
                self.insertTab(i, BoardTab(board, self.__small_screen, parent=self), 'Board {0}'.format(board.address()))

    # return list of all my BoardTabs
    def tab_list(self):
        return [self.widget(i) for i in range(self.count())]

    # make iterable, return iterator over all my BoardTabs
    def __iter__(self):
        return iter([self.widget(i) for i in range(self.count())])

    # try to connect to all enabled terminals, return list of error messages
    def test_connection(self):
        print()
        print('Connection test')
        errors = []
        for board_tab in self:  # type: BoardTab
            try:
                board_tab.board().select()
            except OSError:
                errors.append('Board {0} disconnected'.format(board_tab.board().address()))
            else:
                for terminal in (port.channel1.impedance for port in board_tab.board().mux):
                    if board_tab.port_tabs[terminal.port].isChecked():
                        try:
                            board_tab.board().mux.select(terminal)
                        except PortDisconnectedError as error:
                            errors.append(error.strerror)
        print()
        return errors


# make 'Schedule' UI
class ScheduleGroup(QGroupBox):
    sig_timer_updated = pyqtSignal(str, name='timer_updated')

    # noinspection PyTypeChecker,PyTypeChecker,PyTypeChecker
    def __init__(self):
        super().__init__('Schedule')

        self.interval_label = QLabel('Sweep every')
        self.interval_field = QLineEdit()
        self.interval_field.setMaxLength(2)
        self.interval_field.setValidator(QIntValidator(0, 99))
        self.interval_combobox = ComboBox()
        self.interval_combobox.addItems(['h', 'm', 's'])
        self.interval_layout = QHBoxLayoutWithError(
            self.interval_field,
            self.interval_combobox,
            error='Range: 0 - 24 hours'
        )
        self.interval = None

        self.delay_checkbox = QCheckBox('Start in')
        self.delay_field = QLineEdit()
        self.delay_field.setMaxLength(2)
        self.delay_field.setValidator(QIntValidator(0, 99))
        self.delay_combobox = ComboBox()
        self.delay_combobox.addItems(['h', 'm', 's'])
        self.start_layout = QHBoxLayoutWithError(self.delay_field, self.delay_combobox, error='Range: 0 - 24 hours')
        self.delay_field.setDisabled(True)
        self.delay_combobox.setDisabled(True)
        self.delay_checkbox.toggled.connect(self.delay_field.setEnabled)
        self.delay_checkbox.toggled.connect(self.delay_combobox.setEnabled)
        self.start = None

        self.stop_checkbox = QCheckBox('Stop after')
        self.stop_label = QLabel('sweeps')
        self.stop_field = QLineEdit()
        self.stop_field.setMaxLength(3)
        self.stop_field.setValidator(QIntValidator(1, 999))
        self.stop_layout = QHBoxLayoutWithError(self.stop_field, self.stop_label, error='Range: 1 - 999')
        self.stop_field.setDisabled(True)
        self.stop_label.setDisabled(True)
        self.stop_checkbox.toggled.connect(self.stop_field.setEnabled)
        self.stop_checkbox.toggled.connect(self.stop_label.setEnabled)

        self.next_label = QLabel('Next sweep in')
        self.next_field = QLabel('<hh mm ss>')

        layout = QFormLayout()
        layout.addRow(self.interval_label, self.interval_layout)
        layout.addRow(self.delay_checkbox, self.start_layout)
        layout.addRow(self.stop_checkbox, self.stop_layout)
        layout.addRow(self.next_label, self.next_field)

        self.setLayout(layout)

    # update countdown timer
    def update_timer(self, time: timedelta):
        if time is None:
            schedule_group.next_field.setText('')
        else:
            hours, remainder = divmod(time.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.next_field.setText('{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds)))
        self.sig_timer_updated.emit(self.next_field.text())

    def set_small_screen(self, small_screen):
        self.setHidden(small_screen)


# make 'Sweep' UI
class SweepGroup(QGroupBox):
    # noinspection PyTypeChecker,PyTypeChecker,PyTypeChecker
    def __init__(self):
        super().__init__('Sweep')
        self.log_checkbox = QCheckBox('Logarithmic')
        self.start_label = QLabel('Start (Hz)')
        self.increment_label = QLabel('Step (Hz)')
        self.samples_label = QLabel('# Steps')
        self.final_label = QLabel('Final (Hz)')

        self.start_field = QLineEdit()
        self.final_field = QLineEdit()
        self.samples_field = QLineEdit()
        self.increment_field = QLabel()

        self.start_field.setValidator(QIntValidator(1000, 100000))
        self.final_field.setValidator(QIntValidator(1000, 100000))
        self.samples_field.setValidator(QIntValidator(0, 511))

        self.start_field.setMaxLength(6)
        self.final_field.setMaxLength(6)
        self.samples_field.setMaxLength(3)

        self.start_layout = QHBoxLayoutWithError(self.start_field, error='Range: 1 - 100 kHz')
        self.final_layout = QHBoxLayoutWithError(self.final_field, error='Range: 1 - 100 kHz')
        self.samples_layout = QHBoxLayoutWithError(self.samples_field, error='Range: 0 - 511')
        self.increment_layout = QHBoxLayoutWithError(self.increment_field, stretch=True, error='Range: 0 - 62 kHz')

        layout = QFormLayout()
        layout.addRow(self.log_checkbox)
        layout.addRow(self.start_label, self.start_layout)
        layout.addRow(self.final_label, self.final_layout)
        layout.addRow(self.samples_label, self.samples_layout)
        layout.addRow(self.increment_label, self.increment_layout)

        self.setLayout(layout)

    def set_small_screen(self, small_screen):
        self.setHidden(small_screen)


# make 'Log' UI
class LogGroup(QGroupBox):
    def __init__(self):
        super().__init__('Log')
        self.directory_field = QLineEdit()
        self.directory_field.setReadOnly(True)
        self.change_button = QPushButton('Change...')

        self.directory_layout = QHBoxLayoutWithError(self.directory_field, self.change_button)

        self.magnitude_label = QLabel('Magnitude (Hz):')
        self.magnitude_combo = ComboBox()
        self.phase_label = QLabel('Phase (Hz):')
        self.phase_combo = ComboBox()
        self.combo_values = []

        frequency_layout = QFormLayout()
        frequency_layout.addRow(self.magnitude_label, self.magnitude_combo)
        frequency_layout.addRow(self.phase_label, self.phase_combo)

        layout = QVBoxLayout()
        layout.addLayout(self.directory_layout)
        layout.addLayout(frequency_layout)
        self.setLayout(layout)

    def populate_combos(self, values):
        if self.combo_values != values:
            self.combo_values = values

            values_text = ['{: <8}'.format(value)[:(8 if value == 100000 else 7)] for value in values]

            if all(int(value) == float(value_text) for value, value_text in zip(values, values_text)):
                values_text = [str(int(value)) for value in values]

            for combo in [self.magnitude_combo, self.phase_combo]:
                old_index = combo.currentIndex()
                combo.clear()
                for index in range(len(values)):
                    combo.insertItem(index, values_text[index], values[index])
                combo.setCurrentIndex(old_index if 0 < old_index < combo.count() else 0)

    def set_small_screen(self, small_screen):
        self.change_button.setHidden(small_screen)
        self.magnitude_label.setHidden(small_screen)
        self.magnitude_combo.setHidden(small_screen)
        self.phase_label.setHidden(small_screen)
        self.phase_combo.setHidden(small_screen)

        self.setStyleSheet('font-size: 18pt' if small_screen else '')


class XAxisGroup(QGroupBox):
    def __init__(self):
        super().__init__('X Axis')

        self.frequency_radio = QRadioButton('Frequency')
        self.time_radio = QRadioButton('Time')

        self.__default_font = self.frequency_radio.font()

        layout = QGridLayout()
        layout.addWidget(self.frequency_radio, 0, 0)
        layout.addWidget(self.time_radio, 0, 1)

        self.setLayout(layout)

    def set_small_screen(self, small_screen):
        self.layout().removeWidget(self.time_radio)
        if small_screen:
            # noinspection PyArgumentList
            self.layout().addWidget(self.time_radio, 1, 0)
            stylesheet = 'QRadioButton {font-size: 24pt} QRadioButton::indicator {width: 25px; height: 25px}'
            self.frequency_radio.setStyleSheet(stylesheet)
            self.time_radio.setStyleSheet(stylesheet)
            self.setStyleSheet('font-size: 18pt')
        else:
            # noinspection PyArgumentList
            self.layout().addWidget(self.time_radio, 0, 1)
            self.frequency_radio.setStyleSheet('')
            self.time_radio.setStyleSheet('')
            self.setStyleSheet('')


class StartStopButton(QPushButton):
    def __init__(self):
        super().__init__('START')
        self.setSizePolicy(self.sizePolicy().Expanding, self.sizePolicy().Expanding)
        self.setDefault(True)
        self.setAutoDefault(True)
        self.setAutoFillBackground(True)

        self.setStyleSheet('background-color: lime')

        font = self.font()
        font.setPointSize(24)
        self.setFont(font)

        self.update()


def set_small_screen(small_screen):
    # hide things first to avoid violating window bounds
    if small_screen:
        sweep_group.set_small_screen(True)
        schedule_group.set_small_screen(True)

    log_group.set_small_screen(small_screen)
    x_axis_group.set_small_screen(small_screen)
    fluidics_group.set_small_screen(small_screen)

    # show things last to avoid the same
    if not small_screen:
        sweep_group.set_small_screen(False)
        schedule_group.set_small_screen(False)


# change log directory button handler
def change_log_directory():
    # noinspection PyArgumentList,PyCallByClass
    log_group.directory_field.setText(
        QFileDialog.getExistingDirectory(
            window,
            directory=log_group.directory_field.text()
        )
    )


def validate_fast():
    valid = True

    # check all 'Sweep' fields
    for layout, field in [
        (sweep_group.start_layout, sweep_group.start_field),
        (sweep_group.final_layout, sweep_group.final_field),
        (sweep_group.samples_layout, sweep_group.samples_field)
    ]:
        layout.hide_error(field.hasAcceptableInput())
        valid &= field.hasAcceptableInput()

    # fill 'Step' field unless 'Logarithmic' checkbox is checked, in which case just empty and disable it
    if sweep_group.log_checkbox.isChecked():
        sweep_group.increment_label.setDisabled(True)
        sweep_group.increment_field.setText('')
        sweep_group.increment_layout.hide_error()
    else:
        sweep_group.increment_label.setEnabled(True)
        try:
            sweep_group_start = int(sweep_group.start_field.text())
            sweep_group_final = int(sweep_group.final_field.text())
            if sweep_group_final == sweep_group_start:
                increment = 0
            else:
                increment = (sweep_group_final - sweep_group_start) / int(sweep_group.samples_field.text())
            increment_text = '{: <8}'.format(increment)[:7]
            if float(increment_text) == int(increment):
                increment_text = str(int(increment))
            sweep_group.increment_field.setText(increment_text)
            accept = (0 < increment <= 62000)
            valid &= accept
            sweep_group.increment_layout.hide_error(accept)
        except (ValueError, ZeroDivisionError):
            valid = False
            sweep_group.increment_field.setText('')
            sweep_group.increment_layout.hide_error()

    # calculate schedule interval and verify it's less than 24 hours
    if schedule_group.interval_field.hasAcceptableInput():
        schedule_group.interval = timedelta(seconds=int(schedule_group.interval_field.text()))
        if schedule_group.interval_combobox.currentText() == 'h':
            schedule_group.interval *= 3600
        elif schedule_group.interval_combobox.currentText() == 'm':
            schedule_group.interval *= 60

        accept = timedelta() <= schedule_group.interval <= timedelta(hours=24)
        valid &= accept
        schedule_group.interval_layout.hide_error(accept)
    else:
        valid = False
        schedule_group.interval = None
        schedule_group.interval_layout.show_error()

    # calculate schedule delay and verify it is less than 24 hours
    if schedule_group.delay_field.hasAcceptableInput() and schedule_group.delay_checkbox.isChecked():
        schedule_group.start = timedelta(seconds=int(schedule_group.delay_field.text()))
        if schedule_group.delay_combobox.currentText() == 'h':
            schedule_group.start *= 3600
        elif schedule_group.delay_combobox.currentText() == 'm':
            schedule_group.start *= 60

        accept = timedelta() <= schedule_group.start <= timedelta(hours=24)
        valid &= accept
        schedule_group.start_layout.show_error(not accept)
    elif schedule_group.delay_checkbox.isChecked():
        valid = False
        schedule_group.start = None
        schedule_group.start_layout.show_error()
    else:
        schedule_group.start = timedelta()
        schedule_group.start_layout.hide_error()

    schedule_group.update_timer(schedule_group.start)

    # check stop field
    if schedule_group.stop_checkbox.isChecked() and not schedule_group.stop_field.hasAcceptableInput():
        valid = False
        schedule_group.stop_layout.show_error()
    else:
        schedule_group.stop_layout.hide_error()

    return valid


# check all input data is ok
def validate():
    valid = validate_fast()

    # are there any boards discovered
    valid &= len(board_tab_manager.tab_list()) > 0

    # check log directory access
    try:
        with open(log_group.directory_field.text() + '/.test', 'a+') as file:
            file.write('\n')
        os.remove(log_group.directory_field.text() + '/.test')
    except OSError as error:
        log_group.directory_layout.show_error(text=os.strerror(error.errno))
        valid = False
    else:
        log_group.directory_layout.hide_error()

    try:
        steps = int(sweep_group.samples_field.text())
    except ValueError:
        valid = False
    else:
        if sweep_group.log_checkbox.isChecked():
            values = list(logspace(
                log10(int(sweep_group.start_field.text())),
                log10(int(sweep_group.final_field.text())),
                steps+1
            ))
        else:
            values = list(linspace(
                int(sweep_group.start_field.text()),
                int(sweep_group.final_field.text()),
                steps+1
            ))

        log_group.populate_combos(values)

    return valid


# # check all input data is ok
# def validate():
#     # are there any boards discovered
#     valid = len(board_tab_manager.tab_list()) > 0
#
#     # check log directory access
#     try:
#         with open(log_group.directory_field.text() + '/.test', 'a+') as file:
#             file.write('\n')
#         os.remove(log_group.directory_field.text() + '/.test')
#     except OSError as error:
#         log_group.directory_layout.show_error(text=os.strerror(error.errno))
#         valid = False
#     else:
#         log_group.directory_layout.hide_error()
#
#     # check all 'Sweep' fields
#     for layout, field in [
#         (sweep_group.start_layout, sweep_group.start_field),
#         (sweep_group.final_layout, sweep_group.final_field),
#         (sweep_group.samples_layout, sweep_group.samples_field)
#     ]:
#         layout.hide_error(field.hasAcceptableInput())
#         valid &= field.hasAcceptableInput()
#
#     # fill 'Step' field unless 'Logarithmic' checkbox is checked, in which case just empty and disable it
#     if sweep_group.log_checkbox.isChecked():
#         sweep_group.increment_label.setDisabled(True)
#         sweep_group.increment_field.setText('')
#         sweep_group.increment_layout.hide_error()
#     else:
#         sweep_group.increment_label.setEnabled(True)
#         try:
#             sweep_group_start = int(sweep_group.start_field.text())
#             sweep_group_final = int(sweep_group.final_field.text())
#             if sweep_group_final == sweep_group_start:
#                 increment = 0
#             else:
#                 increment = (sweep_group_final - sweep_group_start) / int(sweep_group.samples_field.text())
#             increment_text = '{: <8}'.format(increment)[:7]
#             if float(increment_text) == int(increment):
#                 increment_text = str(int(increment))
#             sweep_group.increment_field.setText(increment_text)
#             accept = (0 < increment <= 62000)
#             valid &= accept
#             sweep_group.increment_layout.hide_error(accept)
#         except (ValueError, ZeroDivisionError):
#             valid = False
#             sweep_group.increment_field.setText('')
#             sweep_group.increment_layout.hide_error()
#
#     # calculate schedule interval and verify it's less than 24 hours
#     if schedule_group.interval_field.hasAcceptableInput():
#         schedule_group.interval = timedelta(seconds=int(schedule_group.interval_field.text()))
#         if schedule_group.interval_combobox.currentText() == 'h':
#             schedule_group.interval *= 3600
#         elif schedule_group.interval_combobox.currentText() == 'm':
#             schedule_group.interval *= 60
#
#         accept = timedelta() <= schedule_group.interval <= timedelta(hours=24)
#         valid &= accept
#         schedule_group.interval_layout.hide_error(accept)
#     else:
#         valid = False
#         schedule_group.interval = None
#         schedule_group.interval_layout.show_error()
#
#     # calculate schedule delay and verify it is less than 24 hours
#     if schedule_group.delay_field.hasAcceptableInput() and schedule_group.delay_checkbox.isChecked():
#         schedule_group.start = timedelta(seconds=int(schedule_group.delay_field.text()))
#         if schedule_group.delay_combobox.currentText() == 'h':
#             schedule_group.start *= 3600
#         elif schedule_group.delay_combobox.currentText() == 'm':
#             schedule_group.start *= 60
#
#         accept = timedelta() <= schedule_group.start <= timedelta(hours=24)
#         valid &= accept
#         schedule_group.start_layout.show_error(not accept)
#     elif schedule_group.delay_checkbox.isChecked():
#         valid = False
#         schedule_group.start = None
#         schedule_group.start_layout.show_error()
#     else:
#         schedule_group.start = timedelta()
#         schedule_group.start_layout.hide_error()
#
#     update_timer(schedule_group.start)
#
#     # check stop field
#     if schedule_group.stop_checkbox.isChecked() and not schedule_group.stop_field.hasAcceptableInput():
#         valid = False
#         schedule_group.stop_layout.show_error()
#     else:
#         schedule_group.stop_layout.hide_error()
#
#     try:
#         steps = int(sweep_group.samples_field.text())
#     except ValueError:
#         valid = False
#     else:
#         if sweep_group.log_checkbox.isChecked():
#             values = list(logspace(
#                 log10(int(sweep_group.start_field.text())),
#                 log10(int(sweep_group.final_field.text())),
#                 steps+1
#             ))
#         else:
#             values = list(linspace(
#                 int(sweep_group.start_field.text()),
#                 int(sweep_group.final_field.text()),
#                 steps+1
#             ))
#
#         log_group.populate_combos(values)
#
#     return valid


# enable/disable/change parts of the UI when acquisition is started and stopped
def set_controls(started=None):
    if started is None:
        # make it a yellow stopping button
        start_stop_button.setText('STOPPING')
        start_stop_button.setStyleSheet('background-color: yellow')
        start_stop_button.repaint()
        return

    start_stop_button.setText('STOP' if started else 'START')
    start_stop_button.setStyleSheet('background-color: ' + ('red' if started else 'lime'))

    # parts of the UI to 'de-grey' when they're disabled
    unmute = [
        sweep_group.start_field,
        sweep_group.samples_field,
        sweep_group.final_field,
        schedule_group.interval_field,
        schedule_group.interval_combobox,
        log_group.directory_field,
        log_group.magnitude_combo,
        log_group.phase_combo,
    ]

    # parts of the UI to disable
    disable = unmute + [
        sweep_group.log_checkbox,
        schedule_group.delay_checkbox,
        schedule_group.stop_checkbox,
        log_group.change_button,
        log_group.magnitude_combo,
        log_group.phase_combo,
    ]

    # disable all port tabs, unmute enabled tabs and channels
    for board_tab in board_tab_manager:  # type: BoardTab
        for port_tab in board_tab:
            disable += [port_tab]
            if port_tab.isChecked():
                unmute += [port_tab]
                disable += [channel for channel in port_tab.channels.values()]

    if sweep_group.log_checkbox.isChecked():
        unmute += [sweep_group.log_checkbox]

    if schedule_group.delay_checkbox.isChecked():
        unmute += [schedule_group.delay_checkbox, schedule_group.delay_field, schedule_group.delay_combobox]
        disable += [schedule_group.delay_field, schedule_group.delay_combobox]

    if schedule_group.stop_checkbox.isChecked():
        unmute += [schedule_group.stop_checkbox, schedule_group.stop_field, schedule_group.stop_label]
        disable += [schedule_group.stop_field, schedule_group.stop_label]

    # do the disabling
    for widget in disable:
        widget.setDisabled(started)

    # do the un-muting
    for widget in unmute:
        widget.setStyleSheet('' if not started else
                             'color: black; '
                             'QComboBox { color: black; }; '                             
                             'QCheckBox { color: black; }; '
                             'QLabel { color: black; }; '
                             'QCheckBox::QLabel { color: black; }; '
                             'QWidget { color: black; }; '
                             'QListView { color: black; }; '
                             )


# start button handler
def start():
    # disable start button for now
    start_stop_button.clicked.disconnect()

    autostart_timer.stop()
    # save setup
    save_config()
    # check connections
    errors = '\n'.join(board_tab_manager.test_connection())

    if len(errors) > 0 or not validate():
        if len(errors) > 0:
            QMessageBox.critical(window, 'Connection Error', errors)
        start_stop_button.clicked.connect(start)
        return

    board_detector.stop()
    set_controls(True)

    sweeps = int(schedule_group.stop_field.text()) if schedule_group.stop_checkbox.isChecked() else None

    # configure SchedulerThread
    global scheduler_thread
    scheduler_thread = SchedulerThread(
        int(sweep_group.start_field.text()),
        int(sweep_group.final_field.text()),
        int(sweep_group.samples_field.text()),
        sweep_group.log_checkbox.isChecked(),
        schedule_group.interval,
        schedule_group.start,
        sweeps,
        board_tab_manager.tab_list()
    )

    # connect signals for timer and stopping
    scheduler_thread.sig_update_timer.connect(schedule_group.update_timer)
    scheduler_thread.sig_done.connect(stop)
    scheduler_thread.start()
    # re-enable start button, change function to stop
    start_stop_button.clicked.connect(stop)


# stop button handler
def stop():
    # disable stop button for now
    # noinspection PyUnresolvedReferences
    try:
        start_stop_button.clicked.disconnect()
    except TypeError:  # no connected listeners
        pass

    set_controls(None)

    # disconnect the time or else it keeps interfering
    try:
        scheduler_thread.sig_update_timer.disconnect()
    except TypeError:  # no connected listeners
        pass

    if scheduler_thread.isRunning():
        scheduler_thread.finished.connect(stop)
        scheduler_thread.quit()
        return

    # ask the SchedulerThread to stop
    scheduler_thread.quit()
    # stop all labels blinking
    try:
        blink_timer.disconnect()
    except TypeError:  # no connected listeners
        pass
    board_tab_manager.show_channel_labels()

    validate()
    # re-enable stop button and change function to start
    set_controls(False)
    start_stop_button.clicked.connect(start)
    board_detector.start()


class SchedulerThread(QThread):
    sig_update_timer = pyqtSignal(timedelta, name='update_timer')
    sig_done = pyqtSignal(name='done')

    def __init__(self, start_freq, final_freq, samples, logarithmic, period, delay, sweeps, tabs, parent=None):
        super().__init__(parent)
        self.__start_freq = start_freq
        self.__final_freq = final_freq
        self.__samples = samples
        self.__logarithmic = logarithmic
        self.__period = period
        self.__delay = delay
        self.__sweeps = sweeps
        self.__tabs = tabs
        self.__mux_thread = QThread()
        self.quit_now = False

    def run(self):
        # next sweep happens after start delay
        next_time = datetime.utcnow() + self.__delay

        for sweep in count():
            if sweep == self.__sweeps:
                break
            # check time and update timer 10 times per second
            while next_time - datetime.utcnow() > timedelta() and not self.quit_now:
                self.sig_update_timer.emit(next_time - datetime.utcnow())
                sleep(0.5)
            next_time += self.__period

            # make sure MuxThread is finished
            self.__mux_thread.wait()
            if self.quit_now:
                return
            self.__mux_thread = MuxThread(
                datetime.utcnow(),
                self.__start_freq,
                self.__final_freq,
                self.__samples,
                self.__logarithmic,
                self.__tabs
            )
            self.__mux_thread.start()

        self.__mux_thread.wait()
        if not self.quit_now:
            self.sig_done.emit()

    # request stop
    def quit(self):
        self.quit_now = True
        # pass request down
        self.__mux_thread.quit()


# thread for synchronising terminal changes between boards
class MuxThread(QThread):
    sig_error = pyqtSignal(str, name='error')

    def __init__(self, time, start_freq, final_freq, samples, logarithmic, tabs, parent=None):
        super().__init__(parent)
        # make a SweepThread for every board
        self.sweep_threads = [SweepThread(time, start_freq, final_freq, samples, logarithmic, tab) for tab in tabs]
        self.quit_now = False
        self.sig_error.connect(error_dialog.update_message)

    def run(self):
        while len(self.sweep_threads) > 0:
            for i in range(len(self.sweep_threads)-1, -1, -1):
                try:
                    # try every enabled terminal until one is found that's not disconnected
                    while True:
                        try:
                            self.sweep_threads[i].select_next_terminal()
                        except PortDisconnectedError as error:
                            self.sweep_threads[i].stop_blinking()
                            self.sig_error.emit(error.strerror)
                        else:
                            break
                except StopIteration:  # run out of enabled terminals
                    self.sweep_threads[i].stop_blinking()
                    del self.sweep_threads[i]
                except IOError:  # can't connect to board
                    self.sweep_threads[i].stop_blinking()
                    self.sig_error.emit('Board {0} IO failure'.format(self.sweep_threads[i].tab.board().address()))
                    del self.sweep_threads[i]
            # start all threads together
            for sweep_thread in self.sweep_threads:
                sweep_thread.start()
            # wait for them all to stop before carrying on
            for sweep_thread in self.sweep_threads:
                sweep_thread.wait()
            if self.quit_now:
                return

    # request stop
    def quit(self):
        self.quit_now = True
        # pass request down
        for sweep_thread in self.sweep_threads:
            sweep_thread.quit()


# thread for doing a sweep on a single board
class SweepThread(QThread):
    sig_new_data = pyqtSignal(datetime, Board.Mux.Port.Channel.Terminal, dict, name='new_data')
    sig_error = pyqtSignal(str, name='error')
    sig_blink_labels = pyqtSignal(bool, name='blink_labels')
    sig_blink_label = pyqtSignal(bool, Board.Mux.Port.Channel.Terminal, name='blink_label')
    sig_select = pyqtSignal(Board.Mux.Port.Channel.Terminal, name='select')

    def __init__(self, time, start_freq, final_freq, samples, logarithmic, tab: BoardTab, parent=None):
        super().__init__(parent)
        self.time = time
        self.start_freq = start_freq
        self.final_freq = final_freq
        self.samples = samples
        self.logarithmic = logarithmic
        self.tab = tab
        self.terminals = iter(tab.enabled_terminals())
        self.quit_now = False
        self.tab.board().quit_now = False
        self.sig_new_data.connect(tab.new_data)
        self.sig_error.connect(error_dialog.update_message)
        self.sig_blink_labels.connect(tab.blink, Qt.BlockingQueuedConnection)
        self.sig_blink_label.connect(tab.blink, Qt.BlockingQueuedConnection)
        self.sig_select.connect(tab.select, Qt.BlockingQueuedConnection)

    def run(self):
        error_msg = None

        # try to recover once after a failure
        for tries in range(2):
            try:
                while not self.quit_now:
                    if self.logarithmic:
                        results = {}
                        for freq in logspace(log10(self.start_freq), log10(self.final_freq), self.samples+1):
                            results.update(self.tab.board().sweep(freq, 0, 0))
                    else:
                        results = self.tab.board().sweep(
                            self.start_freq,
                            (self.final_freq - self.start_freq) / self.samples,
                            self.samples
                        )
                    if len(results) == self.samples+1:
                        self.sig_new_data.emit(self.time, self.tab.board().mux.selected(), results)
                        break
                    else:
                        print('Got {0} samples instead of {1}!'.format(len(results), self.samples+1))
                return
            except QuitNow:
                return
            except (TimeoutError, IOError) as error:
                if type(error) is IOError:
                    error_msg = 'Board {0} IO failure'.format(self.tab.board().address())
                else:
                    error_msg = str(error)

        # show the exception message
        self.sig_error.emit(error_msg)

    def stop_blinking(self):
        if not self.quit_now:
            # self.tab.blink(False)
            self.sig_blink_labels.emit(False)

    # get the next enabled terminal from the associated tab and select it
    def select_next_terminal(self):
        if not self.quit_now:
            terminal = next(self.terminals)
            self.sig_blink_labels.emit(False)
            self.tab.board().select()
            self.tab.board().mux.select(terminal)
            self.sig_blink_label.emit(True, terminal)

    # request stop
    def quit(self):
        self.quit_now = True
        # pass request down
        self.tab.board().quit_now = True


class BoardDetector:
    def __init__(self, board_tab_mgr: BoardTabManager):
        self.__board_tab_manager = board_tab_mgr
        self.__timer = QTimer()
        self.__timer.timeout.connect(self.__detect)
        self.__timer.setInterval(3000)

    def __detect(self):
        old_boards = [board_tab.board() for board_tab in self.__board_tab_manager]
        boards = []

        for board in old_boards:
            try:
                board.select()
            except IOError:
                pass
            else:
                boards.append(board)

        for address in [a for a in range(0, 8) if a not in [board.address() for board in old_boards]]:
            try:
                # try to connect
                boards.append(Board(address))

                message_box = QMessageBox(window)
                message_box.setText('Found board {0}, reading calibration constants...'.format(address))
                message_box.setWindowTitle('Detecting Boards')
                message_box.setModal(True)
                message_box.setStandardButtons(QMessageBox.NoButton)
                message_box.setIcon(QMessageBox.Information)

                # REVERT: address 7 bodge for testing legacy boards
                # if address == 7:
                #     boards[-1].interp_1x = boards[0].interp_1x
                #     boards[-1].interp_5x = boards[0].interp_5x
                #     message_box.close()
                #     continue

                # load calibration constants in a different thread
                thread = QThread()
                thread.run = boards[-1].load_calibration_constants
                thread.finished.connect(message_box.accept)
                thread.start()
                if message_box.exec() != QMessageBox.Accepted:
                    return
            except IOError:
                pass

        # add/remove tabs
        self.__board_tab_manager.update_tabs(boards)

    def start(self):
        self.__detect()
        self.__timer.start()

    def stop(self):
        self.__timer.stop()

    # boards = []
    # old_board_addresses = [board_tab.board().address() for board_tab in self.__board_tab_manager]
    #
    # for address in range(0, 8):
    #     try:
    #         # try to connect
    #         Board.select_board(address)
    #         boards.append(Board(address))
    #
    #         if address not in old_board_addresses:
    #             message_box = QMessageBox(window)
    #             message_box.setText('Found board {0}, reading calibration constants...'.format(address))
    #             message_box.setWindowTitle('Detecting Boards')
    #             message_box.setModal(True)
    #             message_box.setStandardButtons(QMessageBox.NoButton)
    #             message_box.setIcon(QMessageBox.Information)
    #
    #             # REVERT: address 7 bodge for testing legacy boards
    #             # if address == 7:
    #             #     boards[-1].interp_1x = boards[0].interp_1x
    #             #     boards[-1].interp_5x = boards[0].interp_5x
    #             #     message_box.close()
    #             #     continue
    #
    #             # load calibration constants in a different thread
    #             thread = QThread()
    #             thread.run = boards[-1].load_calibration_constants
    #             thread.finished.connect(message_box.accept)
    #             thread.start()
    #             if message_box.exec() != QMessageBox.Accepted:
    #                 return
    #     except IOError:
    #         pass
    #
    # print('old', old_board_addresses, 'new', [board.address() for board in boards])
    # if [board.address() for board in boards] != old_board_addresses:
    #     # add/remove tabs
    #     self.__board_tab_manager.update_tabs(boards)


# restore
def load_config(_board_tab_detector):
    data = {}
    try:
        with open('/home/pi/.settings.ini', 'r') as settings_file:
            data = json.load(settings_file)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        pass

    # noinspection PyUnreachableCode
    try:
        sweep_group.log_checkbox.setChecked(data.get('sweep_group.log_checkbox', False))
        schedule_group.delay_checkbox.setChecked(data.get('schedule_group.delay_checkbox', False))
        schedule_group.stop_checkbox.setChecked(data.get('schedule_group.stop_checkbox', False))
        sweep_group.start_field.setText(data.get('sweep_group.start_field', '1000'))
        sweep_group.final_field.setText(data.get('sweep_group.final_field', '100000'))
        sweep_group.samples_field.setText(data.get('sweep_group.samples_field', '198'))
        schedule_group.interval_field.setText(data.get('schedule_group.interval_field', '1'))
        schedule_group.delay_field.setText(data.get('schedule_group.delay_field', '1'))
        schedule_group.stop_field.setText(data.get('schedule_group.stop_field', '100'))
        log_group.directory_field.setText(data.get('log_group.directory_field', '/home/pi/Loc Control'))
        schedule_group.delay_combobox.setCurrentIndex(data.get('schedule_group.delay_combobox', 0))
        schedule_group.interval_combobox.setCurrentIndex(data.get('schedule_group.interval_combobox', 0))
        x_axis_group.frequency_radio.setChecked(data.get('x_axis_group.frequency_radio', True))
        x_axis_group.time_radio.setChecked(not data.get('x_axis_group.frequency_radio', True)),
        log_group.populate_combos(data.get('log_group.combo_values', [])),
        log_group.magnitude_combo.setCurrentIndex(data.get('log_group.magnitude_combo', -1)),
        log_group.phase_combo.setCurrentIndex(data.get('log_group.phase_combo', -1)),
    except ValueError:
        save_config()
        load_config(_board_tab_detector)
        return

    validate()
    _board_tab_detector.start()

    for board_tab in board_tab_manager:  # type: BoardTab
        for index, port_tab in board_tab.port_tabs.items():
            # port 'enabled' checkbox status stored as: board address -> port number -> 'port'
            try:
                port_tab.setChecked(data[str(board_tab.board().address())][str(index)]['port'])
            except (KeyError, ValueError, AttributeError):
                port_tab.setChecked(True)

            # channel 'enabled' checkbox status stored as: board address -> port number -> channel number
            for channel_index, channel in port_tab.channels.items():
                try:
                    channel.setChecked(data[str(board_tab.board().address())][str(index)][str(channel_index)])
                except (KeyError, ValueError, AttributeError):
                    channel.setChecked(True)


# save UI state to JSON file
def save_config():
    data = {
        'sweep_group.log_checkbox': sweep_group.log_checkbox.isChecked(),
        'schedule_group.delay_checkbox': schedule_group.delay_checkbox.isChecked(),
        'schedule_group.stop_checkbox': schedule_group.stop_checkbox.isChecked(),
        'sweep_group.start_field': sweep_group.start_field.text(),
        'sweep_group.final_field': sweep_group.final_field.text(),
        'sweep_group.samples_field': sweep_group.samples_field.text(),
        'schedule_group.interval_field': schedule_group.interval_field.text(),
        'schedule_group.delay_field': schedule_group.delay_field.text(),
        'schedule_group.stop_field': schedule_group.stop_field.text(),
        'log_group.directory_field': log_group.directory_field.text(),
        'schedule_group.delay_combobox': schedule_group.delay_combobox.currentIndex(),
        'schedule_group.interval_combobox': schedule_group.interval_combobox.currentIndex(),
        'x_axis_group.frequency_radio': x_axis_group.frequency_radio.isChecked(),
        'log_group.combo_values': log_group.combo_values,
        'log_group.magnitude_combo': log_group.magnitude_combo.currentIndex(),
        'log_group.phase_combo': log_group.phase_combo.currentIndex(),
    }

    for board_tab in board_tab_manager:  # type: BoardTab
        data[str(board_tab.board().address())] = {}
        for index, port_tab in board_tab.port_tabs.items():
            # port 'enabled' checkbox status stored as: board address -> port number -> 'port'
            data[str(board_tab.board().address())][str(index)] = {'port': port_tab.isChecked()}

            # channel 'enabled' checkbox status stored as: board address -> port number -> channel number
            for channel_index, channel in port_tab.channels.items():
                data[str(board_tab.board().address())][str(index)][str(channel_index)] = channel.isChecked()

    with open('/home/pi/.settings.ini', 'w') as settings_file:
        json.dump(data, settings_file)


# error dialog that must handle updating of error messages from several different threads
class ErrorDialog(QMessageBox):
    def __init__(self, parent):
        super().__init__(parent)
        self.error_set = set()
        self.setWindowTitle('Error')
        self.setModal(False)
        self.setStandardButtons(QMessageBox.Ok)
        self.setIcon(QMessageBox.Critical)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.finished.connect(self.error_set.clear)

    def update_message(self, error):
        self.error_set.add(error)  # atomic operation
        self.setText('\n'.join(sorted(self.error_set, key=str.lower)))
        self.show()


autostart_timer = QTimer()
autostart_timer.setSingleShot(True)

# user instructions for calibration
if len(sys.argv) > 1:
    if sys.argv[1] == '-autostart':
        autostart_timer.timeout.connect(start)
    else:
        try:
            cal_address = int(sys.argv[2])
        except (ValueError, IndexError):
            cal_address = None

        if len(sys.argv) == 3 and sys.argv[1] == '-calibrate' and cal_address is not None and 0 <= cal_address <= 7:
            try:
                input('Plug calibration breakout board into port 1 and press enter\n')
            except KeyboardInterrupt:
                exit()
            Board(cal_address).calibrate(Board.Mux.port1)
        else:
            print('Usage: LocControl.py [-autostart] or [-calibrate <board_address>]')
        exit()

# for key, value in os.environ.items():
#     print('{0}={1}'.format(key, value))

# make Qt application, set mouse cursor to waiting symbol and set the UI style
app = QApplication([])
app.setOverrideCursor(Qt.WaitCursor)
app.setStyle('cleanlooks')

# noinspection PyArgumentList
window = QWidget()
window.setWindowTitle('Loc Control')
window.showMaximized()

# do this to show the window to the user as early as possible
app.processEvents()

# make the UI
sweep_group = SweepGroup()
schedule_group = ScheduleGroup()
log_group = LogGroup()
x_axis_group = XAxisGroup()
fluidics_group = FluidicsGroup(window)
start_stop_button = StartStopButton()

sweep_group.log_checkbox.stateChanged.connect(validate)

sweep_group.start_field.textChanged.connect(validate_fast)
sweep_group.final_field.textChanged.connect(validate_fast)
sweep_group.samples_field.textChanged.connect(validate_fast)

sweep_group.start_field.editingFinished.connect(validate)
sweep_group.final_field.editingFinished.connect(validate)
sweep_group.samples_field.editingFinished.connect(validate)

# noinspection PyUnresolvedReferences
schedule_group.delay_combobox.currentIndexChanged.connect(validate)
# noinspection PyUnresolvedReferences
schedule_group.interval_combobox.currentIndexChanged.connect(validate)

schedule_group.delay_checkbox.stateChanged.connect(validate)
schedule_group.stop_checkbox.stateChanged.connect(validate)

schedule_group.interval_field.textChanged.connect(validate_fast)
schedule_group.delay_field.textChanged.connect(validate_fast)
schedule_group.stop_field.textChanged.connect(validate_fast)

schedule_group.interval_field.editingFinished.connect(validate)
schedule_group.delay_field.editingFinished.connect(validate)
schedule_group.stop_field.editingFinished.connect(validate)

log_group.directory_field.textChanged.connect(validate)
x_axis_group.frequency_radio.toggled.connect(validate)

start_stop_button.clicked.connect(start)
log_group.change_button.clicked.connect(change_log_directory)

settings_layout = QVBoxLayout()
# noinspection PyArgumentList
settings_layout.addWidget(sweep_group)
# noinspection PyArgumentList
settings_layout.addWidget(schedule_group)
settings_layout.addWidget(log_group)
settings_layout.addWidget(x_axis_group)
settings_layout.addWidget(fluidics_group)
# noinspection PyArgumentList
settings_layout.addWidget(start_stop_button)
settings_layout.setContentsMargins(0, 0, 0, 0)

# noinspection PyArgumentList
settings = QWidget()
settings.setLayout(settings_layout)
settings.setFixedWidth(250)
settings.setContentsMargins(0, 0, 0, 0)

board_tab_manager = BoardTabManager()
board_tab_manager.sig_small_screen.connect(set_small_screen)

window_layout = QHBoxLayout()
# noinspection PyArgumentList
window_layout.addWidget(settings)
# noinspection PyArgumentList
window_layout.addWidget(board_tab_manager, 0)

window.setLayout(window_layout)

# 1 Hz graph label blinking tick source
blink_timer = QTimer()
blink_timer.start(500)

error_dialog = ErrorDialog(window)

scheduler_thread = None

# process ample events to show load_config() dialog
app.processEvents()
app.restoreOverrideCursor()
board_detector = BoardDetector(board_tab_manager)
load_config(board_detector)

autostart_timer.start(10000)

exit(app.exec_())

from datetime import timedelta, datetime
import os
from time import sleep
import os.path
import sys
from numpy import logspace
from math import log10
from Board import Board, QuitNow, PortDisconnectedError
from itertools import count
import json
import matplotlib
import matplotlib.pyplot as plt
from PyQt5.QtCore import QSize, QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QIntValidator
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import QApplication, QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,\
                            QPushButton, QTabWidget, QStyle, QVBoxLayout, QWidget, QFormLayout, QMessageBox, QFileDialog

class BoardTabs(QTabWidget):
    class BoardTab(QTabWidget): # tab of port tabs
        class PortTab(QGroupBox): # tab of 16 graphs
            class ChannelWidget(QGroupBox): # pairs of graphs
                class TerminalLabel(QLabel): # label above graphs
                    def __init__(self, *__args):
                        super().__init__(*__args)
                        self.sizePolicy().setRetainSizeWhenHidden(True)
                        self.setAlignment(Qt.AlignHCenter)
                        board_tabs.sig_show_all_labels.connect(self.show) # connect signal handler to stop being hidden

                    def toggle_visibility(self):
                        self.setVisible(self.isHidden())

                def __init__(self, channel):
                    super().__init__('Channel {0}'.format(channel))
                    self.setAlignment(Qt.AlignHCenter)
                    self.setCheckable(True)
                    self.setChecked(True)

                    # initialise graphs
                    self.impedance_graph = QSvgWidget(ROOT_DIR + 'no_data.svg')
                    self.reference_graph = QSvgWidget(ROOT_DIR + 'no_data.svg')

                    self.impedance_label = self.TerminalLabel('Impedance')
                    self.reference_label = self.TerminalLabel('Reference')

                    layout = QGridLayout()
                    # noinspection PyArgumentList
                    layout.addWidget(self.impedance_label, 0, 0)
                    # noinspection PyArgumentList
                    layout.addWidget(self.reference_label, 0, 1)
                    # noinspection PyArgumentList
                    layout.addWidget(self.impedance_graph, 1, 0)
                    # noinspection PyArgumentList
                    layout.addWidget(self.reference_graph, 1, 1)
                    self.setLayout(layout)

            def __init__(self):
                super().__init__('Enabled')
                self.setCheckable(True)
                layout = QGridLayout()

                # store my ChannelWidgets
                self.channels = {}
                for channel in range(1, 9):
                    self.channels[channel] = self.ChannelWidget(channel)
                    # noinspection PyArgumentList
                    layout.addWidget(self.channels[channel], (channel-1) // 2, (channel-1) % 2)

                self.setLayout(layout)

            def __iter__(self): # make iterable, return iterator over my ChannelWidgets
                return iter(self.channels.values())

        def __init__(self, board: Board, parent=None):
            super().__init__(parent)
            self.__board = board

            # store my PortTabs
            self.port_tabs = {}
            for port in range(1, 5):
                self.port_tabs[port] = self.PortTab()
                self.addTab(self.port_tabs[port], 'Port {0}'.format(port))

        def __iter__(self): # make iterable, return iterator over my PortTabs
            return iter([self.widget(i) for i in range(self.count())])

        def select(self, terminal): # select board and terminal WITHOUT MUTEX!
            self.board().select()
            self.board().mux.select(terminal)
            self.blink(True, terminal)

        def blink(self, blink, terminal=None): # enable or disable blinking one or all labels
            if terminal is None:
                terminals = self.terminals()
            else:
                terminals = [terminal]

            for terminal in terminals:
                if terminal.is_reference:
                    label = self.port_tabs[terminal.port].channels[terminal.channel].reference_label
                else:
                    label = self.port_tabs[terminal.port].channels[terminal.channel].impedance_label

                if blink:
                    blink_timer.timeout.connect(label.toggle_visibility)
                else:
                    try:
                        blink_timer.timeout.disconnect(label.toggle_visibility)
                    except TypeError:
                        pass
                    label.show()

        def terminals(self): # return list of enabled terminals across all enabled ports
            terminals = []
            for port in self.__board.mux:
                for channel in port:
                    for terminal in channel:
                        if self.port_tabs[terminal.port].isChecked():
                            if self.port_tabs[terminal.port].channels[terminal.channel].isChecked():
                                terminals.append(terminal)
            return terminals

        def new_data(self, time, terminal, results: dict, raw_results: dict=None):
            self.blink(False, terminal)

            # REVERT: result printing
            # real = self.board().real
            # imag = self.board().imag
            # magnitudes = self.board().magnitudes

            # print('Got {0} samples from board {1} port {2} channel {3} terminal {4}'.format(len(results), self.__board.address(), terminal.port, terminal.channel, 'reference' if terminal.is_reference else 'impedance'))

            frequencies, impedances, phases = [], [], []
            for f, (i, p) in sorted(results.items()):
                frequencies.append(f)
                impedances.append(i)
                phases.append(p)

            # REVERT: result printing
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

            log_filename = log_layout.field.text() + '/board{0}_port{1}_channel{2}_{3}'.format(self.board().address(), terminal.port, terminal.channel, 'reference' if terminal.is_reference else 'impedance')
            if not os.path.exists(log_filename):
                with open(log_filename, 'a+') as log_file:
                    log_file.write('Board: {0}\n'.format(self.board().address()))
                    log_file.write('Port: {0}\n'.format(terminal.port))
                    log_file.write('Channel: {0}\n'.format(terminal.channel))
                    log_file.write('{0} terminal\n'.format('Reference' if terminal.is_reference else 'Impedance'))
                    log_file.write('\n')
                    log_file.write('Time Initiated (UTC)\tFrequency (Hz)\tMagnitude (Ω)\tPhase (º)\n')

            with open(log_filename, 'a+') as log_file:
                for f, (i, p) in sorted(results.items()):
                    log_file.write('{0}\t{1: <8g}\t{2: <8g}\t{3:+g}\n'.format(time.strftime('%Y-%m-%d %H:%M'), f, float('{:.4g}'.format(i)), p,))
                log_file.write('\n')

            # REVERT: raw data save
            # if raw_results is not None:
            #     raw_log_filename = log_layout.field.text() + '/.board{0}_port{1}_channel{2}_{3}'.format(self.board().address(), terminal.port, terminal.channel, 'reference' if terminal.is_reference else 'impedance')
            #     with open(raw_log_filename, 'a+') as log_file:
            #         log_file.write('{0}\t'.format(time.strftime('%Y-%m-%d %H:%M')))
            #         json.dump(raw_results, log_file)
            #         log_file.write('\n')

            fig, ax1 = plt.subplots(dpi=40)  # type: (plt.Figure, plt.Axes)
            fig.tight_layout()
            fig.set_size_inches(5, 3)

            ax1.plot(frequencies, impedances, 'b-')
            ax1.set_xlabel('Frequency (Hz)')
            # Make the y-axis label, ticks and tick labels match the line color.
            ax1.set_ylabel('Magnitude (Ω)', color='b')
            ax1.tick_params('y', colors='b')
            ax1.set_ylim(0, 10000)
            ax1.set_xlim(min(frequencies), max(frequencies))
            ax1.set_xscale('log')

            ax2 = ax1.twinx()
            ax2.plot(frequencies, phases, 'r-')
            ax2.set_ylabel('phase (degrees)', color='r')
            ax2.tick_params('y', colors='r')
            ax2.set_ylim(-90, 90)
            ax2.set_yticks([-90, -60, -30, 0, 30, 60, 90])
            filename = ROOT_DIR + '{0}_{1}_{2}_{3}.svg'.format(
                self.__board.address(), terminal.port, terminal.channel, 'r' if terminal.is_reference else 'i'
            )
            fig.savefig(filename, bbox_inches='tight', transparent=True, dpi=40)
            plt.close(fig)

            if terminal.is_reference:
                self.port_tabs[terminal.port].channels[terminal.channel].reference_graph.load(filename)
            else:
                self.port_tabs[terminal.port].channels[terminal.channel].impedance_graph.load(filename)

        def board(self):
            return self.__board

    sig_show_all_labels = pyqtSignal(name='show_all_labels')

    # make 'No Data' graph
    def __init__(self):
        super().__init__()

        frequencies = range(1000, 100000)

        fig, ax1 = plt.subplots(dpi=40)  # type: (plt.Figure, plt.Axes)
        fig.tight_layout()
        fig.set_size_inches(5, 3)

        ax1.set_xlabel('Frequency (Hz)')
        # Make the y-axis label, ticks and tick labels match the line color.
        ax1.set_ylabel('Magnitude (Ω)', color='b')
        ax1.tick_params('y', colors='b')
        ax1.set_ylim(0, 10000)
        ax1.set_xlim(min(frequencies), max(frequencies))
        ax1.set_xscale('log')

        ax2 = ax1.twinx()
        ax2.set_ylabel('phase (degrees)', color='r')
        ax2.tick_params('y', colors='r')
        ax2.set_ylim(-90, 90)
        ax2.set_yticks([-90, -60, -30, 0, 30, 60, 90])

        fig.text(0.5, 0.5, 'No data', horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes, fontsize=30)
        filename = ROOT_DIR + 'no_data.svg'
        fig.savefig(filename, bbox_inches='tight', transparent=True, dpi=40)
        plt.close(fig)

    # add/remove tabs according to the list of Boards provided
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
                    elif i == self.count()-1:
                        i += 1
                self.insertTab(i, self.BoardTab(board, parent=self), 'Board {0}'.format(board.address()))

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
        for board_tab in self:  # type: BoardTabs.BoardTab
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
    def __init__(self):
        super().__init__('Schedule')

        self.interval_label = QLabel('Sweep every')
        self.interval_field = QLineEdit()
        self.interval_field.setMaxLength(2)
        self.interval_field.setValidator(QIntValidator(0, 99))
        self.interval_combobox = QComboBox()
        self.interval_combobox.addItems(['h', 'm', 's'])
        self.interval_layout = QHBoxLayoutWithError(self.interval_field, self.interval_combobox, error='Range: 0 - 24 hours')
        self.interval = None

        self.delay_checkbox = QCheckBox('Start in')
        self.delay_field = QLineEdit()
        self.delay_field.setMaxLength(2)
        self.delay_field.setValidator(QIntValidator(0, 99))
        self.delay_combobox = QComboBox()
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

# Subclass of QHBoxLayout with error symbol built-in
class QHBoxLayoutWithError(QHBoxLayout):
    class ErrorLabel(QLabel):
        def __init__(self, application, text=None):
            super().__init__()
            if text is not None:
                self.setToolTip(text)
            self.setPixmap(application.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(QSize(16, 16)))

        # def enterEvent(self, QEvent):
        #     super().enterEvent(QEvent)
        #     # super().toolTipDuration()
        #     QToolTip.showText(self.pos(), None, super.view)

    def __init__(self, *widgets, stretch=False, error=None):
        super().__init__()
        for widget in widgets:
            # noinspection PyArgumentList
            self.addWidget(widget)
        if stretch:
            self.addStretch()
        self.__error_label = self.ErrorLabel(app, error)
        # noinspection PyArgumentList
        self.addWidget(self.__error_label)

    def show_error(self, show=True, text=None):
        if text is not None:
            self.__error_label.setToolTip(text)
        if show:
            self.__error_label.show()
        else:
            self.__error_label.hide()

    def hide_error(self, hide=True):
        self.show_error(not hide)

# make 'Sweep' UI
class SweepGroup(QGroupBox):
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

# make 'Log' UI
class LogLayout(QHBoxLayoutWithError):
    def __init__(self):
        self.field = QLineEdit('Results')
        self.field.setReadOnly(True)
        self.button = QPushButton('Change...')
        super().__init__(QLabel('Log'), self.field, self.button)

# change log directory button handler
def change_log_directory():
    # noinspection PyArgumentList,PyCallByClass
    log_layout.field.setText(QFileDialog.getExistingDirectory(window, directory=log_layout.field.text()))

# check all input data is ok
def validate():
    # are there any boards discovered
    valid = len(board_tabs.tab_list()) > 0

    # check log directory access
    try:
        with open(log_layout.field.text()+'/.test', 'a+') as file:
            file.write('\n')
        os.remove(log_layout.field.text()+'/.test')
    except OSError as error:
        log_layout.show_error(text=os.strerror(error.errno))
        valid = False
    else:
        log_layout.hide_error()

    # check all 'Sweep' fields
    for layout, field in [(sweep_group.start_layout, sweep_group.start_field),
                   (sweep_group.final_layout, sweep_group.final_field),
                   (sweep_group.samples_layout, sweep_group.samples_field)]:
        layout.hide_error(field.hasAcceptableInput())
        valid &= field.hasAcceptableInput()

    # fill 'Step' field unless 'Logarithmic' checkbox is checked, then just empty and disable it
    if sweep_group.log_checkbox.isChecked():
        sweep_group.increment_label.setDisabled(True)
        sweep_group.increment_field.setText('')
        sweep_group.increment_layout.hide_error()
    else:
        sweep_group.increment_label.setEnabled(True)
        try:
            if int(sweep_group.final_field.text()) == int(sweep_group.start_field.text()):
                increment = 0
            else:
                increment = (int(sweep_group.final_field.text()) - int(sweep_group.start_field.text())) / int(sweep_group.samples_field.text())
            increment_text = '{: <8}'.format(increment)[:7]
            if float(increment_text) == int(increment):
                increment_text = str(int(increment))
            sweep_group.increment_field.setText(increment_text)
            accept = (0 <= increment <= 62000)
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

    # calculate schedule delay and verify it's less than 24 hours
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

    update_timer(schedule_group.start)

    # check stop field
    if schedule_group.stop_checkbox.isChecked() and not schedule_group.stop_field.hasAcceptableInput():
        valid = False
        schedule_group.stop_layout.show_error()
    else:
        schedule_group.stop_layout.hide_error()

    return valid

# enable/disable/change parts of the UI when acquisition is started and stopped
def set_controls(started):
    start_stop_button.setText('STOP' if started else 'START')

    # change start/stop button colour
    # noinspection PyShadowingNames
    pal = start_stop_button.palette()
    pal.setColor(pal.Button, Qt.red if started else Qt.green)
    start_stop_button.setPalette(pal)
    start_stop_button.update()

    # parts of the UI to 'de-grey' when they're disabled
    unmute = [
        sweep_group.start_field,
        sweep_group.samples_field,
        sweep_group.final_field,
        schedule_group.interval_field,
        schedule_group.interval_combobox,
        log_layout.field
    ]

    # parts of the UI to disable
    # noinspection PyTypeChecker
    disable = unmute + [
        sweep_group.log_checkbox,
        schedule_group.delay_checkbox,
        schedule_group.stop_checkbox,
        log_layout.button,
        detect_boards_button
    ]

    # disable all port tabs, unmute enabled tabs and channels
    for board_tab in board_tabs:
        for port_tab in board_tab:  # type: BoardTabs.PortTab
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

    # do the unmuting
    for widget in unmute:
        widget.setStyleSheet('' if not started else
                             'color: black; '
                             'QComboBox { color: black; }; '
                             'QCheckBox { color: black; }; '
                             'QLabel { color: black; }; '
                             'QCheckBox::QLabel { color: black; }; '
                             'QWidget { color: black; }; '
                             'QListView { color: black; }; ')

# start button handler
def start():
    # save setup
    save_config()
    # check connections
    errors = '\n'.join(board_tabs.test_connection())

    if len(errors) > 0:
        # noinspection PyArgumentList,PyCallByClass
        QMessageBox.critical(window, 'Connection Error', errors)
    elif validate():
        set_controls(True)

        # disable start button for now
        # noinspection PyUnresolvedReferences
        start_stop_button.clicked.disconnect()

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
            board_tabs.tab_list()
        )

        # connect signals for timer and stopping
        scheduler_thread.sig_update_timer.connect(update_timer)
        scheduler_thread.sig_done.connect(stop)
        scheduler_thread.start()
        # re-enable start button, change function to stop
        start_stop_button.clicked.connect(stop)

# stop button handler
def stop():
    # disable stop button for now
    # noinspection PyUnresolvedReferences
    start_stop_button.clicked.disconnect()

    # make it a yellow stopping button
    start_stop_button.setText('STOPPING')
    # noinspection PyShadowingNames
    pal = start_stop_button.palette()
    pal.setColor(pal.Button, Qt.yellow)
    start_stop_button.setPalette(pal)
    start_stop_button.repaint()

    # disconnect the time or else it keeps interfering
    scheduler_thread.sig_update_timer.disconnect(update_timer)
    # ask the SchedulerThread to stop
    scheduler_thread.quit()
    # stop all labels blinking
    try:
        blink_timer.disconnect()
    except TypeError: # no connected listeners
        pass
    board_tabs.sig_show_all_labels.emit()

    validate()
    # re-enable stop button and change function to start
    set_controls(False)
    start_stop_button.clicked.connect(start)

# def start_stop():
#     if 'started' not in start_stop.__dict__: start_stop.started = False
#     if not start_stop.started:
#         save_config()
#         errors = '\n'.join(board_tabs.test_connection())
#     else:
#         errors = ''
# 
#     if len(errors) > 0:
#         # noinspection PyArgumentList,PyCallByClass
#         QMessageBox.critical(window, 'Connection Error', errors)
#     elif validate():
#         if len(board_tabs.tab_list()) == 0:
#             return
#         start_stop.started = not start_stop.started
# 
#         start_stop_button.setEnabled(start_stop.started)
#         start_stop_button.repaint()
#         start_stop_button.setText('STOP' if start_stop.started else 'START')
# 
#         # noinspection PyShadowingNames
#         pal = start_stop_button.palette()
#         pal.setColor(pal.Button, Qt.red if start_stop.started else Qt.green)
#         start_stop_button.setPalette(pal)
#         start_stop_button.update()
# 
#         unmute = [
#             sweep_group.start_field,
#             sweep_group.samples_field,
#             sweep_group.final_field,
#             schedule_group.interval_field,
#             schedule_group.interval_combobox,
#             log_layout.field
#         ]
# 
#         # noinspection PyTypeChecker
#         disable = unmute + [
#             sweep_group.log_checkbox,
#             schedule_group.delay_checkbox,
#             schedule_group.stop_checkbox,
#             log_layout.button,
#             detect_boards_button
#         ]
# 
#         for board_tab in board_tabs:
#             for port_tab in board_tab:  # type: BoardTabs.PortTab
#                 disable += [port_tab]
#                 if port_tab.isChecked():
#                     unmute += [port_tab]
#                     disable += [channel for channel in port_tab.channels.values()]
#                     # unmute += [channel for channel in port_tab.channels.values() if channel.isChecked()]
# 
#         if sweep_group.log_checkbox.isChecked():
#             unmute += [sweep_group.log_checkbox]
# 
#         if schedule_group.delay_checkbox.isChecked():
#             unmute += [schedule_group.delay_checkbox, schedule_group.delay_field, schedule_group.delay_combobox]
#             disable += [schedule_group.delay_field, schedule_group.delay_combobox]
# 
#         if schedule_group.stop_checkbox.isChecked():
#             unmute += [schedule_group.stop_checkbox, schedule_group.stop_field, schedule_group.stop_label]
#             disable += [schedule_group.stop_field, schedule_group.stop_label]
# 
#         for widget in disable:
#             widget.setDisabled(start_stop.started)
# 
#         for widget in unmute:
#             widget.setStyleSheet('' if not start_stop.started else
#                                  'color: black; '
#                                  'QComboBox { color: black; }; '
#                                  'QCheckBox { color: black; }; '
#                                  'QLabel { color: black; }; '
#                                  'QCheckBox::QLabel { color: black; }; '
#                                  'QWidget { color: black; }; '
#                                  'QListView { color: black; }; ')
# 
#         if start_stop.started:
#             sweeps = int(schedule_group.stop_field.text()) if schedule_group.stop_checkbox.isChecked() else None
# 
#             global scheduler_thread
#             scheduler_thread = SchedulerThread(
#                 int(sweep_group.start_field.text()),
#                 int(sweep_group.final_field.text()),
#                 int(sweep_group.samples_field.text()),
#                 sweep_group.log_checkbox.isChecked(),
#                 schedule_group.interval,
#                 schedule_group.start,
#                 sweeps,
#                 board_tabs.tab_list()
#             )
# 
#             scheduler_thread.sig_update_timer.connect(update_timer)
#             scheduler_thread.sig_done.connect(start_stop)
#             scheduler_thread.start()
#         else:
#             scheduler_thread.sig_update_timer.disconnect(update_timer)
#             scheduler_thread.quit()
#             validate()
#             try:
#                 blink_timer.disconnect()
#             except TypeError:
#                 pass
#             board_tabs.sig_show_all_labels.emit()
#             start_stop_button.setEnabled(True)

# thread that handles timings in between sweeps
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
                sleep(0.1)
            next_time += self.__period

            # make sure MuxThread is finished
            self.__mux_thread.wait()
            if self.quit_now:
                return
            self.__mux_thread = MuxThread(datetime.utcnow(), self.__start_freq, self.__final_freq, self.__samples, self.__logarithmic, self.__tabs)
            self.__mux_thread.start()

        self.__mux_thread.wait()
        if not self.quit_now:
            self.sig_done.emit()

    # request stop
    def quit(self):
        self.quit_now = True
        # pass request down
        self.__mux_thread.quit()
        self.wait()

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
                            break
                        except PortDisconnectedError as error:
                            self.sweep_threads[i].tab.blink(False)
                            self.sig_error.emit(error.strerror)
                except StopIteration: # run out of enabled terminals
                    self.sweep_threads[i].tab.blink(False)
                    del self.sweep_threads[i]
                except IOError: # can't connect to board
                    self.sweep_threads[i].tab.blink(False)
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
        self.wait()

# thread for doing a sweep on a single board
class SweepThread(QThread):
    # emit this when a sweep is done
    sig_new_data = pyqtSignal(datetime, Board.Mux.Port.Channel.Terminal, dict, name='new_data')
    sig_error = pyqtSignal(str, name='error')

    def __init__(self, time, start_freq, final_freq, samples, logarithmic, tab: BoardTabs.BoardTab, parent=None):
        super().__init__(parent)
        self.time = time
        self.start_freq = start_freq
        self.final_freq = final_freq
        self.samples = samples
        self.logarithmic = logarithmic
        self.tab = tab
        self.terminals = iter(tab.terminals())
        self.quit_now = False
        self.tab.board().quit_now = False
        self.sig_new_data.connect(tab.new_data)
        self.sig_error.connect(error_dialog.update_message)

    def run(self):
        error_msg = None

        # try to recover once after a failure
        for tries in range(2):
            try:
                if self.quit_now:
                    return
                elif self.logarithmic: # log sweep
                    results = {}
                    for freq in logspace(log10(self.start_freq), log10(self.final_freq), self.samples):
                        results.update(self.tab.board().sweep(freq, 0, 0))
                    self.sig_new_data.emit(self.time, self.tab.board().mux.selected(), results)
                else:
                    self.sig_new_data.emit(self.time, self.tab.board().mux.selected(), self.tab.board().sweep(self.start_freq, (self.final_freq - self.start_freq) / self.samples, self.samples))
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

    # get the next enabled terminal from the associated tab and select it
    def select_next_terminal(self):
        self.tab.blink(False)
        self.tab.select(next(self.terminals))

    # request stop
    def quit(self):
        self.quit_now = True
        # pass request down
        self.tab.board().quit_now = True
        self.wait()

# update countdown timer
def update_timer(time: timedelta):
    if time is None:
        schedule_group.next_field.setText('')
    else:
        hours, remainder = divmod(time.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        schedule_group.next_field.setText('{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds)))

# try to find boards
def detect_boards():
    boards = []
    for address in range(0, 8):
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
                return []
        except IOError:
            pass

    # add/remove tabs
    board_tabs.update_tabs(boards)

# restore
def load_config():
    data = {}
    try:
        with open('/home/pi/.loc_settings.ini', 'r') as settings_file:
            data = json.load(settings_file)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        pass

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
        log_layout.field.setText(data.get('log_layout.field', '/home/pi/Loc Control'))
        schedule_group.delay_combobox.setCurrentIndex(data.get('schedule_group.delay_combobox', 0))
        schedule_group.interval_combobox.setCurrentIndex(data.get('schedule_group.interval_combobox', 0))
    except ValueError:
        save_config()
        load_config()
        return

    validate()
    detect_boards()

    for board_tab in board_tabs:  # type: BoardTabs.BoardTab
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

#save UI state to JSON file
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
        'log_layout.field': log_layout.field.text(),
        'schedule_group.delay_combobox': schedule_group.delay_combobox.currentIndex(),
        'schedule_group.interval_combobox': schedule_group.interval_combobox.currentIndex(),
    }

    for board_tab in board_tabs:  # type: BoardTabs.BoardTab
        data[str(board_tab.board().address())] = {}
        for index, port_tab in board_tab.port_tabs.items():
            # port 'enabled' checkbox status stored as: board address -> port number -> 'port'
            data[str(board_tab.board().address())][str(index)] = {'port': port_tab.isChecked()}

            # channel 'enabled' checkbox status stored as: board address -> port number -> channel number
            for channel_index, channel in port_tab.channels.items():
                data[str(board_tab.board().address())][str(index)][str(channel_index)] = channel.isChecked()

    with open('/home/pi/.loc_settings.ini', 'w') as settings_file:
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
        self.error_set.add(error) # atomic operation
        self.setText('\n'.join(sorted(self.error_set, key=str.lower)))
        self.show()

# user instructions for calibration
if len(sys.argv) > 1:
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
        print('Usage: LocControl.py [-calibrate <board_address>]')
    exit()

matplotlib.use('Qt5Agg')

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

# location of graph image files
ROOT_DIR = '/tmp/LocControl/'
os.makedirs(ROOT_DIR, exist_ok=True)

# make the UI
sweep_group = SweepGroup()
schedule_group = ScheduleGroup()
log_layout = LogLayout()
detect_boards_button = QPushButton('Detect Boards')
start_stop_button = QPushButton('START')
start_stop_button.setSizePolicy(start_stop_button.sizePolicy().Expanding, start_stop_button.sizePolicy().Expanding)
start_stop_button.setDefault(True)
start_stop_button.setAutoDefault(True)
start_stop_button.setAutoFillBackground(True)

pal = start_stop_button.palette()
pal.setColor(pal.Button, Qt.green)
start_stop_button.setPalette(pal)

font = start_stop_button.font()
font.setPointSize(24)
start_stop_button.setFont(font)

start_stop_button.update()

sweep_group.log_checkbox.stateChanged.connect(validate)
sweep_group.start_field.textChanged.connect(validate)
sweep_group.final_field.textChanged.connect(validate)
sweep_group.samples_field.textChanged.connect(validate)
schedule_group.delay_combobox.currentIndexChanged.connect(validate)
schedule_group.interval_combobox.currentIndexChanged.connect(validate)
schedule_group.delay_checkbox.stateChanged.connect(validate)
schedule_group.stop_checkbox.stateChanged.connect(validate)
schedule_group.interval_field.textChanged.connect(validate)
schedule_group.delay_field.textChanged.connect(validate)
schedule_group.stop_field.textChanged.connect(validate)
log_layout.field.textChanged.connect(validate)

start_stop_button.clicked.connect(start)
detect_boards_button.clicked.connect(detect_boards)
log_layout.button.clicked.connect(change_log_directory)

settings_layout = QVBoxLayout()
# noinspection PyArgumentList
settings_layout.addWidget(sweep_group)
# noinspection PyArgumentList
settings_layout.addWidget(schedule_group)
settings_layout.addLayout(log_layout)
# noinspection PyArgumentList
settings_layout.addWidget(detect_boards_button)
# noinspection PyArgumentList
settings_layout.addWidget(start_stop_button)
settings_layout.setContentsMargins(0, 0, 0, 0)

# noinspection PyArgumentList
settings = QWidget()
settings.setLayout(settings_layout)
settings.setFixedWidth(250)
settings.setContentsMargins(0, 0, 0, 0)

board_tabs = BoardTabs()

window_layout = QHBoxLayout()
# noinspection PyArgumentList
window_layout.addWidget(settings)
# noinspection PyArgumentList
window_layout.addWidget(board_tabs, 0)

window.setLayout(window_layout)

# 1 Hz graph label blinking tick source
blink_timer = QTimer()
blink_timer.start(500)

error_dialog = ErrorDialog(window)

# process ample events to show load_config() dialog
app.processEvents()
app.restoreOverrideCursor()
load_config()

exit(app.exec_())
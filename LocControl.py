from datetime import timedelta, datetime
import os
from time import sleep
import os.path

import matplotlib.pyplot as plt
from PyQt5.QtCore import QSize, QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QIntValidator
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import QApplication, QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,\
                            QPushButton, QTabWidget, QStyle, QVBoxLayout, QWidget, QFormLayout, QMessageBox, QFileDialog

from Board import Board, QuitNow, PortDisconnectedError
import json

class BoardTabs(QTabWidget):
    class BoardTab(QTabWidget):
        class PortTab(QGroupBox):
            class ChannelWidget(QGroupBox):
                def __init__(self, channel):
                    super().__init__('Channel {0}'.format(channel))
                    self.setAlignment(Qt.AlignHCenter)

                    self.impedance_graph = QSvgWidget(ROOT_DIR + 'no_data.svg')
                    self.reference_graph = QSvgWidget(ROOT_DIR + 'no_data.svg')

                    impedance_label = QLabel('Impedance')
                    reference_label = QLabel('Reference')
                    impedance_label.setAlignment(Qt.AlignHCenter)
                    reference_label.setAlignment(Qt.AlignHCenter)

                    layout = QGridLayout()
                    # noinspection PyArgumentList
                    layout.addWidget(impedance_label, 0, 0)
                    # noinspection PyArgumentList
                    layout.addWidget(reference_label, 0, 1)
                    # noinspection PyArgumentList
                    layout.addWidget(self.impedance_graph, 1, 0)
                    # noinspection PyArgumentList
                    layout.addWidget(self.reference_graph, 1, 1)
                    self.setLayout(layout)

            def __init__(self):
                super().__init__('Enabled')
                self.setCheckable(True)
                layout = QGridLayout()
                self.channels = {}
                for channel in range(1, 9):
                    self.channels[channel] = self.ChannelWidget(channel)
                    # noinspection PyArgumentList
                    layout.addWidget(self.channels[channel], (channel-1) // 2,(channel-1) % 2)

                self.setLayout(layout)

        def __init__(self, board: Board, parent=None):
            super().__init__(parent)
            self.__board = board
            self.port_tabs = {}
            for port in range(1, 5):
                self.port_tabs[port] = self.PortTab()
                self.addTab(self.port_tabs[port], 'Port {0}'.format(port))

        def terminals(self):
            terminals = []
            for port in self.__board.mux:
                for channel in port:
                    for terminal in channel:
                        if self.port_tabs[terminal.port].isChecked():
                        # if self.widget(terminal.port - 1).isChecked():
                            terminals.append(terminal)
            return terminals

        def new_data(self, time, terminal, results: dict):
            print('Got {0} samples from board {1} port {2} channel {3} terminal {4}'.format(len(results), self.__board.address(), terminal.port, terminal.channel, 'reference' if terminal.is_reference else 'impedance'))
            frequencies, impedances, phases = [], [], []
            for f, (i, p) in sorted(results.items()):
                frequencies.append(f)
                impedances.append(i)
                phases.append(p)

            log_filename = log_layout.field.text() + '/board{0}_port{1}_channel{2}_{3}'.format(self.board().address(), terminal.port, terminal.channel, 'reference' if terminal.is_reference else 'impedance')
            if not os.path.exists(log_filename):
                with open(log_filename, 'a+') as log_file:
                    log_file.write('Board: {0}\n'.format(self.board().address()))
                    log_file.write('Port: {0}\n'.format(terminal.port))
                    log_file.write('Channel: {0}\n'.format(terminal.channel))
                    log_file.write('{0} terminal\n'.format('Reference' if terminal.is_reference else 'Impedance'))
                    log_file.write('\n')
                    log_file.write('Time Initiated (UTC)\tFrequency (Hz)\tImpedance (Ω)\tPhase (º)\n')

            with open(log_filename, 'a+') as log_file:
                for f, (i, p) in sorted(results.items()):
                    log_file.write('{0}\t{1}\t{2}\t{3}\n'.format(time.strftime('%Y-%m-%d %H:%M'), f, i, p,))
                log_file.write('\n')

            # TODO: adjust graph DPI to be visible

            fig, ax1 = plt.subplots()
            ax1.plot(frequencies, impedances, 'b-')
            ax1.set_xlabel('frequency (Hz)')
            # Make the y-axis label, ticks and tick labels match the line color.
            ax1.set_ylabel('impedance (Ω)', color='b')
            ax1.tick_params('y', colors='b')
            ax1.set_ylim(0, 10000)
            ax1.set_xlim(min(frequencies), max(frequencies))

            ax2 = ax1.twinx()
            ax2.plot(frequencies, phases, 'r-')
            ax2.set_ylabel('phase (degrees)', color='r')
            ax2.tick_params('y', colors='r')
            ax2.set_ylim(-180, 180)

            fig.tight_layout()
            filename = ROOT_DIR + '{0}_{1}_{2}_{3}.svg'.format(
                self.__board.address(), terminal.port, terminal.channel, 'r' if terminal.is_reference else 'i'
            )
            fig.savefig(filename, bbox_inches='tight', transparent=True)
            plt.close(fig)
            if terminal.is_reference:
                self.port_tabs[terminal.port].channels[terminal.channel].reference_graph.load(filename)
            else:
                self.port_tabs[terminal.port].channels[terminal.channel].impedance_graph.load(filename)


        def board(self):
            return self.__board

    def __init__(self):
        super().__init__()

        frequencies = range(1000, 100000)

        fig, ax1 = plt.subplots()
        ax1.set_xlabel('frequency (Hz)')
        # Make the y-axis label, ticks and tick labels match the line color.
        ax1.set_ylabel('impedance (Ω)', color='b')
        ax1.tick_params('y', colors='b')
        ax1.set_ylim(0, 10000)
        ax1.set_xlim(min(frequencies), max(frequencies))

        ax2 = ax1.twinx()
        ax2.set_ylabel('phase (degrees)', color='r')
        ax2.tick_params('y', colors='r')
        ax2.set_ylim(-180, 180)

        fig.tight_layout()
        fig.text(0.5, 0.5, 'No data', horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes, fontsize=40)
        filename = ROOT_DIR + 'no_data.svg'
        fig.savefig(filename, bbox_inches='tight', transparent=True)
        plt.close(fig)

    def update_tabs(self, boards):
        for i in range(self.count() - 1, -1, -1):
            if self.widget(i).board().address() not in (board.address() for board in boards):
                self.removeTab(i)

        for board in boards:
            if board.address() not in (self.widget(i).board().address() for i in range(self.count())):
                i = 0
                for i in range(self.count()):
                    if i+1 == self.count() or board.address() < self.widget(i + 1).board().address():
                        i += 1
                        break
                self.insertTab(i, self.BoardTab(board, parent=self), 'Board {0}'.format(board.address()))

    def tab_list(self):
        return [self.widget(i) for i in range(self.count())]

    def __iter__(self):
        return iter([self.widget(i) for i in range(self.count())])

    def test_connection(self):
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

        return errors

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
        self.stop_field.setValidator(QIntValidator(0, 999))
        self.stop_layout = QHBoxLayoutWithError(self.stop_field, self.stop_label, error='Range: 0 - 999')
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

class SweepGroup(QGroupBox):
    def __init__(self):
        super().__init__('Sweep')
        self.log_checkbox = QCheckBox('Logarithmic')
        self.start_label = QLabel('Start (Hz)')
        self.increment_label = QLabel('Increment (Hz)')
        self.samples_label = QLabel('Samples')
        self.final_label = QLabel('Final (Hz)')

        self.start_field = QLineEdit()
        self.increment_field = QLineEdit()
        self.samples_field = QLineEdit()
        self.final_field = QLabel()

        self.start_field.setValidator(QIntValidator(1000, 100000))
        self.increment_field.setValidator(QIntValidator(0, 62000))
        self.samples_field.setValidator(QIntValidator(1, 512))

        self.start_field.setMaxLength(6)
        self.increment_field.setMaxLength(5)
        self.samples_field.setMaxLength(3)

        self.start_layout = QHBoxLayoutWithError(self.start_field, error='Range: 1 - 100 kHz')
        self.increment_layout = QHBoxLayoutWithError(self.increment_field, error='Range: 0 - 62 kHz')
        self.samples_layout = QHBoxLayoutWithError(self.samples_field, error='Range: 1 - 512')
        self.final_layout = QHBoxLayoutWithError(self.final_field, stretch=True, error='Range: 1 - 100 kHz')

        layout = QFormLayout()
        layout.addRow(self.log_checkbox)
        layout.addRow(self.start_label, self.start_layout)
        layout.addRow(self.increment_label, self.increment_layout)
        layout.addRow(self.samples_label, self.samples_layout)
        layout.addRow(self.final_label, self.final_layout)

        self.setLayout(layout)

class LogLayout(QHBoxLayoutWithError):
    def __init__(self):
        self.field = QLineEdit('Results')
        self.field.setReadOnly(True)
        self.button = QPushButton('Change...')
        super().__init__(QLabel('Log'), self.field, self.button)

class DetectButton(QPushButton):
    def __init__(self):
        super().__init__('Detect Boards')
        # super().__init__('Detect Boards (hover for help)')
        # TODO: actual help
        # self.setToolTip('')

def change_log_directory():
    # noinspection PyArgumentList,PyCallByClass
    log_layout.field.setText(QFileDialog.getExistingDirectory(window, directory=log_layout.field.text()))

def validate():
    valid = True

    try:
        with open(log_layout.field.text()+'/.test', 'a+') as file:
            file.write('\n')
        os.remove(log_layout.field.text()+'/.test')
    except OSError as error:
        log_layout.show_error(text=os.strerror(error.errno))
        valid = False
    else:
        log_layout.hide_error()

    for layout, field in [(sweep_group.start_layout, sweep_group.start_field),
                   (sweep_group.increment_layout, sweep_group.increment_field),
                   (sweep_group.samples_layout, sweep_group.samples_field)]:
        layout.hide_error(field.hasAcceptableInput())
        valid &= field.hasAcceptableInput()

    try:
        final = int(sweep_group.start_field.text()) + int(sweep_group.increment_field.text()) * int(sweep_group.samples_field.text())
        sweep_group.final_field.setText(str(final))
        accept = (1000 <= final <= 100000)
        valid &= accept
        sweep_group.final_layout.hide_error(accept)
    except ValueError:
        valid = False
        sweep_group.final_field.setText('')
        sweep_group.final_layout.hide_error()

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

    if schedule_group.stop_checkbox.isChecked() and not schedule_group.stop_field.hasAcceptableInput():
        valid = False
        schedule_group.stop_layout.show_error()
    else:
        schedule_group.stop_layout.hide_error()

    return valid

def start_stop():
    if 'started' not in start_stop.__dict__: start_stop.started = False
    if not start_stop.started:
        save_config()
        errors = '\n'.join(board_tabs.test_connection())
    else:
        errors = ''

    if len(errors) > 0:
        # noinspection PyArgumentList,PyCallByClass
        QMessageBox.critical(window, 'Connection Error', errors)
    elif validate():
        if len(board_tabs.tab_list()) == 0:
            return
        start_stop.started = not start_stop.started

        start_stop_button.setEnabled(start_stop.started)
        start_stop_button.repaint()
        start_stop_button.setText('Stop' if start_stop.started else 'Start')

        unmute = [
            sweep_group.start_field,
            sweep_group.increment_field,
            sweep_group.samples_field,
            schedule_group.interval_field,
            schedule_group.interval_combobox,
            log_layout.field
        ]

        # noinspection PyTypeChecker
        disableables = unmute + [
            sweep_group.log_checkbox,
            schedule_group.delay_checkbox,
            schedule_group.stop_checkbox,
            log_layout.button,
            detect_boards_button
        ]

        if sweep_group.log_checkbox.isChecked():
            unmute += [sweep_group.log_checkbox]

        if schedule_group.delay_checkbox.isChecked():
            unmute += [schedule_group.delay_checkbox, schedule_group.delay_field, schedule_group.delay_combobox]
            disableables += [schedule_group.delay_field, schedule_group.delay_combobox]

        if schedule_group.stop_checkbox.isChecked():
            unmute += [schedule_group.stop_checkbox, schedule_group.stop_field, schedule_group.stop_label]
            disableables += [schedule_group.stop_field, schedule_group.stop_label]

        for widget in disableables:
            widget.setDisabled(start_stop.started)

        for widget in unmute:
            widget.setStyleSheet('' if not start_stop.started else
                                 'color: black; '
                                 'QComboBox { color: black; }; '
                                 'QCheckBox { color: black; }; '
                                 'QLabel { color: black; }; '
                                 'QCheckBox::QLabel { color: black; }; '
                                 'QWidget { color: black; }; '
                                 'QListView { color: black; }; ')

        if start_stop.started:
            sweeps = int(schedule_group.stop_field.text()) if schedule_group.stop_checkbox.isChecked() else None

            global scheduler_thread
            scheduler_thread = SchedulerThread(
                int(sweep_group.start_field.text()),
                int(sweep_group.increment_field.text()),
                int(sweep_group.samples_field.text()),
                schedule_group.interval,
                schedule_group.start,
                sweeps,
                board_tabs.tab_list()
            )

            scheduler_thread.sig_update_timer.connect(update_timer)
            scheduler_thread.start()
        else:
            scheduler_thread.sig_update_timer.disconnect(update_timer)
            scheduler_thread.quit()
            while not scheduler_thread.wait():
                pass
            validate()
            start_stop_button.setEnabled(True)


class SchedulerThread(QThread):
    sig_update_timer = pyqtSignal(timedelta, name='update_timer')

    def __init__(self, start_freq, increment_freq, samples, period, delay, sweeps, tabs, parent=None):
        super().__init__(parent)
        self.__start_freq = start_freq
        self.__increment_freq = increment_freq
        self.__samples = samples
        self.__period = period
        self.__delay = delay
        self.__sweeps = sweeps
        self.__tabs = tabs
        self.__mux_thread = QThread()
        self.quit_now = False

    def run(self):
        def sweep_gen(sweeps):
            while sweeps is None:
                yield 0
            yield range(0, sweeps)

        next_time = datetime.utcnow() + self.__delay

        for _ in sweep_gen(self.__sweeps):
            while next_time - datetime.utcnow() > timedelta() and not self.quit_now:
                self.sig_update_timer.emit(next_time - datetime.utcnow())
                sleep(0.1)
            next_time += self.__period

            self.__mux_thread.wait()
            if self.quit_now:
                return
            self.__mux_thread = MuxThread(datetime.utcnow(), self.__start_freq, self.__increment_freq, self.__samples, self.__tabs)
            self.__mux_thread.start()


    def quit(self):
        self.quit_now = True
        self.__mux_thread.quit()
        self.__mux_thread.wait()

class MuxThread(QThread):
    def __init__(self, time, start_freq, increment_freq, samples, tabs, parent=None):
        super().__init__(parent)
        self.sweep_threads = [SweepThread(time, start_freq, increment_freq, samples, tab) for tab in tabs]
        self.quit_now = False

    def run(self):
        # TODO: handle communication failures
        while len(self.sweep_threads) > 0:
            for i in range(len(self.sweep_threads)-1, -1, -1):
                try:
                    self.sweep_threads[i].select_next_terminal()
                except StopIteration:
                    del self.sweep_threads[i]

            for sweep_thread in self.sweep_threads:
                sweep_thread.start()
            for sweep_thread in self.sweep_threads:
                sweep_thread.wait()
            if self.quit_now:
                return

    def quit(self):
        self.quit_now = True
        for sweep_thread in self.sweep_threads:
            sweep_thread.quit()
        for sweep_thread in self.sweep_threads:
            sweep_thread.wait()

class SweepThread(QThread):
    sig_new_data = pyqtSignal(datetime, Board.Mux.Port.Channel.Terminal, dict, name='new_data')

    def __init__(self, time, start_freq, increment_freq, samples, tab: BoardTabs.BoardTab, parent=None):
        super().__init__(parent)
        self.time = time
        self.start_freq = start_freq
        self.increment_freq = increment_freq
        self.samples = samples
        self.tab = tab
        self.terminals = iter(tab.terminals())
        self.quit_now = False
        self.tab.board().quit_now = False
        self.sig_new_data.connect(tab.new_data)

    def run(self):
        if self.quit_now:
            return
        try:
            self.sig_new_data.emit(self.time, self.tab.board().mux.selected(), self.tab.board().sweep(self.start_freq, self.increment_freq, self.samples-1))
        except QuitNow:
            return

    def select_next_terminal(self):
        self.tab.board().select()
        self.tab.board().mux.select(next(self.terminals))

    def quit(self):
        self.quit_now = True
        self.tab.board().quit_now = True


def update_timer(time: timedelta):
    if time is None:
        schedule_group.next_field.setText('')
    else:
        hours, remainder = divmod(time.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        schedule_group.next_field.setText('{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds)))

def detect_boards():
    class Thread(QThread):
        done = pyqtSignal(name='done')

        def __init__(self, board, parent=None):
            super().__init__(parent)
            self.__board = board

        def run(self):
            self.__board.load_calibration_constants()
            self.done.emit()

    boards = []
    for address in range(0, 8):
        try:
            boards.append(Board(address))
            message_box = QMessageBox(window)
            message_box.setText('Found board {0}, reading calibration constants...'.format(address))
            message_box.setWindowTitle('Found board {0}'.format(address))
            message_box.setModal(True)
            message_box.setStandardButtons(QMessageBox.NoButton)
            message_box.setIcon(QMessageBox.Information)
            thread = Thread(boards[-1])
            thread.done.connect(message_box.accept)
            thread.start()
            if message_box.exec() == QMessageBox.Cancel:
                return []
        except IOError:
            pass

    board_tabs.update_tabs(boards)

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
        sweep_group.increment_field.setText(data.get('sweep_group.increment_field', '500'))
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
            try:
                port_tab.setChecked(data[str(board_tab.board().address())][str(index)])
            except (KeyError, ValueError):
                port_tab.setChecked(True)

def save_config():
    data = {
        'sweep_group.log_checkbox': sweep_group.log_checkbox.isChecked(),
        'schedule_group.delay_checkbox': schedule_group.delay_checkbox.isChecked(),
        'schedule_group.stop_checkbox': schedule_group.stop_checkbox.isChecked(),
        'sweep_group.start_field': sweep_group.start_field.text(),
        'sweep_group.increment_field': sweep_group.increment_field.text(),
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
            data[str(board_tab.board().address())][str(index)] = port_tab.isChecked()

    with open('/home/pi/.loc_settings.ini', 'w') as settings_file:
        json.dump(data, settings_file)

ROOT_DIR = '/tmp/LocControl/'
os.makedirs(ROOT_DIR, exist_ok=True)

app = QApplication([])
app.setStyle('cleanlooks')

sweep_group = SweepGroup()
schedule_group = ScheduleGroup()
log_layout = LogLayout()
detect_boards_button = DetectButton()
start_stop_button = QPushButton('Start')

sweep_group.log_checkbox.stateChanged.connect(validate)
sweep_group.start_field.textChanged.connect(validate)
sweep_group.increment_field.textChanged.connect(validate)
sweep_group.samples_field.textChanged.connect(validate)
schedule_group.delay_combobox.currentIndexChanged.connect(validate)
schedule_group.interval_combobox.currentIndexChanged.connect(validate)
schedule_group.delay_checkbox.stateChanged.connect(validate)
schedule_group.stop_checkbox.stateChanged.connect(validate)
schedule_group.interval_field.textChanged.connect(validate)
schedule_group.delay_field.textChanged.connect(validate)
schedule_group.stop_field.textChanged.connect(validate)
log_layout.field.textChanged.connect(validate)

start_stop_button.clicked.connect(start_stop)
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
settings_layout.addStretch()

# noinspection PyArgumentList
settings = QWidget()
settings.setLayout(settings_layout)
settings.setFixedWidth(250)

# TODO: set correct aspect ratio
board_tabs = BoardTabs()

window_layout = QHBoxLayout()
# noinspection PyArgumentList
window_layout.addWidget(settings)
# noinspection PyArgumentList
window_layout.addWidget(board_tabs, 0)

# noinspection PyArgumentList
window = QWidget()
window.setLayout(window_layout)
window.setWindowTitle('Loc Control')
window.show()

# noinspection PyCallByClass,PyTypeChecker
QTimer.singleShot(100, load_config)
app.exec_()
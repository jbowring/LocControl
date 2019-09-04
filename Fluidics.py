from serial import Serial, SerialException
from CustomWidgets import ComboBox
from PyQt5.QtWidgets import QGroupBox, QPushButton, QFormLayout, QMessageBox, QLabel, QListWidget
from PyQt5.QtCore import QSize, QVariant, Qt


class _PumpButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.__style_dict = {}

    def setStyleSheet(self, _):
        raise NotImplementedError

    def setStyleSheetOption(self, option, style):
        self.__style_dict[option] = style
        style_sheet = ''
        for option, style in self.__style_dict.items():
            if style is not None:
                style_sheet += '{0}: {1}; '.format(option, style)
        super().setStyleSheet(style_sheet)


class _ComboBox(ComboBox):
    def __init__(self):
        super().__init__()
        self.__style_dict = {}
        list_view = QListWidget()
        self.setModel(list_view.model())
        self.setView(list_view)

    def setStyleSheet(self, _):
        raise NotImplementedError

    def setStyleSheetOption(self, option, style):
        self.__style_dict[option] = style
        style_sheet = ''
        for option, style in self.__style_dict.items():
            if style is not None:
                style_sheet += '{0}: {1}; '.format(option, style)
        print('setting stylesheet', style_sheet)
        super().setStyleSheet(style_sheet)


class FluidicsGroup(QGroupBox):
    def __init__(self, parent_window):
        super().__init__('Fluidics')
        self.__parent_window = parent_window

        self.__flow_rate_label = QLabel('Flow Rate:')

        self.__flow_rate_combo = _ComboBox()
        # self.__flow_rate_combo.addItem('0 µl', '0')
        self.__flow_rate_combo.addItem('30 µl', '1')
        self.__flow_rate_combo.addItem('5000 µl', '3')
        self.__flow_rate_combo.addItem('Fast', '4')

        self.__direction_label = QLabel('Direction:')

        self.__direction_combo = _ComboBox()
        self.__direction_combo.addItem('Infuse', '0')
        self.__direction_combo.addItem('Withdraw', '1')

        self.__button = _PumpButton()
        self.__button.setStyleSheetOption('font-size', '24pt')

        layout = QFormLayout()
        layout.addRow(self.__flow_rate_label, self.__flow_rate_combo)
        layout.addRow(self.__direction_label, self.__direction_combo)
        layout.addRow(self.__button)
        self.setLayout(layout)

        self.__port = '/dev/ttyACM0'
        self.__stop(just_ui=True)

    def __start(self):
        command = '000{0}{1}\n'.format(self.__direction_combo.currentData(), self.__flow_rate_combo.currentData())

        if self.__send_command(command):
            try:
                self.__button.clicked.disconnect()
            except TypeError:  # no connected listeners
                pass
            self.__flow_rate_combo.setEnabled(False)
            self.__direction_combo.setEnabled(False)
            self.__flow_rate_combo.setStyleSheetOption('color', 'black')
            self.__direction_combo.setStyleSheetOption('color', 'black')
            self.__button.setText('STOP PUMP')
            self.__button.setStyleSheetOption('background-color', 'red')
            self.__button.clicked.connect(self.__stop)

    def __stop(self, just_ui=False):
        if just_ui or self.__send_command('00010\n'):
            try:
                self.__button.clicked.disconnect()
            except TypeError:  # no connected listeners
                pass
            self.__flow_rate_combo.setEnabled(True)
            self.__direction_combo.setEnabled(True)
            self.__flow_rate_combo.setStyleSheetOption('color', None)
            self.__direction_combo.setStyleSheetOption('color', None)
            self.__button.setText('START PUMP')
            self.__button.setStyleSheetOption('background-color', 'lime')
            self.__button.clicked.connect(self.__start)

    def __send_command(self, command, ignore_error=False):
        try:
            Serial(self.__port, timeout=5).write(command.encode())
        except SerialException:
            if ignore_error:
                return True
            else:
                QMessageBox.critical(
                    self,
                    'Pump Communications Failure',
                    'Failed to find pump controller on port {0}'.format(self.__port)
                )
                return False
        else:
            return True

    def set_small_screen(self, small_screen):
        self.setStyleSheet('QGroupBox{font-size: 18pt} QComboBox,QListWidget {font-size: 34pt}' if small_screen else '')
        self.__button.setStyleSheetOption('height', '100px' if small_screen else None)

        for combo in [self.__flow_rate_combo, self.__direction_combo]:
            combo.setStyleSheetOption('height', '100px' if small_screen else None)
            for i in range(combo.view().count()):
                if small_screen:
                    combo.view().item(i).setSizeHint(QSize(combo.view().item(i).sizeHint().width(), 100))
                else:
                    combo.view().item(i).setData(Qt.SizeHintRole, QVariant())

        self.__flow_rate_label.setHidden(small_screen)
        self.__direction_label.setHidden(small_screen)

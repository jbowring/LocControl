from serial import Serial, SerialException
from PyQt5.QtWidgets import QGroupBox, QComboBox, QPushButton, QFormLayout, QMessageBox


class FluidicsGroup(QGroupBox):
    def __init__(self, parent_window):
        super().__init__('Fluidics')
        self.__parent_window = parent_window

        self.__flow_rate_combo = QComboBox()
        # self.__flow_rate_combo.addItem('0 µl', '0')
        self.__flow_rate_combo.addItem('30 µl', '1')
        self.__flow_rate_combo.addItem('5000 µl', '3')
        self.__flow_rate_combo.addItem('Fast', '4')

        self.__direction_combo = QComboBox()
        self.__direction_combo.addItem('Infuse', '0')
        self.__direction_combo.addItem('Withdraw', '1')

        self.__button = QPushButton()
        font = self.__button.font()
        font.setPointSize(14)
        self.__button.setFont(font)

        layout = QFormLayout()
        layout.addRow('Flow Rate:', self.__flow_rate_combo)
        layout.addRow('Direction:', self.__direction_combo)
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
            self.__flow_rate_combo.setStyleSheet('color: black')
            self.__direction_combo.setStyleSheet('color: black')
            self.__button.setText('STOP PUMP')
            self.__button.setStyleSheet('background-color: red')
            self.__button.clicked.connect(self.__stop)

    def __stop(self, just_ui=False):
        if just_ui or self.__send_command('00010\n'):
            try:
                self.__button.clicked.disconnect()
            except TypeError:  # no connected listeners
                pass
            self.__flow_rate_combo.setEnabled(True)
            self.__direction_combo.setEnabled(True)
            self.__flow_rate_combo.setStyleSheet('')
            self.__direction_combo.setStyleSheet('')
            self.__button.setText('START PUMP')
            self.__button.setStyleSheet('background-color: lime')
            self.__button.clicked.connect(self.__start)

    def __send_command(self, command, ignore_error=False):
        try:
            Serial(self.__port).write(command.encode())
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

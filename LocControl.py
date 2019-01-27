from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget, QFormLayout)

app = QApplication([])


def make_sweep_group():
    log_checkbox = QCheckBox('Logarithmic')
    start_label = QLabel('Start (Hz)')
    interval_label = QLabel('Interval (Hz)')
    points_label = QLabel('Points')
    final_label = QLabel('Final (Hz)')
    
    start_field = QLineEdit('100')
    interval_field = QLineEdit('100')
    points_field = QLineEdit('990')
    final_field = QLabel('9999')
    
    layout = QFormLayout()
    layout.addRow(log_checkbox)
    layout.addRow(start_label, start_field)
    layout.addRow(interval_label, interval_field)
    layout.addRow(points_label, points_field)
    layout.addRow(final_label, final_field)
    
    group = QGroupBox('Sweep')
    group.setLayout(layout)
    return group


def make_schedule_group():
    interval_label = QLabel('Sweep every')
    interval_field = QLineEdit('1')
    interval_combobox = QComboBox()
    interval_combobox.addItems(['h', 'm', 's'])
    interval_layout = QHBoxLayout()
    interval_layout.addWidget(interval_field)
    interval_layout.addWidget(interval_combobox)
    
    start_checkbox = QCheckBox('Start in')
    start_field = QLineEdit('1')
    start_combobox = QComboBox()
    start_combobox.addItems(['h', 'm', 's'])
    start_layout = QHBoxLayout()
    start_layout.addWidget(start_field)
    start_layout.addWidget(start_combobox)
    start_field.setDisabled(True)
    start_combobox.setDisabled(True)
    
    stop_checkbox = QCheckBox('Stop after')
    stop_label = QLabel('sweeps')
    stop_field = QLineEdit('10')
    stop_layout = QHBoxLayout()
    stop_layout.addWidget(stop_field)
    stop_layout.addWidget(stop_label)
    stop_field.setDisabled(True)

    next_label = QLabel('Next sweep in')
    next_field = QLabel('<hh mm ss>')

    layout = QFormLayout()
    layout.addRow(interval_label, interval_layout)
    layout.addRow(start_checkbox, start_layout)
    layout.addRow(stop_checkbox, stop_layout)
    layout.addRow(next_label, next_field)

    group = QGroupBox('Schedule')
    group.setLayout(layout)
    return group


def make_log_layout():
    layout = QHBoxLayout()
    field = QLineEdit('Results')
    field.setReadOnly(True)
    button = QPushButton('Change...')
    layout.addWidget(QLabel('Log directory'))
    layout.addWidget(field)
    layout.addWidget(button)

    return layout


sweep_group = make_sweep_group()
schedule_group = make_schedule_group()
log_layout = make_log_layout()
start_stop_button = QPushButton('Start')

settings_layout = QVBoxLayout()
settings_layout.addWidget(sweep_group)
settings_layout.addWidget(schedule_group)
settings_layout.addLayout(log_layout)
settings_layout.addWidget(start_stop_button)

window = QWidget()
window.setLayout(settings_layout)
window.setWindowTitle('Loc Control')
window.show()
app.exec_()

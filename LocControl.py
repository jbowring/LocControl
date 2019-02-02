from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDial, QDialog,
                             QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QProgressBar, QPushButton, QRadioButton, QScrollBar, QSizePolicy,
                             QSlider, QSpinBox, QStyleFactory, QTableWidget, QTabWidget,
                             QTextEdit, QVBoxLayout, QWidget, QFormLayout, QFileDialog)
from dateutil.rrule import weekday

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib
import random

matplotlib.use('QT5Agg')


def make_sweep_group():
    log_checkbox = QCheckBox('Logarithmic')
    start_label = QLabel('Start (Hz)')
    interval_label = QLabel('Interval (Hz)')
    samples_label = QLabel('Samples')
    final_label = QLabel('Final (Hz)')

    start_field = QLineEdit('100')
    interval_field = QLineEdit('100')
    samples_field = QLineEdit('990')
    final_field = QLabel('9999')

    layout = QFormLayout()
    layout.addRow(log_checkbox)
    layout.addRow(start_label, start_field)
    layout.addRow(interval_label, interval_field)
    layout.addRow(samples_label, samples_field)
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
    start_checkbox.toggled.connect(start_field.setEnabled)
    start_checkbox.toggled.connect(start_combobox.setEnabled)

    stop_checkbox = QCheckBox('Stop after')
    stop_label = QLabel('sweeps')
    stop_field = QLineEdit('10')
    stop_layout = QHBoxLayout()
    stop_layout.addWidget(stop_field)
    stop_layout.addWidget(stop_label)
    stop_field.setDisabled(True)
    stop_checkbox.toggled.connect(stop_field.setEnabled)

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


app = QApplication([])

sweep_group = make_sweep_group()
schedule_group = make_schedule_group()
log_layout = make_log_layout()
start_stop_button = QPushButton('Start')

settings_layout = QVBoxLayout()
settings_layout.addWidget(sweep_group)
settings_layout.addWidget(schedule_group)
settings_layout.addLayout(log_layout)
settings_layout.addWidget(start_stop_button)

tabs = QTabWidget()
tab1 = QWidget()
tab1_layout = QGridLayout()
tab1.setLayout(tab1_layout)
tabs.addTab(tab1, 'Board 1')
tabs.addTab(QWidget(), 'Board 2')

layout = QHBoxLayout()
layout.addLayout(settings_layout, 0)
layout.addWidget(tabs, 1)


class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)

        FigureCanvas.__init__(self, fig)
        self.setParent(parent)

        FigureCanvas.setSizePolicy(self, QSizePolicy.Expanding, QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)

    def plot(self, data):
        ax = self.figure.add_subplot(111)
        ax.plot(data, 'r-')
        self.draw()

data = [0.7080047878851999, 0.6683695118503081, 0.49729540313380727, 0.6598648844833899, 0.5415399961562541, 0.003046626679499398, 0.5958037255442881, 0.7376226178295634, 0.4068605293526456, 0.96567372446259, 0.12008175923942321, 0.8914099267262007, 0.7100205200909128, 0.5084370688235172, 0.4018559310183749, 0.44991208212412026, 0.322256163539692, 0.9562439185880058, 0.45156369626148707, 0.14461428628852147, 0.6882588166433491, 0.7761536532275696, 0.7547250151731597, 0.04807538403747724, 0.8845126957106171]

for i in range(2):
    for j in range(2):
        w = QWidget()
        m = PlotCanvas(w, 3, 3, 75)
        # m.move(0, 0)
        m.plot(data)
        tab1_layout.addWidget(w, i, j)

tab1_layout.setSpacing(0)

window = QWidget()
window.setLayout(layout)
window.setWindowTitle('Loc Control')
window.showMaximized()

app.exec_()

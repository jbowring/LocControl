from PyQt5.QtCore import QSize
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QStyle, QToolTip, QComboBox


class _ErrorLabel(QLabel):
    def __init__(self, text=''):
        super().__init__()
        self.__tooltip_text = text
        self.setToolTip(text)
        self.setPixmap(QApplication.instance().style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(QSize(16, 16)))

    def enterEvent(self, event):
        QToolTip.hideText()
        super().enterEvent(event)
        QToolTip.showText(QCursor.pos(), self.__tooltip_text)


# Subclass of QHBoxLayout with error symbol built-in
class QHBoxLayoutWithError(QHBoxLayout):
    def __init__(self, *widgets, stretch=False, error=None):
        super().__init__()
        for widget in widgets:
            # noinspection PyArgumentList
            self.addWidget(widget)
        if stretch:
            self.addStretch()
        self.__error_label = _ErrorLabel(error)
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


class ComboBox(QComboBox):
    def __init__(self):
        super().__init__()
        # noinspection PyUnresolvedReferences
        self.activated.connect(lambda _: self.clearFocus())

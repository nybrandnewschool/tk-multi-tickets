# -*- coding: utf-8 -*-
from __future__ import print_function, division

# Shotgun imports
from sgtk.platform.qt import QtCore, QtGui

# Local imports
from . import res


class ErrorDialog(QtGui.QDialog):

    def __init__(self, label, message, parent=None):
        super(ErrorDialog, self).__init__(parent)

        self.setWindowTitle('tk-multi-tickets Error')
        self.setWindowIcon(QtGui.QIcon(res.get_path('icon_256.png')))
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
        )

        self.label = QtGui.QLabel(label)
        self.text = QtGui.QPlainTextEdit(message)
        self.text.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)

        self.button = QtGui.QPushButton('Dismiss')
        self.button.setSizePolicy(
            QtGui.QSizePolicy.Maximum,
            QtGui.QSizePolicy.Maximum,
        )
        self.button.clicked.connect(self.accept)

        self.layout = QtGui.QVBoxLayout()
        self.layout.setStretch(1, 1)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.text)
        self.layout.addWidget(self.button)
        self.layout.setAlignment(self.button, QtCore.Qt.AlignRight)
        self.setLayout(self.layout)

    def accept(self):
        super(ErrorDialog, self).accept()
        self.close()

    def reject(self):
        super(ErrorDialog, self).reject()
        self.close()

    @property
    def hide_tk_title_bar(self):
        return True

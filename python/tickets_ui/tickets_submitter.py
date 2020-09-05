# -*- coding: utf-8 -*-
from __future__ import print_function

# Standard library imports
from functools import partial
import contextlib
import os
import shutil
import tempfile
import textwrap
import traceback
import webbrowser

# Shotgun imports
import sgtk
from sgtk.platform.qt import QtCore, QtGui

# Local imports
from .dialogs import ErrorDialog
from .notice import Notice
from . import res


app = sgtk.platform.current_bundle()
task_manager = sgtk.platform.import_framework(
    'tk-framework-shotgunutils',
    'task_manager'
)
screen_grab = sgtk.platform.import_framework(
    'tk-framework-qtwidgets',
    'screen_grab',
)
context_selector = sgtk.platform.import_framework(
    'tk-framework-qtwidgets',
    'context_selector',
)


def show(app, **field_defaults):
    '''Show the TicketsSubmitter for the given app.'''

    app.logger.info('Launching tickets submitter...')
    return app.engine.show_dialog(
        'Submit a Ticket',
        app,
        TicketsSubmitter,
        **field_defaults
    )


class Attachments(QtGui.QListWidget):
    '''Attachments Widget - List of screen captures.'''

    style = textwrap.dedent('''
        QListView {
            border: 0;
            background: transparent;
        }
    ''')

    def __init__(self, parent):
        super(Attachments, self).__init__(parent)

        self.setFlow(QtGui.QListView.LeftToRight)
        self.setViewMode(QtGui.QListView.IconMode)
        self.setResizeMode(QtGui.QListView.Adjust)
        self.setGridSize(QtCore.QSize(36, 36))
        self.setStyleSheet(self.style)
        self.setMaximumHeight(36)
        self.setSelectionMode(self.NoSelection)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._attachments = []
        self._default_items = []

        # Capture button
        self.capture_button = QtGui.QToolButton(
            icon=QtGui.QIcon(res.get_path('camera.png'))
        )
        self.capture_button.setToolTip('Grab part of the screen.')
        self.capture_button.clicked.connect(self._on_capture)
        item = QtGui.QListWidgetItem()
        item.setSizeHint(self.gridSize())
        self.addItem(item)
        self.setItemWidget(item, self.capture_button)
        self._default_items.append(item)

    def add_attachment(self, pixmap):
        size = self.gridSize()
        item = QtGui.QListWidgetItem()
        item.attachment = pixmap
        pixmap = pixmap.scaled(
            size,
            QtCore.Qt.KeepAspectRatioByExpanding,
        ).copy(
            QtCore.QRect(QtCore.QPoint(), size)
        )
        item.setIcon(QtGui.QIcon(pixmap))
        item.setSizeHint(size)
        self.insertItem(0, item)
        self._attachments.insert(0, item)

    def get_attachments(self):
        attachments = []
        for item in self._attachments:
            attachments.append(item.attachment)
        return attachments

    def _remove_item_at(self, pos):
        item = self.itemAt(pos)
        row = self.row(item)
        self._attachments.pop(row)
        self.takeItem(row)

    def _preview_item_at(self, pos):
        item = self.itemAt(pos)

        self._preview = QtGui.QLabel()
        self._preview.setPixmap(item.attachment)
        self._preview.show()
        self._preview.setWindowTitle('Preview')
        self._preview.setWindowIcon(QtGui.QIcon(res.get_path('icon_256.png')))
        self._preview.setGeometry(
            QtGui.QStyle.alignedRect(
                QtCore.Qt.LeftToRight,
                QtCore.Qt.AlignCenter,
                self._preview.size(),
                QtGui.QApplication.instance().desktop().availableGeometry()
            )
        )

    def _show_context_menu(self, pos):

        item = self.itemAt(pos)
        row = self.row(item)
        if row >= self.count() - 1:
            return

        menu = QtGui.QMenu()
        menu.addAction(
            QtGui.QIcon(res.get_path('preview.png')),
            'preview',
            partial(self._preview_item_at, pos),
        )
        menu.addAction(
            QtGui.QIcon(res.get_path('clear.png')),
            'remove',
            partial(self._remove_item_at, pos),
        )
        menu.exec_(self.mapToGlobal(pos))

    def _on_capture(self):
        pixmap = screen_grab.screen_capture()
        self.add_attachment(pixmap)


class TicketsSubmitter(QtGui.QWidget):
    '''UI for submitting support tickets.'''

    def __init__(self, *args, **kwargs):

        # Get field defaults
        fields = kwargs.pop('fields', None)
        fields.setdefault('title', None)
        fields.setdefault('priority', None)
        fields.setdefault('type', None)
        fields.setdefault('description', None)
        fields.setdefault('context', None)
        fields.setdefault('error', None)
        fields.setdefault('message', None)
        self._exc_info = fields.pop('exc_info', None)

        # Initialize widget
        super(TicketsSubmitter, self).__init__(*args, **kwargs)

        # Create task manager
        self._task_manager = task_manager.BackgroundTaskManager(
            parent=self,
            start_processing=True,
            max_threads=2,
        )

        # Create widgets
        self.message = QtGui.QLabel()
        self.message.setWordWrap(True)
        self.sep0 = QtGui.QFrame()
        self.sep0.setFrameShape(self.sep0.HLine)
        self.sep0.setFrameShadow(self.sep0.Sunken)
        self.context_selector = context_selector.ContextWidget(self)
        self.context_selector.ui.label.setText('Ticket Context')
        self.context_selector.ui.label.hide()
        self.context_selector.context_changed.connect(self._on_context_changed)
        self._context = None
        self.sep1 = QtGui.QFrame()
        self.sep1.setFrameShape(self.sep1.HLine)
        self.sep1.setFrameShadow(self.sep1.Sunken)
        self.title = QtGui.QLineEdit(self)
        self.type = QtGui.QComboBox(self)
        self.type.setSizePolicy(
            QtGui.QSizePolicy.Expanding,
            QtGui.QSizePolicy.Expanding,
        )
        self.priority = QtGui.QComboBox(self)
        self.priority.setSizePolicy(
            QtGui.QSizePolicy.Expanding,
            QtGui.QSizePolicy.Expanding,
        )
        self.description = QtGui.QTextEdit(self)
        policy = self.description.sizePolicy()
        policy.setVerticalStretch(1)
        self.description.setSizePolicy(policy)
        self.attachments = Attachments(self)
        self.error = QtGui.QTextEdit(self)
        self.error.setFocusPolicy(QtCore.Qt.NoFocus)
        self.error.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        policy = self.error.sizePolicy()
        policy.setVerticalStretch(1)
        self.error.setSizePolicy(policy)
        self.submit_button = QtGui.QPushButton('Submit')
        self.submit_button.clicked.connect(self._on_submit)

        # Layout widgets
        footer_layouer = QtGui.QHBoxLayout()
        footer_layouer.addStretch(1)
        footer_layouer.addWidget(self.submit_button)
        self.footer = QtGui.QWidget()
        self.footer.setLayout(footer_layouer)

        self.layout = QtGui.QFormLayout()
        self.layout.addRow(self.message)
        self.layout.addRow(self.sep0)
        self.layout.addRow(self.context_selector)
        self.layout.addRow(self.sep1)
        self.layout.addRow('Title', self.title)
        self.layout.addRow('Type', self.type)
        self.layout.addRow('Priority', self.priority)
        self.layout.addRow('Attachments', self.attachments)
        self.layout.addRow('Description', self.description)
        self.layout.addRow('Error', self.error)
        self.layout.addRow(self.footer)
        self.setLayout(self.layout)
        if not fields['error']:
            self.hide_field(self.error)
        if not fields['message']:
            self.hide_field(self.message)
            self.hide_field(self.sep0)

        # Initialize field defaults
        QtCore.QTimer.singleShot(
            50,
            partial(self.set_field_defaults, fields),
        )
        self.adjustSize()

    @property
    def hide_tk_title_bar(self):
        return True

    def closeEvent(self, event):
        self._task_manager.shut_down()
        event.accept()

    def show_field(self, field):
        '''Show a field.'''

        field.show()
        label = self.layout.labelForField(field)
        if label:
            label.show()

    def hide_field(self, field):
        '''Hide a field.'''

        field.hide()
        label = self.layout.labelForField(field)
        if label:
            label.hide()

    def set_field_defaults(self, fields):
        '''Initialize field defaults'''

        # Set context
        context = fields.get('context', None) or app.context
        self.context_selector.set_up(self._task_manager)
        self.context_selector.set_context(context)
        self._context = context

        # Set title
        if fields['title']:
            self.title.setText(fields['title'])

        # Set description
        if fields['description']:
            self.description.setText(fields['description'])

        # Set message
        if fields['message']:
            self.show_field(self.message)
            self.show_field(self.sep0)
            self.message.setText(fields['message'])
        else:
            self.hide_field(self.message)
            self.hide_field(self.sep0)

        # Set error
        if fields['error']:
            self.show_field(self.error)
            self.error.setText(fields['error'])
        else:
            self.hide_field(self.error)

        # Set priority values
        values = app.io.get_priority_values()
        self.priority.addItems(values)
        self.priority.setCurrentIndex(self.priority.count() - 1)
        if fields['priority']:
            index = self.priority.findText(
                fields['priority'],
                QtCore.Qt.MatchFixedString,
            )
            if index > -1:
                self.priority.setCurrentIndex(index)

        # Set type values
        values = app.io.get_type_values()
        self.type.addItems(values)
        if fields['type']:
            index = self.type.findText(
                fields['type'],
                QtCore.Qt.MatchFixedString,
            )
            if index > -1:
                self.type.setCurrentIndex(index)

    def get_fields(self):
        return {
            'title': self.title.text(),
            'description': self.description.toPlainText(),
            'sg_ticket_type': self.type.currentText(),
            'sg_priority': self.priority.currentText(),
            'sg_error': self.error.toPlainText(),
        }

    def get_attachments(self):
        return self.attachments.get_attachments()

    def get_context(self):
        return self._context

    def _on_context_changed(self, context):
        self._context = context

    def _on_submit(self):
        fields = self.get_fields()
        context = self.get_context()
        attachments = self.get_attachments()

        if not fields['title']:
            note = Notice(
                'Title required.',
                fg_color="#EEE",
                bg_color="#EB5757",
                parent=self
            )
            note.show_top(self)
            self.title.setFocus()
            return

        if not fields['description']:
            note = Notice(
                'Description required.',
                fg_color="#EEE",
                bg_color="#EB5757",
                parent=self
            )
            note.show_top(self)
            self.description.setFocus()
            return

        self.close()

        try:
            with tmp_save_pixmaps(attachments) as attachments:
                ticket = app.create_ticket(
                    fields=fields,
                    context=context,
                    attachments=attachments,
                    exc_info=self._exc_info,
                )
            self._after_submit(ticket)
        except Exception:
            app.logger.exception('Error')
            error_message = ErrorDialog(
                label='Failed to submit Ticket.',
                message=traceback.format_exc(),
                parent=self,
            )
            error_message.exec_()

    def _after_submit(self, ticket):
        msg = QtGui.QMessageBox()
        msg.setWindowIcon(QtGui.QIcon(res.get_path('icon_256.png')))
        msg.setWindowTitle('Ticket Submitted')
        msg.setText('Your Ticket is #%s.' % ticket['id'])
        view_ticket = msg.addButton('View Ticket', msg.AcceptRole)
        msg.addButton('Okay', msg.AcceptRole)
        msg.exec_()

        if msg.clickedButton() == view_ticket:
            webbrowser.open(app.get_ticket_url(ticket['id']), new=2)


@contextlib.contextmanager
def tmp_save_pixmaps(pixmaps):
    '''Save pixmaps to a temp directory and return a list of temp files.'''

    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_files = []
        for i, pixmap in enumerate(pixmaps):
            tmp_file = os.path.join(tmp_dir, 'image{:0>2d}.png'.format(i))
            pixmap.save(tmp_file)
            tmp_files.append(tmp_file)
        yield tmp_files
    finally:
        shutil.rmtree(tmp_dir)

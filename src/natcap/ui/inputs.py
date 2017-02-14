from __future__ import absolute_import

import os
import threading
import logging
import platform
import subprocess
import warnings
import sys
import atexit

from qtpy import QtWidgets
from qtpy import QtCore
from qtpy import QtGui
import six
import qtawesome

from . import execution

try:
    QApplication = QtGui.QApplication
except AttributeError:
    QApplication = QtWidgets.QApplication

QT_APP = QApplication.instance()
if QT_APP is None:
    QT_APP = QApplication(sys.argv)  # pragma: no cover

LOGGER = logging.getLogger(__name__)
ICON_FOLDER = qtawesome.icon('fa.folder-o')
ICON_FILE = qtawesome.icon('fa.file-o')
ICON_ENTER = qtawesome.icon('fa.arrow-circle-o-right',
                            color='green')
_QLABEL_STYLE_TEMPLATE = ('QLabel {{padding={padding};'
                          'background-color={bg_color};'
                          'border={border};}}')
QLABEL_STYLE_INFO = _QLABEL_STYLE_TEMPLATE.format(
    padding='15px', bg_color='#d4efcc', border='2px solid #3e895b')
QLABEL_STYLE_ERROR = _QLABEL_STYLE_TEMPLATE.format(
    padding='15px', bg_color='#ebabb6', border='2px solid #a23332')

def _cleanup():
    # Adding this allows tests to run on linux via `python setup.py nosetests`
    # and `python setup.py test` without segfault.
    QT_APP.deleteLater()  # pragma: no cover
atexit.register(_cleanup)


def _apply_sizehint(widget):
    size_hint = widget.sizeHint()
    if size_hint.isValid():
        widget.setMinimumSize(size_hint)


def open_workspace(dirname):
    LOGGER.debug("Opening dirname %s", dirname)
    # Try opening up a file explorer to see the results.
    try:
        LOGGER.info('Opening file explorer to workspace directory')
        if platform.system() == 'Windows':
            # Try to launch a windows file explorer to visit the workspace
            # directory now that the operation has finished executing.
            LOGGER.info('Using windows explorer to view files')
            subprocess.Popen('explorer "%s"' % os.path.normpath(dirname))
        elif platform.system() == 'Darwin':
            LOGGER.info('Using mac finder to view files')
            subprocess.Popen(
                'open %s' % os.path.normpath(dirname), shell=True)
        else:
            # Assume we're on linux.  No biggie, just use xdg-open to use
            # default file opening scheme.
            LOGGER.info('Not on windows or mac, using default file browser')
            subprocess.Popen(['xdg-open', dirname])
    except OSError as error:
        # OSError is thrown if the given file browser program (whether
        # explorer or xdg-open) cannot be found.  No biggie, just pass.
        LOGGER.error(error)
        LOGGER.error(
            ('Cannot find default file browser. Platform: %s |'
                ' folder: %s'), platform.system(), dirname)



class ThreadSafeDataManager(object):
    """A thread-safe data management object for saving data across the multiple
    threads of the Qt GUI."""
    def __init__(self):
        self.data = {
            'last_dir': '',
        }
        self.lock = threading.Lock()

    def __getitem__(self, key):
        with self.lock:
            data = self.data[key]
        return data

    def __setitem__(self, key, value):
        with self.lock:
            self.data[key] = value

DATA = ThreadSafeDataManager()  # common data stored here


def center_window(window_ptr):
    """Center a window on whatever screen it appears.
            window_ptr - a pointer to a Qt window, whether an application or a
                QDialog.
        returns nothing."""
    geometry = window_ptr.frameGeometry()
    center = QtWidgets.QDesktopWidget().availableGeometry().center()
    geometry.moveCenter(center)
    window_ptr.move(geometry.topLeft())


class MessageArea(QtWidgets.QLabel):
    def __init__(self):
        QtWidgets.QLabel.__init__(self)
        self.setWordWrap(True)
        self.setTextFormat(QtCore.Qt.RichText)
        self.error = False

    def set_error(self, is_error):
        self.error = is_error
        if is_error:
            self.setStyleSheet(QLABEL_STYLE_ERROR)
        else:
            self.setStyleSheet(QLABEL_STYLE_INFO)
        self.show()


class QLogHandler(logging.StreamHandler):
    def __init__(self, stream_widget):
        logging.StreamHandler.__init__(self, stream=stream_widget)
        self._stream = stream_widget
        self.setLevel(logging.NOTSET)  # capture everything

        self.formatter = logging.Formatter(
            fmt='%(asctime)s %(name)-18s %(levelname)-8s %(message)s',
            datefmt='%m/%d/%Y %H:%M:%S ')
        self.setFormatter(self.formatter)


class LogMessagePane(QtWidgets.QPlainTextEdit):

    message_received = QtCore.Signal(six.text_type)

    def __init__(self):
        QtWidgets.QPlainTextEdit.__init__(self)

        self.setReadOnly(True)
        self.setStyleSheet("QWidget { background-color: White }")
        self.message_received.connect(self._write)

    def write(self, message):
        self.message_received.emit(message)

    def _write(self, message):
        self.insertPlainText(message)
        self.textCursor().movePosition(QtGui.QTextCursor.End)
        self.setTextCursor(self.textCursor())


class FileSystemRunDialog(QtWidgets.QDialog):
    def __init__(self):
        QtWidgets.QDialog.__init__(self)

        self.is_executing = False
        self.cancel = False
        self.out_folder = None

        self.setLayout(QtWidgets.QVBoxLayout())
        self.resize(700, 500)
        center_window(self)
        self.setModal(True)

        # create statusArea-related widgets for the window.
        self.statusAreaLabel = QtWidgets.QLabel('Messages:')
        self.log_messages_pane = LogMessagePane()
        self.loghandler = QLogHandler(self.log_messages_pane)
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.NOTSET)
        self.logger.addHandler(self.loghandler)

        # create an indeterminate progress bar.  According to the Qt
        # documentation, an indeterminate progress bar is created when a
        # QProgressBar's minimum and maximum are both set to 0.
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)
        self.progressBar.setTextVisible(False)
        progress_sizehint = self.progressBar.sizeHint()
        if progress_sizehint.isValid():
            self.progressBar.setMinimumSize(progress_sizehint)

        self.openWorkspaceCB = QtWidgets.QCheckBox('Open workspace after success')
        self.openWorkspaceButton = QtWidgets.QPushButton('Open workspace')
        self.openWorkspaceButton.pressed.connect(self._request_workspace)
        self.openWorkspaceButton.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        self.openWorkspaceButton.setMaximumWidth(150)
        self.openWorkspaceButton.setVisible(False)
        self.messageArea = MessageArea()
        self.messageArea.clear()

        # Add the new widgets to the window
        self.layout().addWidget(self.statusAreaLabel)
        self.layout().addWidget(self.log_messages_pane)
        self.layout().addWidget(self.messageArea)
        self.layout().addWidget(self.progressBar)
        self.layout().addWidget(self.openWorkspaceCB)
        self.layout().addWidget(self.openWorkspaceButton)

        self.backButton = QtWidgets.QPushButton(' Back')
        self.backButton.setToolTip('Return to parameter list')

        # add button icons
        self.backButton.setIcon(QtGui.QIcon(ICON_ENTER))

        # disable the 'Back' button by default
        self.backButton.setDisabled(True)

        # create the buttonBox (a container for buttons) and add the buttons to
        # the buttonBox.
        self.buttonBox = QtWidgets.QDialogButtonBox()
        self.buttonBox.addButton(
            self.backButton, QtWidgets.QDialogButtonBox.AcceptRole)

        # connect the buttons to their callback functions.
        self.backButton.clicked.connect(self.closeWindow)

        # add the buttonBox to the window.
        self.layout().addWidget(self.buttonBox)

        # Customize the window title bar to disable the close/minimize/mazimize
        # buttons, just showing the title of the modal dialog.
        self.setWindowFlags(
            QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint)

    def __del__(self):
        self.logger.removeHandler(self.loghandler)
        self.deleteLater()

    def start(self, window_title, out_folder):
        if not window_title:
            window_title = "Running ..."
        self.setWindowTitle(window_title)
        self.out_folder = out_folder

        self.is_executing = True
        self.log_messages_pane.clear()
        self.progressBar.setMaximum(0)  # start the progressbar.
        self.backButton.setDisabled(True)

        self.log_messages_pane.write('Initializing...\n')

    def finish(self, exception_found, thread_exception=None):
        """Notify the user that model processing has finished.
            returns nothing."""

        self.is_executing = False
        self.progressBar.setMaximum(1)  # stops the progressbar.
        self.backButton.setDisabled(False)
        if exception_found:
            self.messageArea.set_error(True)
            self.messageArea.setText(
                (u'<b>%s</b> encountered: <em>%s</em> <br/>'
                 'See the log for details.') % (
                    thread_exception.__class__.__name__,
                    thread_exception))
        else:
            self.messageArea.set_error(False)
            self.messageArea.setText('Model completed successfully.')

        # Change the open workspace presentation.
        if self.openWorkspaceCB.isChecked():
            self._request_workspace()
        self.openWorkspaceCB.setVisible(False)
        self.openWorkspaceButton.setVisible(True)

    def _request_workspace(self, event=None):
        open_workspace(self.out_dir)

    def closeWindow(self):
        """Close the window and ensure the modelProcess has completed.
            returns nothing."""

        self.openWorkspaceCB.setVisible(True)
        self.openWorkspaceButton.setVisible(False)
        self.messageArea.clear()
        self.cancel = False
        self.done(0)

    def reject(self):
        """Reject the dialog.

        Triggered when the user presses ESC.  Overridden from Qt.
        """
        # Called when the user presses ESC.
        if self.is_executing:
            # Don't allow the window to close if we're executing.
            return
        QtWidgets.QDialog.reject(self)

    def closeEvent(self, event):
        """
        Prevent the user from closing the modal dialog.
        Qt event handler, overridden from QWidget.closeEvent.
        """
        if self.is_executing:
            event.ignore()
        else:
            QtWidgets.QDialog.closeEvent(self, event)


class InfoButton(QtWidgets.QPushButton):
    def __init__(self, default_message=None):
        QtWidgets.QPushButton.__init__(self)
        self.setFlat(True)
        if default_message:
            self.setWhatsThis(default_message)
        self.clicked.connect(self._show_popup)

    def _show_popup(self, clicked=None):
        QtWidgets.QWhatsThis.enterWhatsThisMode()
        QtWidgets.QWhatsThis.showText(self.pos(), self.whatsThis(), self)


class ValidButton(InfoButton):
    def set_errors(self, errors):
        # Set to None or [] or anything such that bool(errors) is False to
        # clear..

        if errors:
            self.setIcon(qtawesome.icon('fa.times',
                                        color='red'))
            error_string = '<br/>'.join(errors)
        else:
            self.setIcon(qtawesome.icon('fa.check',
                                        color='green'))
            error_string = 'Validation successful'
        self.setWhatsThis(error_string)


class HelpButton(InfoButton):
    def __init__(self, default_message=None):
        InfoButton.__init__(self, default_message)
        self.setIcon(qtawesome.icon('fa.info-circle',
                                    color='blue'))


class ValidationWorker(QtCore.QObject):

    started = QtCore.Signal()
    finished = QtCore.Signal()

    def __init__(self, target, args, limit_to=None, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.target = target
        self.args = args
        self.limit_to = limit_to
        self.warnings = []
        self.error = None
        self.started.connect(self.run)
        self._finished = False

    def isFinished(self):
        return self._finished

    def start(self):
        self.started.emit()

    def run(self):
        QT_APP.processEvents()
        # Target must adhere to InVEST validation API.
        LOGGER.info(('Starting validation thread with target=%s, args=%s, '
                     'limit_to=%s'), self.target, self.args, self.limit_to)
        try:
            self.warnings = self.target(self.args, limit_to=self.limit_to)
            LOGGER.info('Validation thread returned warnings: %s',
                        self.warnings)
        except Exception as error:
            self.error = str(error)
            LOGGER.exception('Validation: Error when validating %s:',
                             self.target)
        self._finished = True
        self.finished.emit()
        QT_APP.processEvents()


class FileDialog(object):
    def __init__(self):
        object.__init__(self)
        self.file_dialog = QtWidgets.QFileDialog()

    def __del__(self):
        self.file_dialog.deleteLater()

    def save_file(self, title, start_dir=None, savefile=None):
        if not start_dir:
            start_dir = os.path.expanduser(DATA['last_dir'])

        # Allow us to open folders with spaces in them.
        os.path.normpath(start_dir)

        if savefile:
            default_path = os.path.join(start_dir, savefile)
        else:
            # If we pass a folder, the dialog will open to the folder
            default_path = start_dir

        filename = self.file_dialog.getSaveFileName(self.file_dialog, title, default_path)
        DATA['last_dir'] = os.path.dirname(six.text_type(filename))
        return filename

    def open_file(self, title, start_dir=None):
        if not start_dir:
            start_dir = os.path.expanduser(DATA['last_dir'])

        # Allow us to open folders with spaces in them.
        os.path.normpath(start_dir)

        filename = self.file_dialog.getOpenFileName(self.file_dialog, title, start_dir)
        DATA['last_dir'] = os.path.dirname(six.text_type(filename))
        return filename

    def open_folder(self, title, start_dir=None):
        if not start_dir:
            start_dir = os.path.expanduser(DATA['last_dir'])
        dialog_title = 'Select folder: ' + title

        dirname = self.file_dialog.getExistingDirectory(self.file_dialog, dialog_title,
                                                        start_dir)
        dirname = six.text_type(dirname)
        DATA['last_dir'] = dirname
        return dirname


class _FileSystemButton(QtWidgets.QPushButton):

    _icon = ICON_FOLDER
    path_selected = QtCore.Signal(six.text_type)

    def __init__(self, dialog_title):
        QtWidgets.QPushButton.__init__(self)
        self.setIcon(self._icon)
        self.dialog_title = dialog_title
        self.dialog = FileDialog()
        self.open_method = None  # This should be overridden
        self.clicked.connect(self._get_path)

    def _get_path(self):
        selected_path = self.open_method(title=self.dialog_title,
                                         start_dir=DATA['last_dir'])
        self.path_selected.emit(selected_path)


class FileButton(_FileSystemButton):

    _icon = ICON_FILE

    def __init__(self, dialog_title):
        _FileSystemButton.__init__(self, dialog_title)
        self.open_method = self.dialog.open_file


class FolderButton(_FileSystemButton):

    _icon = ICON_FOLDER

    def __init__(self, dialog_title):
        _FileSystemButton.__init__(self, dialog_title)
        self.open_method = self.dialog.open_folder


class Input(QtCore.QObject):

    value_changed = QtCore.Signal(six.text_type)
    interactivity_changed = QtCore.Signal(bool)

    def __init__(self, label, helptext=None, required=False, interactive=True,
                 args_key=None):
        QtCore.QObject.__init__(self)
        self.label = label
        self.widgets = []
        self.dirty = False
        self.interactive = interactive
        self.required = required
        self.args_key = args_key
        self.helptext = helptext
        self.lock = threading.Lock()

    def value(self):
        raise NotImplementedError

    def set_value(self):
        raise NotImplementedError

    def set_required(self, required):
        self.required = required

    def set_noninteractive(self, noninteractive):
        self.set_interactive(not noninteractive)

    def set_interactive(self, enabled):
        self.interactive = enabled
        for widget in self.widgets:
            if not widget:  # widgets to be skipped are None
                continue
            widget.setEnabled(enabled)
        self.interactivity_changed.emit(self.interactive)

    def _add_to(self, layout):
        self.setParent(layout.parent().window())  # all widgets belong to Form
        current_row = layout.rowCount()
        for widget_index, widget in enumerate(self.widgets):
            if not widget:
                continue

            # set the default interactivity based on self.interactive
            widget.setEnabled(self.interactive)

            _apply_sizehint(widget)
            layout.addWidget(
                widget,  # widget
                current_row,  # row
                widget_index)  # column


class GriddedInput(Input):

    hidden_changed = QtCore.Signal(bool)
    validity_changed = QtCore.Signal(bool)
    sufficiency_changed = QtCore.Signal(bool)

    def __init__(self, label, helptext=None, required=False, interactive=True,
                 args_key=None, hideable=False, validator=None):
        Input.__init__(self, label=label, helptext=helptext, required=required,
                       interactive=interactive, args_key=args_key)
        if not required:
            label = label + ' (Optional)'

        self._valid = True
        self._validation_thread = None
        self.validator = validator
        self.label = QtWidgets.QLabel(label)
        self.hideable = hideable
        self.sufficient = False  # False until value set and interactive
        self.valid_button = ValidButton()
        if helptext:
            self.help_button = HelpButton(helptext)
        else:
            self.help_button = QtWidgets.QWidget()  # empty widget!

        self.widgets = [
            self.valid_button,
            self.label,
            None,
            None,
            self.help_button,
        ]

        if self.hideable:
            self.label = QtWidgets.QCheckBox(self.label.text())
            self.widgets[1] = self.label
            self.label.stateChanged.connect(self._hideability_changed)
            self._hideability_changed(True)
            QT_APP.processEvents()

        self.lock = threading.Lock()

        self.value_changed.connect(self._check_sufficiency)
        self.interactivity_changed.connect(self._check_sufficiency)

    def _check_sufficiency(self, event=None):
        new_sufficiency = bool(self.value()) and self.interactive

        LOGGER.debug('Sufficiency for %s %s --> %s', self,
                     self.sufficient, new_sufficiency)

        if self.sufficient != new_sufficiency:
            self.sufficient = new_sufficiency
            self.sufficiency_changed.emit(new_sufficiency)


    def __del__(self):
        if self._validation_thread != None:
            if self._validation_thread.isRunning():
                self._validation_thread.quit()
                self._validation_thread.wait(msecs=200)
                if self._validation_thread.isRunning():
                    self._validation_thread.terminate()
            self._validation_thread.deleteLater()

    def _validate(self):
        self.lock.acquire()

        try:
            # When input is required but has no value, note requirement without
            # starting a thread.
            if self.required:
                if not self.value():
                    LOGGER.info('Validation: input is required and has no value')
                    self.valid_button.set_errors(['Input is required'])
                    self._validation_finished(new_validity=False)
                    return

                if self.value() and not self.args_key:
                    warnings.warn(('Validation: %s instance has no args_key, but '
                                'must to validate.  Skipping.') %
                                self.__class__.__name__)
                    self._validation_finished(new_validity=True)
                    return

            if self.validator:
                LOGGER.info('Validation: validator taken from self.validator: %s',
                            self.validator)
                validator_ref = self.validator
            else:
                if not self.args_key:
                    LOGGER.info(('Validation: No validator and no args_id defined; '
                                 'skipping.  Input assumed to be valid. %s'),
                                self)
                    self._validation_finished(new_validity=True)
                    return
                else:
                    # args key defined, but a validator is not; input assumed
                    # to be valid.
                    LOGGER.info(('Validation: args_key defined, but no '
                                 'validator defined.  Input assumed to be '
                                 'valid. %s'), self)
                    self._validation_finished(new_validity=True)
                    return

            try:
                args = self.parent().assemble_args()
            except AttributeError:
                # When self.parent() is not set, as in testing.
                # self.parent() is only set when the Input is added to a layout.
                args = {self.args_key: self.value()}

            LOGGER.info(
                ('Starting validation thread for %s with target:%s, args:%s, '
                 'limit_to:%s'),
                self, validator_ref, args, self.args_key)
            if not self._validation_thread or not self._validation_thread.isRunning():
                self._validation_thread = QtCore.QThread(parent=self)
                self._validation_thread.start()

            self._validation_worker = ValidationWorker(
                target=validator_ref,
                args=args,
                limit_to=self.args_key)
            self._validation_worker.moveToThread(self._validation_thread)
            self._validation_worker.finished.connect(
                self._validation_thread_finished)
            self._validation_worker.start()

            QT_APP.processEvents()
        except Exception:
            QT_APP.processEvents()
            LOGGER.exception('Error found when validating %s, releasing lock.',
                             self)
            self.lock.release()
            raise
        QT_APP.processEvents()

    def _validation_finished(self, new_validity):
        LOGGER.info('Cleaning up validation for %s', self)
        current_validity = self._valid
        self._valid = new_validity
        self.lock.release()
        if current_validity != new_validity:
            self.validity_changed.emit(new_validity)

    def _validation_thread_finished(self):
        self._validation_thread.quit()

        LOGGER.info('Validation thread finished for %s', self)
        warnings_ = [w[1] for w in self._validation_worker.warnings
                     if self.args_key in w[0]]
        self.valid_button.set_errors(warnings_)
        new_validity = len(warnings_) == 0
        self._validation_finished(new_validity)
        self._validation_worker.deleteLater()

    def valid(self):
        # TODO: wait until the lock is released.
        try:
            while not self._validation_worker.isFinished():
                QtCore.QThread.msleep(50)
            return self._valid
        except AttributeError:
            # When validation threads aren't part of the equation.
            return self._valid

    @QtCore.Slot(int)
    def _hideability_changed(self, show_widgets):
        for widget in self.widgets[2:]:
            if not widget:
                continue
            widget.setHidden(not bool(show_widgets))
        self.hidden_changed.emit(bool(show_widgets))

    @QtCore.Slot(int)
    def set_hidden(self, hidden):
        if not self.hideable:
            raise ValueError('Input is not hideable.')
        self.label.setChecked(not hidden)

    def hidden(self):
        if self.hideable:
            return not self.label.isChecked()
        return False


class Text(GriddedInput):
    def __init__(self, label, helptext=None, required=False, interactive=True,
                 args_key=None, hideable=False, validator=None):
        GriddedInput.__init__(self, label=label, helptext=helptext,
                              required=required, interactive=interactive,
                              args_key=args_key, hideable=hideable,
                              validator=validator)
        self.textfield = QtWidgets.QLineEdit()
        self.textfield.textChanged.connect(self._text_changed)
        self.widgets[2] = self.textfield

    def _text_changed(self, new_text):
        self.dirty = True
        self.value_changed.emit(new_text)
        self._validate()

    def value(self):
        return self.textfield.text()

    def set_value(self, value):
        if value and self.hideable:
            self.set_hidden(False)

        if isinstance(value, int) or isinstance(value, float):
            value = str(value)
        self.textfield.setText(value)


class _Path(Text):
    def __init__(self, label, helptext=None, required=False, interactive=True,
                 args_key=None, hideable=False, validator=None):
        Text.__init__(self, label, helptext, required, interactive, args_key,
                      hideable, validator=validator)

        self.widgets = [
            self.valid_button,
            self.label,
            self.textfield,
            None,
            self.help_button,
        ]


class Folder(_Path):
    def __init__(self, label, helptext=None, required=False, interactive=True,
                 args_key=None, hideable=False, validator=None):
        _Path.__init__(self, label, helptext, required, interactive, args_key,
                       hideable, validator=validator)
        self.path_select_button = FolderButton('Select folder')
        self.path_select_button.path_selected.connect(self.textfield.setText)
        self.widgets[3] = self.path_select_button

        if self.hideable:
            self._hideability_changed(False)


class File(_Path):
    def __init__(self, label, helptext=None, required=False, interactive=True,
                 args_key=None, hideable=False, validator=None):
        _Path.__init__(self, label, helptext, required, interactive, args_key,
                       hideable, validator=validator)
        self.path_select_button = FileButton('Select file')
        self.path_select_button.path_selected.connect(self.textfield.setText)
        self.widgets[3] = self.path_select_button

        if self.hideable:
            self._hideability_changed(False)


class Checkbox(GriddedInput):

    # Re-setting value_changed to adapt to the type requirement.
    value_changed = QtCore.Signal(bool)
    # Re-setting interactivity_changed to avoid a segfault while testing on
    # linux via `python setup.py nosetests`.
    interactivity_changed = QtCore.Signal(bool)

    def __init__(self, label, helptext=None, interactive=True, args_key=None):
        GriddedInput.__init__(self, label=label, helptext=helptext,
                              interactive=interactive, args_key=args_key,
                              hideable=False, validator=None)

        self.checkbox = QtWidgets.QCheckBox(label)
        self.checkbox.stateChanged.connect(self.value_changed.emit)
        self.widgets[0] = None  # No need for a valid button
        self.widgets[1] = self.checkbox  # replace label with checkbox

    def value(self):
        return self.checkbox.isChecked()

    def valid(self):
        return True

    def set_value(self, value):
        self.checkbox.setChecked(value)


class Dropdown(GriddedInput):
    def __init__(self, label, helptext=None, interactive=True, args_key=None,
                 hideable=False, options=()):
        GriddedInput.__init__(self, label=label, helptext=helptext,
                              interactive=interactive, args_key=args_key,
                              hideable=hideable, validator=None)
        self.dropdown = QtWidgets.QComboBox()
        self.widgets[2] = self.dropdown
        self.set_options(options)
        self.dropdown.currentIndexChanged.connect(self._index_changed)

        # Init hideability if needed
        if self.hideable:
            self._hideability_changed(False)

    def _index_changed(self, newindex):
        self.value_changed.emit(self.options[newindex])

    def set_options(self, options):
        self.dropdown.clear()
        cast_options = []
        for label in options:
            if type(label) in (int, float):
                label = str(label)
            cast_value = six.text_type(label, 'utf-8')
            self.dropdown.addItem(cast_value)
            cast_options.append(cast_value)
        self.options = cast_options
        self.user_options = options

    def value(self):
        return self.dropdown.currentText()

    def set_value(self, value):
        # Handle case where value is of the type provided by the user,
        # and the case where it's been converted to a utf-8 string.
        try:
            index = self.options.index(value)
        except (IndexError, ValueError):
            index = self.user_options.index(value)
        self.dropdown.setCurrentIndex(index)


class Label(QtWidgets.QLabel):
    def __init__(self, *args, **kwargs):
        QtWidgets.QLabel.__init__(self, *args, **kwargs)
        self.setWordWrap(True)
        self.setOpenExternalLinks(True)

    def _add_to(self, layout):
        layout.addWidget(self, layout.rowCount(),  # target row
                         0,  # target starting column
                         1,  # row span
                         layout.columnCount())  # span all columns


class Container(QtWidgets.QGroupBox, Input):

    # need to redefine signals here.
    value_changed = QtCore.Signal(bool)
    interactivity_changed = QtCore.Signal(bool)

    def __init__(self, label, interactive=True, expandable=False,
                 expanded=True, args_key=None):
        QtWidgets.QGroupBox.__init__(self)
        Input.__init__(self, label=label, interactive=interactive,
                       args_key=args_key)
        self.setCheckable(expandable)
        if self.isCheckable():
            self.setChecked(expanded)
        self.setTitle(label)
        self.setLayout(QtWidgets.QGridLayout())
        self.toggled.connect(self.value_changed.emit)

    @property
    def expanded(self):
        if self.expandable:
            return self.isChecked()
        return True

    @expanded.setter
    def expanded(self, value):
        if not self.expandable:
            raise ValueError('Container cannot be expanded when not '
                             'expandable')
        return self.setChecked(value)

    @property
    def expandable(self):
        return self.isCheckable()

    @expandable.setter
    def expandable(self, value):
        return self.setCheckable(value)

    def add_input(self, input):
        input._add_to(layout=self.layout())

    def _add_to(self, layout):
        layout.addWidget(self,
                         layout.rowCount(),  # target row
                         0,  # target starting column
                         1,  # row span
                         layout.columnCount())  # span all columns

    def value(self):
        return self.expanded

    def set_value(self, value):
        self.expanded = value


class Multi(Container):

    value_changed = QtCore.Signal(list)

    class _RemoveButton(QtWidgets.QPushButton):

        remove_requested = QtCore.Signal(int)

        def __init__(self, label, index):
            QtWidgets.QPushButton.__init__(self, label)
            self.index = index
            self.clicked.connect(self._remove)

        def _remove(self, checked=False):
            self.remove_requested.emit(self.index)

    def __init__(self, label, callable_, interactive=True, args_key=None,
                 link_text='Add Another'):
        Container.__init__(self,
                           label=label,
                           interactive=interactive,
                           args_key=args_key,
                           expandable=False,
                           expanded=True)

        if not hasattr(callable_, '__call__'):
            raise ValueError("Callable passed to Multi is not callable.")

        self.callable_ = callable_
        self.add_link = QtWidgets.QLabel('<a href="add_new">%s</a>' % link_text)
        self.add_link.linkActivated.connect(self._add_templated_item)
        self._append_add_link()
        self.items = []
        self.remove_buttons = []

    def value(self):
        return [input_.value() for input_ in self.items]

    def set_value(self, *values):
        self.clear()
        for input_value in values:
            new_input_instance = self.callable_()
            new_input_instance.set_value(input_value)
            self.add_item(new_input_instance)

        self.value_changed.emit(list(values))

    def _add_templated_item(self, label=None):
        self.add_item()

    def add_item(self, new_input=None):
        if not new_input:
            new_input = self.callable_()

        new_input._add_to(self.layout())
        self.items.append(new_input)

        layout = self.layout()
        rightmost_item = layout.itemAtPosition(
            layout.rowCount()-1, layout.columnCount()-1)
        if not rightmost_item:
            col_index = layout.columnCount()-1
        else:
            col_index = layout.columnCount()

        new_remove_button = Multi._RemoveButton(
            '-R-', index=max(0, len(self.items)-1))
        new_remove_button.remove_requested.connect(self.remove)
        self.remove_buttons.append(new_remove_button)

        layout.addWidget(new_remove_button,
                         layout.rowCount()-1,  # current last row
                         col_index,
                         1,  # span 1 row
                         1)  # span 1 column

    def _append_add_link(self):
        layout = self.layout()
        layout.addWidget(self.add_link,
                         layout.rowCount(),  # make new last row
                         0,  # target starting column
                         1,  # row span
                         layout.columnCount())  # span all columns

    def clear(self):
        layout = self.layout()
        for i in reversed(range(layout.count())):
            layout.itemAt(i).widget().setParent(None)
        self._append_add_link()

    def remove(self, index):
        # clear all widgets from the layout.
        self.clear()

        self.items.pop(index)
        self.remove_buttons.pop(index)
        old_items = self.items[:]
        self.items = []
        self.remove_buttons = []
        for item in old_items:
            self.add_item(item)


class Form(QtWidgets.QWidget):

    submitted = QtCore.Signal()
    run_finished = QtCore.Signal()

    def __init__(self):
        QtWidgets.QWidget.__init__(self)

        self.setLayout(QtWidgets.QVBoxLayout())

        self.inputs = Container(label='')
        self.inputs.setFlat(True)
        self.layout().addWidget(self.inputs)

        self.buttonbox = QtWidgets.QDialogButtonBox()
        self.run_button = QtWidgets.QPushButton(' Run')
        self.run_button.setIcon(QtGui.QIcon(ICON_ENTER))

        self.buttonbox.addButton(
            self.run_button, QtWidgets.QDialogButtonBox.AcceptRole)
        self.layout().addWidget(self.buttonbox)
        self.run_button.pressed.connect(self.submitted.emit)

        self.run_dialog = FileSystemRunDialog()

    def run(self, target, logfile=None, args=(), kwargs=None, tempdir=None,
            window_title='', out_folder='/'):

        if not hasattr(target, '__call__'):
            raise ValueError('Target %s must be callable' % target)

        self._thread = execution.Executor(target,
                                          args,
                                          kwargs,
                                          logfile=logfile,
                                          tempdir=tempdir)
        self._thread.finished.connect(self._run_finished)

        self.run_dialog.start(window_title=window_title,
                              out_folder=out_folder)
        QT_APP.processEvents()
        self.run_dialog.show()
        QT_APP.processEvents()
        self._thread.start()

    def _run_finished(self):
        # When the thread finishes.
        self.run_dialog.finish(
            exception_found=(self._thread.exception is not None),
            thread_exception=self._thread.exception)
        self.run_finished.emit()

    def showEvent(self, event=None):
        _apply_sizehint(self.inputs)
        # adjust the window size when we show it.
        screen_geometry = QtWidgets.QDesktopWidget().availableGeometry()

        # 50 pads the width by a scrollbar or so
        # 100 pads the width for the scrollbar and a little more.
        width = min(screen_geometry.width()-50,
                    self.inputs.minimumSizeHint().width()+100)

        screen_height = screen_geometry.height() * 0.95
        # 100 pads the height for buttons, menu bars.
        height = min(self.inputs.minimumSizeHint().height()+100, screen_height)

        self.resize(width, height)
        self.raise_()  # bring the window to the front.  Needed on macs.
        QtWidgets.QWidget.showEvent(self, event)

    def add_input(self, input):
        self.inputs.add_input(input)

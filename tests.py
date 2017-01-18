
import unittest
import functools
import warnings
import time
import threading
import io
import logging
import tempfile
import shutil
import os

import mock
from PyQt4 import QtCore
from PyQt4 import QtGui
from PyQt4.QtTest import QTest


class PyQtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # QApplication needs to be set up before we make any Qt widgets.
        cls._APP = QtGui.QApplication.instance()
        if not cls._APP:
            cls._APP = QtGui.QApplication([''])

    @classmethod
    def tearDownClass(cls):
        cls._APP.quit()


class InputTest(PyQtTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import Input
        return Input(*args, **kwargs)

    def test_label(self):
        input_instance = self.__class__.create_input(label='foo')
        self.assertEqual(input_instance.label, 'foo')

    def test_helptext(self):
        input_instance = self.__class__.create_input(label='foo', helptext='bar')
        self.assertEqual(input_instance.helptext, 'bar')

    def test_required(self):
        input_instance = self.__class__.create_input(label='foo', required=True)
        self.assertEqual(input_instance.required, True)

    def test_nonrequired(self):
        input_instance = self.__class__.create_input(label='foo', required=False)
        self.assertEqual(input_instance.required, False)

    def test_interactive(self):
        input_instance = self.__class__.create_input(label='foo', interactive=True)
        self.assertEqual(input_instance.interactive, True)

    def test_noninteractive(self):
        input_instance = self.__class__.create_input(label='foo', interactive=False)
        self.assertEqual(input_instance.interactive, False)

    def test_set_interactive(self):
        input_instance = self.__class__.create_input(label='foo', interactive=False)
        self.assertEqual(input_instance.interactive, False)
        input_instance.set_interactive(True)
        self.assertEqual(input_instance.interactive, True)

    def test_interactivity_changed(self):
        input_instance = self.__class__.create_input(label='foo', interactive=False)
        callback = mock.MagicMock()
        input_instance.interactivity_changed.connect(callback)
        input_instance.set_interactive(True)
        callback.assert_called_with(True)

    def test_add_to_layout(self):
        base_widget = QtGui.QWidget()
        base_widget.setLayout(QtGui.QGridLayout())

        input_instance = self.__class__.create_input(label='foo')
        input_instance._add_to(base_widget.layout())

    def test_value(self):
        input_instance = self.__class__.create_input(label='foo')
        if input_instance.__class__.__name__ in ('Input', 'GriddedInput'):
            with self.assertRaises(NotImplementedError):
                input_instance.value()
        else:
            self.fail('Test class must reimplement this test method')

    def test_set_value(self):
        input_instance = self.__class__.create_input(label='foo')
        if input_instance.__class__.__name__ in ('Input', 'GriddedInput'):
            with self.assertRaises(NotImplementedError):
                input_instance.set_value()
        else:
            self.fail('Test class must reimplement this test method')

    def test_value_changed_signal_emitted(self):
        input_instance = self.__class__.create_input(label='some_label')
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)

        if input_instance.__class__.__name__ in ('Input', 'GriddedInput'):
            with self.assertRaises(NotImplementedError):
                self.assertEqual(input_instance.value(), '')
                input_instance.set_value('foo')
                callback.assert_called_with(u'foo')
        else:
            self.fail('Test class must reimplement this test method')

    def test_value_changed_signal(self):
        input_instance = self.__class__.create_input(label='foo')
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)
        input_instance.value_changed.emit(unicode('value', 'utf-8'))

        callback.assert_called_with(unicode('value', 'utf-8'))

    def test_interactivity_changed_signal(self):
        input_instance = self.__class__.create_input(label='foo')
        callback = mock.MagicMock()
        input_instance.interactivity_changed.connect(callback)
        input_instance.interactivity_changed.emit(True)

        callback.assert_called_with(True)

    def test_args_key(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     args_key='some_key')
        self.assertEqual(input_instance.args_key, 'some_key')

    def test_no_args_key(self):
        input_instance = self.__class__.create_input(label='foo')
        self.assertEqual(input_instance.args_key, None)

    def test_add_to_container(self):
        from natcap.ui.inputs import Container
        input_instance = self.__class__.create_input(label='foo')
        container = Container(label='Some container')
        container.add_input(input_instance)


class GriddedInputTest(InputTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import GriddedInput
        return GriddedInput(*args, **kwargs)

    def test_label(self):
        input_instance = self.__class__.create_input(label='foo')
        label_text = unicode(input_instance.label.text(), 'utf-8')
        self.assertEqual(label_text,  u'foo (Optional)')

    def test_label_required(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     required=True)
        label_text = unicode(input_instance.label.text(), 'utf-8')
        self.assertEqual(label_text, 'foo')

    def test_validator(self):
        _callback = mock.MagicMock()
        input_instance = self.__class__.create_input(
            label='foo', validator=_callback)
        self.assertEqual(input_instance.validator, _callback)

    def test_helptext(self):
        from natcap.ui.inputs import HelpButton
        input_instance = self.__class__.create_input(label='foo',
                                                     helptext='bar')
        self.assertTrue(isinstance(input_instance.help_button, HelpButton))

    def test_no_helptext(self):
        input_instance = self.__class__.create_input(label='foo')
        self.assertTrue(isinstance(input_instance.help_button, type(None)))

    def test_validate_passes(self):
        """UI: Validation that passes should affect validity."""
        _validation_func = mock.MagicMock(return_value=[])
        input_instance = self.__class__.create_input(
            label='some_label', args_key='some_key',
            validator=_validation_func)
        try:
            input_instance.value()
        except NotImplementedError:
            input_instance.value = lambda: 'value!'

        input_instance._validate()

        # Wait for validation to finish.
        self.assertEqual(input_instance.valid(), True)

    def test_validate_fails(self):
        """UI: Validation that fails should affect validity."""
        _validation_func = mock.MagicMock(
            return_value=[('some_key', 'some warning')])
        input_instance = self.__class__.create_input(
            label='some_label', args_key='some_key',
            validator=_validation_func)
        try:
            input_instance.value()
        except NotImplementedError:
            input_instance.value = lambda: 'value!'

        input_instance._validate()
        self._APP.processEvents()

        # Wait for validation to finish and assert Failure.
        self.assertEqual(input_instance.valid(), False)

    def test_validate_required(self):
        """UI: Requirement with no input should affect validity."""
        input_instance = self.__class__.create_input(
            label='some_label', required=True)
        try:
            input_instance.value()
        except NotImplementedError:
            input_instance.value = lambda: ''

        self.assertEqual(input_instance.valid(), True)
        input_instance._validate()
        # Wait for validation to finish and assert Failure.
        self.assertEqual(input_instance.valid(), False)

    def test_validate_required_args_key(self):
        """UI: Requirement with no input should raise a warning."""
        input_instance = self.__class__.create_input(
            label='some_label', required=True)

        input_instance.value = mock.MagicMock(
            input_instance, return_value=u'something')

        self.assertEqual(input_instance.valid(), True)
        with warnings.catch_warnings(record=True) as messages:
            input_instance._validate()

        # Validation still passes, but verify warning raised
        self.assertEqual(len(messages), 1)
        self.assertEqual(input_instance.valid(), True)

    def test_validate_parent_required(self):
        input_instance = self.__class__.create_input(
            label='some_label', required=True, args_key='something')

        input_instance.value = mock.MagicMock(
            input_instance, return_value=u'something else')

        with self.assertRaises(RuntimeError):
            input_instance._validate()

    def test_validate_target_required(self):
        input_instance = self.__class__.create_input(
            label='some_label', required=True, args_key='something')
        input_instance.value = mock.MagicMock(
            input_instance, return_value=u'something else')

        class _SampleModule(object):
            __name__ = '_SampleModule'

        class _SampleParent(object):
            target = _SampleModule()

        input_instance.parent = mock.MagicMock(return_value=_SampleParent())
        with self.assertRaises(RuntimeError):
            input_instance._validate()


    def test_nonhideable_default_state(self):
        sample_widget = QtGui.QWidget()
        sample_widget.setLayout(QtGui.QGridLayout())
        input_instance = self.__class__.create_input(
            label='some_label', hideable=False)
        input_instance._add_to(sample_widget.layout())
        sample_widget.show()

        self.assertEqual(input_instance.hideable, False)
        self.assertEqual(input_instance.hidden(), False)

        for widget, hidden in zip(input_instance.widgets,
                                  [False, False, False, False, False]):
            if not widget:
                continue
            if not widget.isHidden() == hidden:
                self.fail('Widget %s hidden: %s, expected: %s' % (
                    widget, widget.isHidden(), hidden))

    def test_nonhideable_set_hidden_fails(self):
        input_instance = self.__class__.create_input(
            label='some_label', hideable=False)
        with self.assertRaises(ValueError):
            input_instance.set_hidden(False)

    def test_hideable_set_hidden(self):
        sample_widget = QtGui.QWidget()
        sample_widget.setLayout(QtGui.QGridLayout())
        input_instance = self.__class__.create_input(
            label='some_label', hideable=True)
        input_instance._add_to(sample_widget.layout())
        sample_widget.show()

        self.assertEqual(input_instance.hidden(), True)  # default is hidden
        input_instance.set_hidden(False)
        self.assertEqual(input_instance.hidden(), False)
        for widget, hidden in zip(input_instance.widgets,
                                  [False, False, False, False, False]):
            if not widget:
                continue
            if not widget.isHidden() == hidden:
                self.fail('Widget %s hidden: %s, expected: %s' % (
                    widget, widget.isHidden(), hidden))

        input_instance.set_hidden(True)
        self.assertEqual(input_instance.hidden(), True)
        for widget, hidden in zip(input_instance.widgets,
                                  [False, False, True, True, True]):
            if not widget:
                continue
            if not widget.isHidden() == hidden:
                self.fail('Widget %s hidden: %s, expected: %s' % (
                    widget, widget.isHidden(), hidden))

    def test_hidden_change_signal(self):
        input_instance = self.__class__.create_input(
            label='some_label', hideable=True)
        callback = mock.MagicMock()
        input_instance.hidden_changed.connect(callback)
        self.assertEqual(input_instance.hidden(), True)
        input_instance.set_hidden(False)
        callback.assert_called_with(True)

    def test_hidden_when_not_hideable(self):
        """UI: Verify non-hideable Text input has expected behavior."""
        input_instance = self.__class__.create_input(
            label='Some label', hideable=False)

        self.assertEqual(input_instance.hideable, False)
        self.assertEqual(input_instance.hidden(), False)

        with self.assertRaises(ValueError):
            input_instance.set_hidden(True)


class TextTest(GriddedInputTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import Text
        return Text(*args, **kwargs)

    def test_value(self):
        input_instance = self.__class__.create_input(label='text')
        self.assertEqual(input_instance.value(), '')
        self.assertTrue(isinstance(input_instance.value(), unicode))

    def test_set_value(self):
        input_instance = self.__class__.create_input(label='text')
        self.assertEqual(input_instance.value(), '')
        input_instance.set_value('foo')
        self.assertEqual(input_instance.value(), u'foo')
        self.assertTrue(isinstance(input_instance.value(), unicode))

    def test_value_changed_signal_emitted(self):
        input_instance = self.__class__.create_input(label='text')
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)

        self.assertEqual(input_instance.value(), '')
        input_instance.set_value('foo')
        callback.assert_called_with(u'foo')

    def test_textfield_settext(self):
        input_instance = self.__class__.create_input(label='text')

        input_instance.textfield.setText('foo')
        self.assertEqual(input_instance.value(), u'foo')
        self.assertTrue(isinstance(input_instance.value(), unicode))

    def test_textfield_settext_signal(self):
        input_instance = self.__class__.create_input(label='text')
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)

        input_instance.textfield.setText('foo')
        callback.assert_called_with(u'foo')


class PathTest(TextTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import _Path
        return _Path(*args, **kwargs)

    def test_path_selected(self):
        input_instance = self.__class__.create_input(label='foo')
        # Only run this test on subclasses of path
        if input_instance.__class__.__name__ != '_Path':
            input_instance.path_select_button.path_selected.emit(u'/tmp/foo')
            self.assertTrue(input_instance.value(), '/tmp/foo')


class FolderTest(PathTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import Folder
        return Folder(*args, **kwargs)


class FileTest(PathTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import File
        return File(*args, **kwargs)


class CheckboxTest(GriddedInputTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import Checkbox
        return Checkbox(*args, **kwargs)

    def test_value(self):
        input_instance = self.__class__.create_input(label='new_label')
        self.assertEqual(input_instance.value(), False)  # default value

        # set the value using the qt method
        input_instance.checkbox.setChecked(True)
        self.assertEqual(input_instance.value(), True)

    def test_set_value(self):
        input_instance = self.__class__.create_input(label='new_label')
        self.assertEqual(input_instance.value(), False)
        input_instance.set_value(True)
        self.assertEqual(input_instance.value(), True)

    def test_value_changed_signal_emitted(self):
        input_instance = self.__class__.create_input(label='new_label')
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)
        self.assertEqual(input_instance.value(), False)
        input_instance.set_value(True)
        callback.assert_called_with(True)

    def test_value_changed_signal(self):
        input_instance = self.__class__.create_input(label='new_label')
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)
        input_instance.value_changed.emit(True)
        callback.assert_called_with(True)

    def test_valid(self):
        input_instance = self.__class__.create_input(label='new_label')
        self.assertEqual(input_instance.value(), False)
        self.assertEqual(input_instance.valid(), True)
        input_instance.set_value(True)
        self.assertEqual(input_instance.valid(), True)

    def test_validator(self):
        pass

    def test_validate_required(self):
        pass

    def test_validate_passes(self):
        pass

    def test_validate_fails(self):
        pass

    def test_required(self):
        pass

    def test_nonrequired(self):
        pass

    def test_nonhideable_set_hidden_fails(self):
        pass

    def test_nonhideable_default_state(self):
        pass

    def test_label_required(self):
        pass

    def test_hideable_set_hidden(self):
        pass

    def test_hidden_when_not_hideable(self):
        pass

    def test_hidden_change_signal(self):
        pass

    def test_validate_required_args_key(self):
        pass

    def test_validate_parent_required(self):
        pass

    def test_validate_target_required(self):
        pass


class DropdownTest(GriddedInputTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import Dropdown
        return Dropdown(*args, **kwargs)

    def test_options(self):
        input_instance = self.__class__.create_input(
            label='label', options=('foo', 'bar', 'baz'))
        self.assertEqual(input_instance.options, [u'foo', u'bar', u'baz'])

    def test_options_typecast(self):
        input_instance = self.__class__.create_input(
            label='label', options=(1, 2, 3))
        self.assertEqual(input_instance.options, [u'1', u'2', u'3'])

    def test_set_value(self):
        input_instance = self.__class__.create_input(
            label='label', options=('foo', 'bar', 'baz'))
        input_instance.set_value('foo')
        self.assertEqual(input_instance.value(), u'foo')

    def test_set_value_noncast(self):
        input_instance = self.__class__.create_input(
            label='label', options=(1, 2, 3))
        input_instance.set_value(1)
        self.assertEqual(input_instance.value(), u'1')

    def test_value(self):
        input_instance = self.__class__.create_input(
            label='label', options=('foo', 'bar', 'baz'))
        self.assertEqual(input_instance.value(), u'foo')
        self.assertTrue(isinstance(input_instance.value(), unicode))

    def test_value_changed_signal_emitted(self):
        input_instance = self.__class__.create_input(
            label='label', options=('foo', 'bar', 'baz'))
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)
        self.assertEqual(input_instance.value(), u'foo')
        input_instance.set_value('bar')
        callback.assert_called_with('bar')

    def test_validator(self):
        pass

    def test_validate_required(self):
        pass

    def test_validate_passes(self):
        pass

    def test_validate_fails(self):
        pass

    def test_required(self):
        pass

    def test_nonrequired(self):
        pass

    def test_label_required(self):
        pass

    def test_validate_required_args_key(self):
        pass

    def test_validate_parent_required(self):
        pass

    def test_validate_target_required(self):
        pass


class LabelTest(unittest.TestCase):
    def test_add_to_layout(self):
        from natcap.ui.inputs import Label

        super_widget = QtGui.QWidget()
        super_widget.setLayout(QtGui.QGridLayout())
        label = Label('Hello, World!')
        label._add_to(super_widget.layout())


class ContainerTest(InputTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import Container
        return Container(*args, **kwargs)

    def test_expandable(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     expandable=False)

        self.assertEqual(input_instance.expandable, False)
        self.assertEqual(input_instance.expanded, True)

        input_instance.expandable = True
        self.assertEqual(input_instance.expandable, True)

    def test_expanded(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     expandable=True,
                                                     expanded=True)

        self.assertEqual(input_instance.expandable, True)
        self.assertEqual(input_instance.expanded, True)

        input_instance.expanded = False
        self.assertEqual(input_instance.expanded, False)

    def test_value_changed_signal(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     expandable=True)
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)
        input_instance.value_changed.emit(True)
        callback.assert_called_with(True)

    def test_value_changed_signal_emitted(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     expandable=True,
                                                     expanded=False)
        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)
        self.assertEqual(input_instance.value(), False)
        input_instance.set_value(True)
        self._APP.processEvents()
        callback.assert_called_with(True)

    def test_value(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     expandable=True)

        input_instance.setChecked(False)
        self.assertEqual(input_instance.value(), False)
        input_instance.setChecked(True)
        self.assertEqual(input_instance.value(), True)

    def test_set_value(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     expandable=True,
                                                     expanded=False)

        self.assertEqual(input_instance.value(), False)
        input_instance.set_value(True)
        self.assertEqual(input_instance.value(), True)

    def test_set_value_nonexpandable(self):
        input_instance = self.__class__.create_input(label='foo',
                                                     expandable=False)
        with self.assertRaises(ValueError):
            input_instance.set_value(False)

    def test_helptext(self):
        pass

    def test_nonrequired(self):
        pass

    def test_required(self):
        pass


class MultiTest(ContainerTest):
    @staticmethod
    def create_input(*args, **kwargs):
        from natcap.ui.inputs import Multi

        if 'callable_' not in kwargs:
            kwargs['callable_'] = MultiTest.create_sample_callable(
                label='some text')
        return Multi(*args, **kwargs)

    @staticmethod
    def create_sample_callable(*args, **kwargs):
        from natcap.ui.inputs import Text
        return functools.partial(Text, *args, **kwargs)

    def test_setup_callable_not_callable(self):
        with self.assertRaises(ValueError):
            self.__class__.create_input(
                label='foo',
                callable_=None)

    def test_value_changed_signal_emitted(self):
        input_instance = self.__class__.create_input(
            label='foo',
            callable_=self.__class__.create_sample_callable(label='foo'))

        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)
        self.assertEqual(input_instance.value(), [])
        input_instance.set_value('aaa', 'bbb')
        self._APP.processEvents()
        callback.assert_called_with(['aaa', 'bbb'])

    def test_value_changed_signal(self):
        input_instance = self.__class__.create_input(
            label='foo',
            callable_=self.__class__.create_sample_callable(label='foo'))

        callback = mock.MagicMock()
        input_instance.value_changed.connect(callback)
        self.assertEqual(input_instance.value(), [])
        input_instance.value_changed.emit(['aaa', 'bbb'])
        self._APP.processEvents()
        callback.assert_called_with(['aaa', 'bbb'])

    def test_value(self):
        input_instance = self.__class__.create_input(
            label='foo',
            callable_=self.__class__.create_sample_callable(label='foo'))

        self.assertEqual(input_instance.value(), [])  # default value

    def test_set_value(self):
        input_instance = self.__class__.create_input(
            label='foo',
            callable_=self.__class__.create_sample_callable(label='foo'))

        self.assertEqual(input_instance.value(), [])  # default value
        input_instance.set_value('aaa', 'bbb')
        self.assertEqual(input_instance.value(), ['aaa', 'bbb'])

    def test_remove_item_by_button(self):
        input_instance = self.__class__.create_input(
            label='foo',
            callable_=self.__class__.create_sample_callable(label='foo'))

        self.assertEqual(input_instance.value(), [])  # default value
        input_instance.set_value('aaa', 'bbb', 'ccc')
        self.assertEqual(input_instance.value(), ['aaa', 'bbb', 'ccc'])

        # reach into the Multi and press the 'bbb' remove button
        QTest.mouseClick(input_instance.remove_buttons[1],
                         QtCore.Qt.LeftButton)

        self.assertEqual(input_instance.value(), ['aaa', 'ccc'])

    def test_add_item_by_link(self):
        input_instance = self.__class__.create_input(
            label='foo',
            callable_=self.__class__.create_sample_callable(label='foo'))
        input_instance.add_link.linkActivated.emit('add_new')

        self._APP.processEvents()
        self.assertEqual(input_instance.value(), [''])

    def test_set_value_nonexpandable(self):
        pass

    def test_expanded(self):
        pass

    def test_expandable(self):
        pass


class ValidationWorkerTest(PyQtTest):
    def test_run(self):
        from natcap.ui.inputs import ValidationWorker
        _callable = mock.MagicMock(return_value=[])
        worker = ValidationWorker(
            target=_callable,
            args={'foo': 'bar'},
            limit_to='foo')
        worker.start()
        while not worker.isFinished():
            QTest.qWait(50)
        self.assertEqual(worker.warnings, [])
        self.assertEqual(worker.error, None)

    def test_error(self):
        from natcap.ui.inputs import ValidationWorker
        _callable = mock.MagicMock(side_effect=KeyError('missing'))
        worker = ValidationWorker(
            target=_callable,
            args={'foo': 'bar'},
            limit_to='foo')
        worker.start()
        while not worker.isFinished():
            QTest.qWait(50)
        self.assertEqual(worker.warnings, [])
        self.assertEqual(worker.error, "'missing'")


class FileButtonTest(PyQtTest):
    def test_button_clicked(self):
        from natcap.ui.inputs import FileButton
        button = FileButton('Some title')

        # Patch up the open_method to return a known path.
        # Would block on user input otherwise.
        button.open_method = mock.MagicMock(return_value='/some/path')
        _callback = mock.MagicMock()
        button.path_selected.connect(_callback)

        QTest.mouseClick(button, QtCore.Qt.LeftButton)
        self._APP.processEvents()
        _callback.assert_called_with('/some/path')

    def test_button_title(self):
        from natcap.ui.inputs import FileButton
        button = FileButton('Some title')
        self.assertEqual(button.dialog_title, 'Some title')


class FolderButtonTest(PyQtTest):
    def test_button_clicked(self):
        from natcap.ui.inputs import FolderButton
        button = FolderButton('Some title')

        # Patch up the open_method to return a known path.
        # Would block on user input otherwise.
        button.open_method = mock.MagicMock(return_value='/some/path')
        _callback = mock.MagicMock()
        button.path_selected.connect(_callback)

        QTest.mouseClick(button, QtCore.Qt.LeftButton)
        self._APP.processEvents()
        _callback.assert_called_with('/some/path')

    def test_button_title(self):
        from natcap.ui.inputs import FolderButton
        button = FolderButton('Some title')
        self.assertEqual(button.dialog_title, 'Some title')


class FileDialogTest(PyQtTest):
    def test_save_file_title_and_last_selection(self):
        from natcap.ui.inputs import FileDialog, DATA
        dialog = FileDialog()
        dialog.getSaveFileName = mock.MagicMock(
            spec=dialog.getSaveFileName,
            return_value='/new/file')

        DATA['last_dir'] = '/tmp/foo/bar'

        out_file = dialog.save_file(title='foo', start_dir=None)
        self.assertEqual(dialog.getSaveFileName.call_args[0],  # pos. args
                         (dialog, 'foo', '/tmp/foo/bar'))
        self.assertEqual(out_file, '/new/file')
        self.assertEqual(DATA['last_dir'], u'/new')

    def test_save_file_defined_savefile(self):
        from natcap.ui.inputs import FileDialog
        dialog = FileDialog()
        dialog.getSaveFileName = mock.MagicMock(
            spec=dialog.getSaveFileName,
            return_value='/new/file')

        out_file = dialog.save_file(title='foo', start_dir='/tmp',
                                    savefile='file.txt')
        self.assertEqual(dialog.getSaveFileName.call_args[0],  # pos. args
                         (dialog, 'foo', '/tmp/file.txt'))

    def test_open_file(self):
        from natcap.ui.inputs import FileDialog, DATA
        dialog = FileDialog()

        # patch up the Qt method to get the path to the file to open
        dialog.getOpenFileName = mock.MagicMock(
            spec=dialog.getOpenFileName,
            return_value='/new/file')

        DATA['last_dir'] = '/tmp/foo/bar'

        out_file = dialog.open_file(title='foo')
        self.assertEqual(dialog.getOpenFileName.call_args[0],  # pos. args
                         (dialog, 'foo', '/tmp/foo/bar'))
        self.assertEqual(out_file, '/new/file')
        self.assertEqual(DATA['last_dir'], '/new')

    def test_open_folder(self):
        from natcap.ui.inputs import FileDialog, DATA
        dialog = FileDialog()

        # patch up the Qt method to get the path to the file to open
        dialog.getExistingDirectory = mock.MagicMock(
            spec=dialog.getExistingDirectory,
            return_value='/existing/folder')

        DATA['last_dir'] = '/tmp/foo/bar'
        new_folder = dialog.open_folder('foo', start_dir=None)

        self.assertEqual(dialog.getExistingDirectory.call_args[0],
                         (dialog, 'Select folder: foo', '/tmp/foo/bar'))
        self.assertEqual(new_folder, '/existing/folder')
        self.assertEqual(DATA['last_dir'], '/existing/folder')


class InfoButtonTest(PyQtTest):
    @unittest.skip("'Always segfaults, don't know why")
    def test_buttonpress(self):
        from natcap.ui.inputs import InfoButton
        button = InfoButton('some text')
        self._APP.processEvents()
        self.assertEqual(button.whatsThis(), 'some text')

        # Execute this, for coverage.
        button.show()
        self._APP.processEvents()
        QTest.mouseClick(button, QtCore.Qt.LeftButton)
        self._APP.processEvents()
        self.assertTrue(QtGui.QWhatsThis.inWhatsThisMode())

class ModelUITest(PyQtTest):
    @staticmethod
    def validate(args, limit_to=None):
        return []

    @staticmethod
    def execute(args, limit_to=None):
        pass

    @staticmethod
    def make_ui(docpage=None, target_mod=None):
        from natcap.ui.inputs import InVESTModelForm

        if not target_mod:
            target_mod = ModelUITest

        class Sample(InVESTModelForm):
            label = 'Sample UI'
            target = target_mod
            localdoc = docpage

            def assemble_args(self):
                return {
                    self.workspace.args_key: self.workspace.value(),
                    self.suffix.args_key: self.suffix.value(),
                }

        return Sample()

    def test_with_docs(self):
        form = ModelUITest.make_ui(docpage='foo.html')
        self.assertTrue('foo.html' in form.links.text())
        self.assertEqual(len(form.links.text().split('|')), 3)

    def test_without_docs(self):
        form = ModelUITest.make_ui(docpage=None)
        # links widget will contain version and forums link, no docs.
        self.assertEqual(len(form.links.text().split('|')), 2)

    def test_run_noerror(self):
        import natcap.ui.inputs
        form = ModelUITest.make_ui()
        form.run()
        form._thread.join()
        self._APP.processEvents()

        # At the end of the run, the button should be visible.
        self.assertTrue(form.run_dialog.openWorkspaceButton.isVisible())

        with mock.patch('natcap.ui.inputs.open_workspace'):
            # press the openWorkspaceButton, verify open_workspace called once
            QTest.mouseClick(form.run_dialog.openWorkspaceButton,
                             QtCore.Qt.LeftButton)
            self._APP.processEvents()
            natcap.ui.inputs.open_workspace.assert_called_once()

        # close the window by pressing the back button.
        QTest.mouseClick(form.run_dialog.backButton,
                         QtCore.Qt.LeftButton)
        self.assertFalse(form.run_dialog.isVisible())

    def test_open_workspace_on_success(self):
        import natcap.ui.inputs
        thread_event = threading.Event()

        class _SampleTarget(object):
            @staticmethod
            def validate(args, limit_to=None):
                return []

            @staticmethod
            def execute(args):
                thread_event.wait()

        form = ModelUITest.make_ui(target_mod=_SampleTarget())
        form.run()
        self._APP.processEvents()

        self.assertTrue(form.run_dialog.openWorkspaceCB.isVisible())
        self.assertFalse(form.run_dialog.openWorkspaceButton.isVisible())

        form.run_dialog.openWorkspaceCB.setChecked(True)
        self._APP.processEvents()
        self.assertTrue(form.run_dialog.openWorkspaceCB.isChecked())

        with mock.patch('natcap.ui.inputs.open_workspace'):
            natcap.ui.inputs.open_workspace.assert_not_called()
            thread_event.set()
            self._APP.processEvents()
            form._thread.join()
            while form._thread.is_alive():
                QTest.QWait(50)
                self._APP.processEvents()
            natcap.ui.inputs.open_workspace.assert_called_once()

        # close the window by pressing the back button.
        QTest.mouseClick(form.run_dialog.backButton,
                         QtCore.Qt.LeftButton)
        self.assertFalse(form.run_dialog.isVisible())

    def test_run_prevent_dialog_close_esc(self):
        thread_event = threading.Event()

        class _SampleTarget(object):
            @staticmethod
            def validate(args, limit_to=None):
                return []

            @staticmethod
            def execute(args):
                thread_event.wait()

        form = ModelUITest.make_ui(target_mod=_SampleTarget())
        form.run()
        self._APP.processEvents()
        QTest.keyPress(form.run_dialog, QtCore.Qt.Key_Escape)
        self._APP.processEvents()
        self.assertTrue(form.run_dialog.isVisible())

        # when the execute function finishes, pressing escape should
        # close the window.
        thread_event.set()
        self._APP.processEvents()
        QTest.keyPress(form.run_dialog, QtCore.Qt.Key_Escape)
        self.assertEqual(form.run_dialog.result(), QtGui.QDialog.Rejected)
        self._APP.processEvents()
        self.assertEqual(form.run_dialog.result(), QtGui.QDialog.Rejected)
        self._APP.processEvents()

    def test_run_prevent_dialog_close_event(self):
        thread_event = threading.Event()

        class _SampleTarget(object):
            @staticmethod
            def validate(args, limit_to=None):
                return []

            @staticmethod
            def execute(args):
                thread_event.wait()

        form = ModelUITest.make_ui(target_mod=_SampleTarget())
        form.run()
        self._APP.processEvents()
        form.run_dialog.close()
        self._APP.processEvents()
        self.assertTrue(form.run_dialog.isVisible())

        # when the execute function finishes, pressing escape should
        # close the window.
        thread_event.set()
        form._thread.join()
        self._APP.processEvents()
        form.run_dialog.close()
        self._APP.processEvents()
        self.assertFalse(form.run_dialog.isVisible())

    def test_run_error(self):
        class _SampleTarget(object):
            @staticmethod
            def validate(args, limit_to=None):
                return []

            @staticmethod
            def execute(args):
                raise RuntimeError('Something broke!')

        form = ModelUITest.make_ui(target_mod=_SampleTarget())
        form.run()
        form._thread.join()
        self._APP.processEvents()

        self.assertTrue('encountered' in form.run_dialog.messageArea.text())

    def test_show(self):
        form = ModelUITest.make_ui()
        form.show()


class OpenWorkspaceTest(unittest.TestCase):
    def test_windows(self):
        from natcap.ui.inputs import open_workspace
        with mock.patch('subprocess.Popen') as method:
            with mock.patch('platform.system', return_value='Windows'):
                open_workspace('/foo/bar')
                method.assert_called_with('explorer "/foo/bar"')

    def test_mac(self):
        from natcap.ui.inputs import open_workspace
        with mock.patch('subprocess.Popen') as method:
            with mock.patch('platform.system', return_value='Darwin'):
                open_workspace('/foo/bar')
                method.assert_called_with('open /foo/bar', shell=True)

    def test_linux(self):
        from natcap.ui.inputs import open_workspace
        with mock.patch('subprocess.Popen') as method:
            with mock.patch('platform.system', return_value='Linux'):
                open_workspace('/foo/bar')
                method.assert_called_with(['xdg-open', '/foo/bar'])

    def test_error_in_subprocess(self):
        from natcap.ui.inputs import open_workspace
        with mock.patch('subprocess.Popen',
                        side_effect=OSError('error message')) as patch:
            open_workspace('/foo/bar')
            patch.assert_called_once()


class ExecutionTest(unittest.TestCase):
    def test_print_args(self):
        from natcap.ui.execution import _format_args

        args = {
            'some_arg': [1, 2, 3, 4],
            'foo': 'bar',
        }

        args_string = _format_args(args_dict=args)
        expected_string = unicode(
            'Arguments:\n'
            'foo      bar\n'
            'some_arg [1, 2, 3, 4]\n')
        self.assertEqual(args_string, expected_string)

    def test_format_time_hours(self):
        from natcap.ui.execution import format_time

        seconds = 3667
        self.assertEqual(format_time(seconds), '1h 1m 7s')

    def test_format_time_minutes(self):
        from natcap.ui.execution import format_time

        seconds = 67
        self.assertEqual(format_time(seconds), '1m 7s')

    def test_format_time_seconds(self):
        from natcap.ui.execution import format_time

        seconds = 7
        self.assertEqual(format_time(seconds), '7s')

    def test_thread_filter_same_thread(self):
        from natcap.ui.execution import ThreadFilter

        # name, level, pathname, lineno, msg, args, exc_info, func=None
        record = logging.LogRecord(
            name='foo',
            level=logging.INFO,
            pathname=__file__,
            lineno=500,
            msg='some logging message',
            args=(),
            exc_info=None,
            func='test_thread_filter_same_thread')
        filterer = ThreadFilter(threading.currentThread().name)

        # The record comes from the same thread.
        self.assertEqual(filterer.filter(record), True)

    def test_thread_filter_different_thread(self):
        from natcap.ui.execution import ThreadFilter

        # name, level, pathname, lineno, msg, args, exc_info, func=None
        record = logging.LogRecord(
            name='foo',
            level=logging.INFO,
            pathname=__file__,
            lineno=500,
            msg='some logging message',
            args=(),
            exc_info=None,
            func='test_thread_filter_same_thread')
        filterer = ThreadFilter('Thread-nonexistent')

        # The record comes from the same thread.
        self.assertEqual(filterer.filter(record), False)

    def test_log_to_file(self):
        class _LogThread(threading.Thread):
            def __init__(self, filename):
                threading.Thread.__init__(self)
                self.filename = filename
                self.event = threading.Event()

            def run(self):
                from natcap.ui.execution import log_to_file
                with log_to_file(self.filename):
                    _logger = logging.getLogger(__name__)
                    _logger.debug('debug message')
                    _logger.info('info message')
                    self.event.wait()
                    _logger.warning('warning message')
                    _logger.error('error message')
                    _logger.critical('critical message')

        tempdir = tempfile.mkdtemp()
        try:
            logfilepath = os.path.join(tempdir, 'logfile.txt')

            # Ensure that the logfile can overwrite existing logfiles.
            with open(logfilepath, 'w') as logfile:
                logfile.write('This logfile already exists!')

            test_thread = _LogThread(logfilepath)
            test_thread.start()

            # inject a logmessage that should not appear
            _root_logger = logging.getLogger()
            _root_logger.info('this should not appear')
            test_thread.event.set()  # Resume threaded logging
            test_thread.join()

            # read the file, ensure only 5 lines.
            # "this should not appear" should not be in the text, either.
            with open(logfilepath) as logfile:
                file_contents = logfile.read().strip()
                self.assertEqual(len(file_contents.split('\n')), 5)
                self.assertTrue('this should not appear' not in file_contents)
        finally:
            shutil.rmtree(tempdir)

import threading
import os
import logging
import time
import pprint
import traceback
import contextlib

from PyQt4 import QtCore

LOGGER = logging.getLogger(__name__)
LOG_FMT = "%(asctime)s %(name)-18s %(levelname)-8s %(message)s"
DATE_FMT = "%m/%d/%Y %H:%M:%S "


def _format_args(args_dict):
    sorted_args = sorted(args_dict.iteritems(), key=lambda x: x[0])

    max_key_width = 0
    if len(sorted_args) > 0:
        max_key_width = max(len(x[0]) for x in sorted_args)

    format_str = u"%-" + unicode(str(max_key_width)) + u"s %s"

    args_string = u'\n'.join([format_str % (arg) for arg in sorted_args])
    args_string = u"Arguments:\n%s\n" % args_string
    return args_string


def format_time(seconds):
    """Render the integer number of seconds as a string.  Returns a string.
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    hours = int(hours)
    minutes = int(minutes)

    if hours > 0:
        return "%sh %sm %ss" % (hours, minutes, seconds)

    if minutes > 0:
        return "%sm %ss" % (minutes, seconds)
    return "%ss" % seconds


class ThreadFilter(logging.Filter):
    """When used, this filters out log messages that were recorded from other
    threads.  This is especially useful if we have logging coming from several
    concurrent threads.
    Arguments passed to the constructor:
        thread_name - the name of the thread to identify.  If the record was
            reported from this thread name, it will be passed on.
    """
    def __init__(self, thread_name):
        logging.Filter.__init__(self)
        self.thread_name = thread_name

    def filter(self, record):
        if record.threadName == self.thread_name:
            return True
        return False


@contextlib.contextmanager
def log_to_file(logfile):
    if os.path.exists(logfile):
        LOGGER.warn('Logfile %s exists and will be overwritten', logfile)

    handler = logging.FileHandler(logfile, 'w', encoding='UTF-8')
    formatter = logging.Formatter(LOG_FMT, DATE_FMT)
    thread_filter = ThreadFilter(threading.current_thread().name)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.NOTSET)  # capture everything
    root_logger.addHandler(handler)
    handler.addFilter(thread_filter)
    handler.setFormatter(formatter)
    yield
    handler.close()
    root_logger.removeHandler(handler)

class Executor(QtCore.QObject, threading.Thread):
    """Executor represents a thread of control that runs a python function with
    a single input.  Once created with the proper inputs, threading.Thread has
    the following attributes:
        self.module - the loaded module object provided to __init__()
        self.args   - the argument to the target function.  Usually a dict.
        self.func_name - the function name that will be called.
        self.log_manager - the LogManager instance managing logs for this script
        self.failed - defaults to False.  Indicates whether the thread raised an
            exception while running.
        self.execption - defaults to None.  If not None, points to the exception
            raised while running the thread.
    The Executor.run() function is an overridden function from threading.Thread
    and is started in the same manner by calling Executor.start().  The run()
    function is extremely simple by design: Print the arguments to the logfile
    and run the specified function.  If an execption is raised, it is printed
    and saved locally for retrieval later on.
    In keeping with convention, a single Executor thread instance is only
    designed to be run once.  To run the same function again, it is best to
    create a new Executor instance and run that."""

    finished = QtCore.pyqtSignal()

    def __init__(self, module, args, func_name='execute', log_file=None, tempdir=None):
        """Initialization function for the Executor.
            module - a python module that has already been imported.
            args - a python dictionary of arguments to be passed to the function
            func_name='execute'- a string.  Represents the name of the function
                to be called (e.g. module.func_name).  Defaults to 'execute'.
        """
        QtCore.QObject.__init__(self)
        threading.Thread.__init__(self)
        self.module = module
        self.args = args
        self.func_name = func_name
        self.failed = False
        self.exception = None
        self.traceback = None
        self.tempdir = tempdir

    def run(self):
        """Run the python script provided by the user with the arguments
        specified.  This function also prints the arguments to the logfile
        handler.  If an exception is raised in either the loading or execution
        of the module or function, a traceback is printed and the exception is
        saved."""
        logfile = os.path.join(self.args['workspace_dir'], 'foo.txt')
        with log_to_file(logfile):
            start_time = time.time()
            LOGGER.info(_format_args(self.args))
            try:
                function = getattr(self.module, self.func_name)
            except AttributeError as error:
                LOGGER.exception(error)
                self.failed = True
                raise AttributeError(('Unable to find function "%s" in module "%s" '
                    'at %s') % (self.func_name, self.module.__name__,
                    self.module.__file__))
            try:
                LOGGER.debug('Found function %s', function)
                LOGGER.debug('Starting model with args: \n%s',
                            pprint.pformat(self.args))
                function(self.args)
            except Exception as error:
                # We deliberately want to catch all possible exceptions.
                LOGGER.exception(error)
                self.failed = True
                self.exception = error
                self.traceback = traceback.format_exc()
            finally:
                elapsed_time = round(time.time() - start_time, 2)
                LOGGER.info('Elapsed time: %s', format_time(elapsed_time))
                LOGGER.info('Execution finished')

        self.finished.emit()

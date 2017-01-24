import threading
import os
import logging
import time
import pprint
import traceback
import contextlib
import tempfile

from qtpy import QtCore


LOGGER = logging.getLogger(__name__)
LOG_FMT = "%(asctime)s %(name)-18s %(levelname)-8s %(message)s"
DATE_FMT = "%m/%d/%Y %H:%M:%S "


def _format_args(args_iterable, args_dict):
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


@contextlib.contextmanager
def manage_tempdir(new_tempdir=None):
    """Context manager for resetting the previous tempfile.tempdir.

    When the context manager is exited, ``tempfile.tempdir`` is reset to its
    previous value.

    Parameters:
        new_tempdir (string): The folder that should be the new temporary
            directory.  If None, the system default will be used.  See
            https://docs.python.org/2/library/tempfile.html#tempfile.tempdir
            for details.

    Returns:
        ``None``
    """
    LOGGER.info('Setting tempfile.tempdir to %s', new_tempdir)
    previous_tempdir = tempfile.tempdir
    tempfile.tempdir = new_tempdir
    yield
    LOGGER.info('Resetting tempfile.tempdir to %s', previous_tempdir)
    tempfile.tempdir = previous_tempdir


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

    finished = QtCore.Signal()

    def __init__(self, target, args, kwargs, logfile, tempdir=None):
        QtCore.QObject.__init__(self)
        threading.Thread.__init__(self)
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.logfile = logfile
        self.tempdir = tempdir

        self.failed = False
        self.exception = None
        self.traceback = None

    def run(self):
        """Run the python script provided by the user with the arguments
        specified.  This function also prints the arguments to the logfile
        handler.  If an exception is raised in either the loading or execution
        of the module or function, a traceback is printed and the exception is
        saved."""
        with log_to_file(self.logfile), manage_tempdir(self.tempdir):
            start_time = time.time()

            try:
                LOGGER.debug('Starting target %s with args: \n%s\n%s',
                             self.target,
                             pprint.pformat(self.args),
                             pprint.pformat(self.kwargs))
                self.target(*self.args, **self.kwargs)
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

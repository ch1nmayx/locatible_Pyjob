"""
This module contains the implementation of logging facilities
for the events produced by the *Job Manager* and *Job Monitors*.
"""

import logging
from datetime import datetime


class MonitorLog(object):
    """
    Logs events produced by a *Job Monitor* or *Database* handler.
    """

    def __init__(self, job_id, truck_id, level, prefix):
        """
        Constructs a *Job Monitor* event logger.
        The log file is opened in the *logs* folder.

        :param job_id: The job ID.
        :type job_id: int
        :param truck_id: The truck ID.
        :type truck_id: int
        :param level: The logging level.
        :type level: str
        :param prefix: The log file name prefix (either *JM* or *DB*).
        :type prefix: str
        """
        log_date = str(datetime.strftime(datetime.now(), '%y%m%d_%H%M%S'))
        if level == 'debug':
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO
        self.logger = logging.getLogger('logger_{}_{}'.format(job_id, prefix))
        log_format = "%(message)s"
        logging.basicConfig(format=log_format, level=log_level)
        # file handler
        file_handler = logging.FileHandler('logs/{}_{}_T{}_J{}.log'.format(prefix,
                                                                           log_date,
                                                                           truck_id,
                                                                           job_id))
        file_handler.setLevel(log_level)
        formatter = logging.Formatter(log_format)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def info(self, message):
        """
        Logs the specified message at the *info* level.

        :param message: The message to log.

        """
        self.logger.info(message)

    def debug(self, message):
        """
        Logs the specified message at the *debug* level.

        :param message: The message to log.

        """
        self.logger.debug(message)


class ManagerLog(object):
    """
    Logs events produced by the *Job Manager*.
    """

    def __init__(self, level):
        """
        Constructs a *Job Manager* event logger.
        The log file is opened at *logs/job_manager/log.log*.

        :param level: The logging level.
        :type level: str
        """
        log_date = str(datetime.strftime(datetime.now(), '%y%m%d_%H%M%S'))
        if level == 'debug':
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO
        self.logger = logging.getLogger('job_manager_log')
        log_format = "[%(asctime)s]: %(message)s"
        logging.basicConfig(format=log_format, level=log_level)
        file_handler = logging.FileHandler('logs/job_manager/{}.log'.format(log_date))
        file_handler.setLevel(log_level)
        formatter = logging.Formatter(log_format)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def info(self, message):
        """
        Logs the specified message at the *info* level.

        :param message: The message to log.

        """
        self.logger.info(message)

    def debug(self, message):
        """
        Logs the specified message at the *debug* level.

        :param message: The message to log.

        """
        self.logger.debug(message)

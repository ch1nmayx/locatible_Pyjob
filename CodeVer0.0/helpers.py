"""
Miscellaneous utility functions.
"""

import sys
import json
from datetime import datetime
from math import sqrt


def get_distance(coord1, coord2):
    """
    Returns the distance between two 2D coordinates.

    :param coord1: The first 2D coordinate.
    :param coord2: The second 2D coordinate.
    :returns: The distance between the specified coordinates.
    :rtype: number

    """
    coord1_x = coord1['x']
    coord1_y = coord1['y']
    coord2_x = coord2['x']
    coord2_y = coord2['y']
    return sqrt(((coord1_x - coord2_x) ** 2) + ((coord1_y - coord2_y) ** 2))


def get_time_delta(prev_loc_time, curr_loc_time):
    """
    Returns the difference between two timestamps.

    :param prev_loc_time: The earlier timestamp.
    :type prev_loc_time: str
    :param curr_loc_time: The latter timestamp.
    :type curr_loc_time: str
    :returns: The difference between the specified timestamps, in seconds
    :rtype: number

    """
    curr_time = datetime.strptime(curr_loc_time, '%Y-%m-%d %H:%M:%S.%f')
    prev_time = datetime.strptime(prev_loc_time, '%Y-%m-%d %H:%M:%S.%f')
    time_diff = curr_time - prev_time
    return time_diff.total_seconds()


def get_config():
    """
    Loads and parses the configuration file.

    :returns: The loaded configuration.
    :rtype: dictionary
    """

    param_requirements = {'pickup_check_distance_trigger': (float, int),
                          'pickup_check_distance_window': (float, int),
                          'pickup_post_seconds': (float, int),
                          'drop_check_distance': (float, int),
                          'drop_pre_seconds': (float, int),
                          'job_manager_port': int,
                          'rfid_wait_timeout': int,
                          'database_name': str,
                          'database_password': str,
                          'database_user': str,
                          'database_host': str,
                          'activate_queries': bool}
    try:
        with open('config.txt', 'r') as config_file:
            file_data = config_file.read()
    except EnvironmentError:
        sys.exit('error opening config file')
    try:
        config = json.loads(file_data)
    except ValueError as exception:
        sys.exit('Invalid configuration file format: {}'.format(exception))
    for param in param_requirements:
        if param not in config:
            sys.exit('config file does not contain required parameter: {}'.format(param))
        if not isinstance(config[param], param_requirements[param]):
            sys.exit('Invalid value for parameter {}: {}'.format(param, config[param]))
    return config

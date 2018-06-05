"""
This module contains the *Job Manager* implementation.

The *Job Manager* works as a Flask app that exposes an
endpoint used to start jobs through POST requests.

The POST request handler is defined at
:func:`start_job <job_manager.start_job>`.
"""

import json
from multiprocessing import Process

import mysql.connector
from flask import Flask, request
from flask_cors import CORS

from helpers import get_config
from job_monitor import JobMonitor
from logger import ManagerLog

CONFIG = get_config()
LOGGER = ManagerLog('info')
JOB_MANAGER_PORT = CONFIG['job_manager_port']
DATABASE_NAME = CONFIG['database_name']
DATABASE_PASSWORD = CONFIG['database_password']
DATABASE_USER = CONFIG['database_user']
DATABASE_HOST = CONFIG['database_host']
APP = Flask(__name__)
# allow cross origin requests
CORS(APP)


@APP.route('/job_manager/start_job', methods=['POST'])
def start_job():
    """
    Starts a new :class:`Job Monitor <job_monitor.JobMonitor>`.

    This method handles incoming POST requests, whose content
    must specify the ID of the job to monitor.

    This implementation first extracts the truck ID using the
    job ID specified in the JSON request, by invoking
    :func:`get_job_truck <job_manager.get_job_truck>`.

    Then, before stopping the previous *Job Monitor* that
    monitored the same truck and starting the new one, the
    existence of active tasks is checked by invoking
    :func:`check_for_active_tasks <job_manager.check_for_active_tasks>`.

    The *Job Monitor* is started with
    :func:`start_job_monitor <job_manager.start_job_monitor>`.

    :returns: A JSON formatted string with the request result.
    :rtype: str
    """
    job_id = None
    try:
        job_data = request.get_json()
        job_id = job_data.get('job_id')
        if not job_id:
            message = 'Missing data: job_id={}'.format(job_id)
            LOGGER.info(message)
            return json.dumps({'error': message})

        LOGGER.info('Starting job {}'.format(job_id))
        db_handle, cursor = connect_to_db()
        truck_id = get_job_truck(job_id, cursor)
        if not truck_id:
            message = 'Missing data: truck_id={}'.format(truck_id)
            LOGGER.info(message)
            return json.dumps({'error': message})
        else:
            LOGGER.info('Truck id is {}'.format(truck_id))

        if check_for_active_tasks(truck_id, cursor):
            db_handle.close()
            message = 'Cannot start job {} as truck {} has active tasks'.format(job_id, truck_id)
            LOGGER.info(message)
            return json.dumps({'error': message})
        stop_previous_job_monitor(truck_id, db_handle, cursor)
        start_job_monitor(job_id, truck_id, db_handle, cursor)
        db_handle.close()
        message = 'Job {} has been started'.format(job_id)
        LOGGER.info(message)
        return json.dumps({'success': message})
    except Exception as exc:
        import traceback
        exception_traceback = traceback.format_exc()
        message = 'Unexpected exception when starting job {}: {}'.format(job_id, exc)
        LOGGER.info('{}\n\n{}'.format(message, exception_traceback))
        return json.dumps({'error': message})


def get_job_truck(job_id, cursor):
    """
    Extracts the truck ID which the job was assigned to.

    :param job_id: The job ID.
    :type job_id: str
    :param cursor: The SQL cursor
    :type cursor: MySQLCursor
    :returns: The truck ID, if it was found.
    :rtype: int or None
    """
    sql = "SELECT d.clamp_id AS truck_id \
    FROM jobs j INNER JOIN clamp_driver d ON (j.driver_id = d.id) WHERE j.id={}".format(
        job_id)
    cursor.execute(sql)
    truck = cursor.fetchone()
    if truck:
        return truck['truck_id']
    return None


def check_for_active_tasks(truck_id, cursor):
    """
    Checks whether the monitored truck has still active
    tasks from its previous job.

    In this case, no new *Job Monitor* can be started.

    :param truck_id: The truck ID.
    :type truck_id: int
    :param cursor: The MySQL cursor.
    :type cursor: MySQLCursor
    :returns: *True* if there are active tasks, *False* otherwise.
    :rtype: bool
    """
    sql = "SELECT job_tasks.id, job_tasks.status FROM job_tasks \
    INNER JOIN jobs AS job ON (job_tasks.job_id = job.id) \
    INNER JOIN clamp_driver AS cd ON (job.driver_id = cd.id) \
    WHERE job.active=1 AND cd.clamp_id={} AND job_tasks.status=0".format(truck_id)
    cursor.execute(sql)
    active_tasks = cursor.fetchall()
    if active_tasks:
        return True
    return False


def stop_previous_job_monitor(truck_id, db_handle, cursor):
    """
    Stops the previous *Job Monitor* for the specified truck,
    by setting its *active* field in the database to **0**.

    :param truck_id: The truck ID.
    :type truck_id: int
    :param db_handle: The database handle.
    :type db_handle: MySQLConnection
    :param cursor: The MySQL cursor.
    :type cursor: MySQLCursor
    """
    sql = "UPDATE jobs j INNER JOIN clamp_driver d ON (j.driver_id = d.id) \
    SET active = 0 WHERE d.clamp_id = {} AND active = 1".format(
        truck_id)
    cursor.execute(sql)
    db_handle.commit()


def start_job_monitor(job_id, truck_id, db_handle, cursor):
    """
    Starts a new *Job Monitor* process for the specified truck and job.

    :param job_id: The job ID.
    :type job_id: int
    :param truck_id: The truck ID.
    :type truck_id: int
    :param db_handle: The database handle.
    :type db_handle: MySQLConnection
    :param cursor: The MySQL cursor.
    :type cursor: MySQLCursor
    """
    sql = "UPDATE jobs SET active=1 WHERE id={}".format(job_id)
    cursor.execute(sql)
    db_handle.commit()
    job_monitor = JobMonitor(job_id, truck_id, CONFIG)
    process = Process(target=job_monitor.run)
    process.daemon = True
    process.start()
    LOGGER.info('Job monitor process started for job {} with PID {}'.format(job_id, process.pid))


def connect_to_db():
    """
    Opens the connection to the MySQL database, using the IP
    address and credentials specified in the system configuration.

    :return: The database handle and cursor.
    :rtype: tuple
    """
    db_handle = mysql.connector.connect(user=DATABASE_USER,
                                        password=DATABASE_PASSWORD,
                                        host=DATABASE_HOST,
                                        database=DATABASE_NAME)
    cursor = db_handle.cursor(dictionary=True)
    cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;')
    return db_handle, cursor


if __name__ == '__main__':
    APP.run(port=JOB_MANAGER_PORT)

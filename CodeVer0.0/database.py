"""
Contains implementation of DB-related features.
"""

import time
from datetime import datetime, timedelta
import mysql.connector
from helpers import get_distance
from logger import MonitorLog


class Database(object):
    """ Implements all interactions with the DB. """

    def __init__(self, job_id, truck_id, config):
        """
        Constructs a *Database* handler for the specified job
        and truck.

        :param job_id: The job ID
        :type job_id: int
        :param truck_id: The truck ID
        :type truck_id: int
        :param config: The system configuration
        :type config: dict
        """
        self.config = config
        self.job_id = job_id
        self.truck_id = truck_id
        self.log = MonitorLog(job_id, truck_id, 'info', 'DB')
        self.db_connection = None
        self.cursor = None
        self.__init_db(config)
        self.active = bool(config['activate_queries'])

    def __init_db(self, config):
        """
        Initializes the MySQL Connector using the settings
        specified in the system configuration.

        :param config: The system configuration
        :type config: dict
        """
        self.db_connection = mysql.connector.connect(user=config['database_user'],
                                                     password=config['database_password'],
                                                     host=config['database_host'],
                                                     database=config['database_name'])
        self.cursor = self.db_connection.cursor(dictionary=True)
        self.cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;')

    def close_db(self):
        """
        Closes the connection to the DB.
        """
        self.db_connection.close()

    def is_job_active(self):
        """
        Returns whether the current job is active.

        :returns: Whether the current job is active, or has been
            manually deactivated.
        :rtype: bool
        """
        sql = "SELECT active FROM jobs WHERE id={}".format(self.job_id)
        self.cursor.execute(sql)
        job = self.cursor.fetchone()
        if job is None:
            return False
        if job['active'] == 1:
            return True
        return False

    def get_task_data(self):
        """
        Returns the list of tasks for the current job ID.

        :returns: The list of tasks that belong to this
            *Database* handler's assigned job ID.
        :rtype: list of dicts
        """
        sql = """
        SELECT jt.id, t.model, t.origin AS origin_id, t.destination AS destination_id
        FROM job_tasks AS jt
        INNER JOIN jobs AS j ON (jt.job_id = j.id)
        INNER JOIN tasks AS t ON (jt.task_id = t.id)
        INNER JOIN tasks_lists AS tl ON (t.task_list_id = tl.id)
        INNER JOIN geo_features AS o ON (t.origin = o.id)
        INNER JOIN geo_features AS d ON (t.destination = d.id)
        WHERE jt.job_id={}""".format(self.job_id)
        self.cursor.execute(sql)
        task_data = self.cursor.fetchall()
        tasks = []
        for task in task_data:
            tasks.append({
                'id': task['id'],
                'model': task['model'],
                'origin': task['origin_id'],
                'dest': task['destination_id']})
        return tasks

    def get_loc_data(self, curr_loc_time):
        """
        Returns all location data more recent than the specified time.

        :param curr_loc_time: The minimum timestamp of
            extracted location data.
        :type curr_loc_time: str
        :returns: The list of selected location data, sorted by timestamp
            in ascending order.
        :rtype: list of tuples
        """
        sql = """
        SELECT loc_data.geo_feature_id, x(coordinates) AS x, y(coordinates) AS y, timestamp, \
        speed, clamp_status, gf.type AS type FROM loc_data \
        INNER JOIN geo_features AS gf ON (loc_data.geo_feature_id = gf.id) \
        WHERE truck_id={} AND timestamp > '{}' \
        ORDER BY timestamp ASC""".format(self.truck_id, curr_loc_time)
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def has_active_alerts(self):
        """
        Returns whether this job has currently active alerts.

        :returns: *True* if the monitored job has active alerts
            (clamp event notifications are ignored by this check),
            *False* otherwise.
        :rtype: bool
        """
        sql = "SELECT id FROM alerts \
        WHERE job_id = {} \
        AND active = 1 AND type != 'clamps_closed_event'\
        AND type != 'clamps_closed_warning'".format(self.job_id)
        self.cursor.execute(sql)
        if not self.cursor.fetchall():
            return False
        return True

    def loc_has_active_dl_alerts(self, loc_id):
        """
        Returns whether the specified location has active
        *drop_location* alerts.

        :param loc_id: The location ID
        :type loc_id: int

        :returns: *True* if the monitored job has active
            alerts of type *drop_location*, *False* otherwise.
        :rtype: bool
        """
        sql = "SELECT id FROM alerts \
        WHERE job_id = {} \
        AND active = 1 AND type = 'drop_location' \
        AND loc_id = {}".format(self.job_id, loc_id)
        self.cursor.execute(sql)
        if not self.cursor.fetchall():
            return False
        return True

    def __wait_for_rfid_data(self, target_timestamp):
        """
        Waits until RFID data more recent than the specified timestamp is found.

        The wait times out after the number of seconds specified in the system
        configuration in the *rfid_wait_timeout* option.

        :param target_timestamp: The minimum RFID timestamp this method
            should wait for.
        :type target_timestamp: datetime
        """
        sql = "SELECT latest_rfid_timestamp \
        FROM clamp_trucks \
        WHERE id={}".format(self.truck_id)

        db_tvalue = datetime.strptime('1970-01-01 00:00:00.000', '%Y-%m-%d %H:%M:%S.%f')
        i = 0

        while target_timestamp > db_tvalue and i < self.config['rfid_wait_timeout']:
            self.cursor.execute(sql)
            result = self.cursor.fetchone()
            if result is None:
                return
            db_tvalue = result['latest_rfid_timestamp']
            self.log.info("Latest RFID timestamp is {}".format(db_tvalue))
            if db_tvalue is None or db_tvalue < target_timestamp:
                time.sleep(1)
            i += 1

    def __get_load_data(self, min_time, max_time):
        """
        Extracts all items detected by this truck in the specified time interval.

        This method internally waits for the RFID data of this time interval
        to be fully available, so the call may block for up to the number of seconds
        specified in the system configuration as *rfid_wait_timeout*.

        :param min_time: The start timestamp of the time interval
        :type min_time: datetime
        :param max_time: The end timestamp of the time interval
        :type max_time: datetime

        :returns: The list of items detected by the RFID reader in the specified
            time interval.
        :rtype: list of dicts
        """
        self.__wait_for_rfid_data(max_time)
        sql = "SELECT item.* FROM detected_items \
        INNER JOIN items AS item ON (detected_items.items_item_tag = item.item_tag) \
        WHERE clamp_truck_id={} AND timestamp >= '{}' AND timestamp <= '{}' \
        GROUP BY item.id".format(self.truck_id, min_time, max_time)
        self.log.info(sql)
        self.cursor.execute(sql)
        item_data = self.cursor.fetchall()
        items = []
        for item in item_data:
            items.append({
                'id': item['id'],
                'model': item['model'],
                'item_origin': item['curr_loc_id'],
                'serial_lock': item['serial_lock'],
                'correct_loc_id': None})
        return items

    def __get_load_data_inside_circle(self, event_coords, event_time):
        """
        Extracts all items detected by this truck within a circle centered
        on the specified coordinates. The radius of this circle is specified
        by the system configuration, in the **pickup_check_distance_window**
        option.

        This method is invoked when extracting item data for pickup events.
        It extracts RFID data from the following time window:

        - The window start is the lowest between 60 seconds before the
          pickup and the timestamp at which the clamp truck entered the
          circle centered around the pickup coordinates
        - The window end is the pickup time, incremented by the number
          of seconds specified by the system configuration, in the
          **pickup_post_seconds** option.

        This time window is internally passed to
        :func:`__get_load_data <database.Database._Database__get_load_data>`.

        :param event_coords: The pickup location
        :type event_coords: dict
        :param event_time: The pickup timestamp
        :type event_time: str

        :returns: The list of items detected by the RFID reader in the specified
            area.
        :rtype: list of dicts
        """
        max_time = datetime.strptime(event_time, '%Y-%m-%d %H:%M:%S.%f')
        min_time = max_time - timedelta(seconds=60)
        sql = "SELECT x(coordinates) AS x, y(coordinates) AS y, timestamp \
        FROM loc_data \
        WHERE truck_id={} AND timestamp >= '{}' AND timestamp <= '{}' \
        ORDER BY timestamp DESC".format(self.truck_id, min_time, max_time)
        self.cursor.execute(sql)
        loc_data = self.cursor.fetchall()
        load_query_start_time = min_time
        load_query_end_time = max_time + timedelta(seconds=self.config['pickup_post_seconds'])
        for location in loc_data:
            pickup_distance = get_distance(event_coords, location)
            if pickup_distance >= self.config['pickup_check_distance_window']:
                load_query_start_time = location['timestamp']
                break

        return self.__get_load_data(load_query_start_time, load_query_end_time)

    def get_drop_data(self, drop_time, max_time):
        """
        Extracts all items detected at this drop event.

        This method internally invokes
        :func:`__get_load_data <database.Database._Database__get_load_data>`
        with the following time window:

        - The start time is **drop_time** decremented by the number of seconds
          specified by the system configuration in the **drop_pre_seconds**
          option.
        - The end time is the specified **max_time**.

        :param drop_time: The timestamp of the drop event.
        :type drop_time: str
        :param max_time: The maximum timestamp of RFID data.
        :type max_time: str
        :returns: The list of items detected by the RFID reader in the specified
            time interval.
        :rtype: list of dicts
        """
        self.log.info("\nRetrieving data for drop at {}".format(drop_time))
        query_drop_time = datetime.strptime(drop_time, '%Y-%m-%d %H:%M:%S.%f')
        query_end_time = datetime.strptime(max_time, '%Y-%m-%d %H:%M:%S.%f')
        query_start_time = query_drop_time - timedelta(seconds=self.config['drop_pre_seconds'])
        return self.__get_load_data(query_start_time, query_end_time)

    def get_pickup_data(self, pickup_coords, pickup_time):
        """
        Extracts all item IDs detected at this pickup event.

        This method internally invokes
        :func:`__get_load_data_inside_circle
        <database.Database._Database__get_load_data_inside_circle>`
        with the pickup coordinates and time as arguments, and then
        unwraps the item IDs from the returned list of items.

        :param pickup_coords: The coordinates of the pickup event.
        :type pickup_coords: dict
        :param pickup_time: The timestamp of the pickup event.
        :type pickup_time: str
        :returns: The list of item IDs detected by the RFID reader at this pickup.
        :rtype: list of ints
        """
        self.log.info("\nRetrieving data for pickup at {} in {}".format(pickup_time, pickup_coords))
        inner_pickup_items = self.__get_load_data_inside_circle(pickup_coords, pickup_time)
        self.log.info('Pickup items: {}'.format(inner_pickup_items))

        inner_pickup_ids = []
        for item in inner_pickup_items:
            inner_pickup_ids.append(item['id'])

        self.log.info('Inner pickup IDs: {}'.format(inner_pickup_ids))
        return inner_pickup_ids

    def get_item_data(self, item_ids):
        """
        Used only to simulate scenarios, extracts full data of
        items with the specified IDs.
        :param item_ids: The IDs of the items to extract.
        :type item_ids: list of ints
        :return: Returns the item data.
        :rtype: list of dicts
        """
        if not item_ids:
            return []
        sql = 'SELECT * ' \
              'FROM items ' \
              'WHERE id IN ('
        sql += ','.join(str(item_id) for item_id in item_ids)
        sql += ')'
        self.cursor.execute(sql)
        item_data = self.cursor.fetchall()
        items = []
        for item in item_data:
            items.append({
                'id': item['id'],
                'model': item['model'],
                'item_origin': item['curr_loc_id'],
                'serial_lock': item['serial_lock'],
                'correct_loc_id': None})
        return items

    def save_item_loc(self, item, loc):
        """
        Updates the specified item's location in the DB.

        :param item: The item.
        :type item: dict
        :param loc: The item's new location.
        :type loc: int
        """
        sql = "UPDATE items SET curr_loc_id=%i WHERE id=%i" % (loc, item['id'])
        if self.active:
            self.cursor.execute(sql)
            self.db_connection.commit()
        # print(sql)

    def create_alert(self, alert_loc, alert_type, wrong_items, event_time):
        """
        Inserts a new alert into the DB.

        :param alert_loc: The location ID where the alert was generated.
        :type alert_loc: int
        :param alert_type: The alert type
        :type alert_type: str
        :param wrong_items: The list of wrong items related to this alert.
        :type wrong_items: list or None
        :param event_time: The event timestamp.
        :type event_time: str
        """
        sql = "INSERT INTO alerts \
        (loc_id, item_id, job_id, timestamp, type, active, correct_loc_id) VALUES "
        # if not wrong_items passed in then its a location only alert
        if not wrong_items:
            sql += "({}, NULL, {}, '{}', '{}', 1, NULL)".format(
                alert_loc, self.job_id, event_time, alert_type)
        else:
            for item in wrong_items:
                if item['correct_loc_id'] is None:
                    sql += "({}, '{}', {}, '{}', '{}', 1, NULL),".format(
                        alert_loc, item['id'], self.job_id, event_time, alert_type)
                else:
                    sql += "({}, '{}', {}, '{}', '{}', 1, {}),".format(
                        alert_loc, item['id'],
                        self.job_id, event_time, alert_type, item['correct_loc_id'])
            sql = sql.rstrip(',')
        if self.active:
            self.cursor.execute(sql)
            self.db_connection.commit()
        self.log.info(sql)

    def get_model_alerts(self, item):
        """
        Returns the active alerts that match the specified item's
        model, generated in the item's origin location.
        :param item: The item whose model and origin must match the alert.
        :type item: dict
        :return: The alert, or *None* if none is found.
        :rtype: list
        """
        sql = "SELECT a.id \
                FROM alerts a INNER JOIN items i ON (a.item_id = i.id) \
                WHERE a.job_id = {} \
                AND a.active = 1 AND a.loc_id = {} \
                AND i.model = '{}'".format(self.job_id, item['item_origin'], item['model'])
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def cancel_alert(self, alert_id):
        """
        Cancels the alert with the specified ID.
        :param alert_id: The ID of the alert to cancel.
        :type alert_id: int
        """
        if not self.active:
            return
        sql = "UPDATE alerts SET active = 0 \
        WHERE job_id = {} AND id = {}".format(self.job_id, alert_id)
        self.cursor.execute(sql)
        self.db_connection.commit()

    def cancel_alerts(self, alert_type):
        """
        Cancels all active alerts of the specified type.

        :param alert_type: The type of alerts to cancel.
        :type alert_type: str
        """
        if not self.active:
            return
        sql = "UPDATE alerts SET active = 0 \
        WHERE job_id = {} AND type = '{}'".format(self.job_id, alert_type)
        self.cursor.execute(sql)
        self.db_connection.commit()

    def cancel_item_alerts(self, items):
        """
        Cancels all alerts related to the specified items.

        :param items: The items whose alerts must be cancelled.
        :type items: list
        """
        if not self.active:
            return
        for item in items:
            sql = "UPDATE alerts SET active = 0 \
                  WHERE job_id = {} AND item_id = {}".format(self.job_id, item['id'])
            self.cursor.execute(sql)
            self.db_connection.commit()

    def cancel_model_alerts(self, model, loc_id):
        """
        Cancels all alerts related to a specific model and location.

        :param model: The model whose alerts must be cancelled.
        :type model: str
        :param loc_id: The location at which alerts must be cancelled.
        :type loc_id: int
        """
        if not self.active:
            return
        self.log.info('\nCanceling model alerts')
        sql = "UPDATE alerts a INNER JOIN items i ON (a.item_id = i.id) \
        SET a.active = 0 \
        WHERE i.model = '{}' AND a.job_id = {} \
        AND a.loc_id = {}".format(model, self.job_id, loc_id)
        self.log.info(sql)
        self.cursor.execute(sql)
        self.db_connection.commit()

    def cancel_remaining_tasks_alert(self, loc_id):
        """
        Cancels all missing tasks alerts at the specified location.

        :param loc_id: The location at which alerts must be cancelled.
        :type loc_id: int
        """
        sql = "UPDATE alerts SET active = 0 \
              WHERE type = 'remaining_tasks' \
              AND job_id = {} AND loc_id = {}".format(self.job_id, loc_id)
        if self.active:
            self.cursor.execute(sql)
            self.db_connection.commit()

    def save_job(self, start_time, finish_time, carries):
        """
        Updates job when it is completed.

        This method updates the job's row in the database, setting its
        status to *1*, and also updating the total number of carries and trips.
        The start and finish time are also updated with the actual start and
        completion timestamps.

        :param start_time: The job's start time.
        :type start_time: str
        :param finish_time: The job's completion time.
        :type finish_time: str
        :param carries: The carries detected during this job.
        :type carries: list
        """
        trip_count = 0
        for carry in carries:
            trip_count += len(carry.trips)
        sql = "UPDATE jobs SET start_time='{}', finish_time='{}', status=1, " \
              "total_carries={}, total_trips={} " \
              "WHERE id={} " \
            .format(start_time, finish_time, len(carries), trip_count, self.job_id)
        if self.active:
            self.cursor.execute(sql)
            self.db_connection.commit()
        # print('\n')
        # print(sql)

    def save_task(self, task):
        """
        Updates task when it is completed.

        In case the specified task is a correction task created when the
        driver dropped more correct items than requested, this method exits
        without performing any database operation, as corrective tasks are
        not stored in the DB.

        This method is invoked each time a task completion is detected at
        drop time.

        :param task: The completed task.
        :type task: :class:`Task <models.Task>`
        """
        sql = "UPDATE job_tasks \
                SET item_id={}, status=1, start_time='{}', finish_time='{}', avg_speed={} \
                WHERE id={}" \
            .format(task.item_id, task.start_time, task.finish_time, task.avg_speed, task.task_id)
        if self.active:
            self.cursor.execute(sql)
            self.db_connection.commit()

    def save_carries(self, carries):
        """
        Inserts all carries and trips into the DB.

        This method is invoked when the job is completed, and all carry
        and trip analytics have been generated.

        :param carries: The carries to insert into the database.
        :type carries: list of :class:`Carry <models.Carry>`
        """
        sql = "INSERT INTO carries (job_id, carry_number, start_time, finish_time, unit_count, "
        sql += "total_trips, origin, destination, stow_time, dock_time, total_distance, \
                avg_trip_distance, avg_trip_time) VALUES "
        for carry in carries:
            sql += "({}, {}, '{}', '{}', {}, {}, '{}', '{}', {}, {}, {}, {}, {})," \
                .format(
                    self.job_id,
                    carry.carry_num,
                    carry.start_time,
                    carry.finish_time,
                    carry.unit_count,
                    len(carry.trips),
                    carry.origin,
                    carry.dest,
                    int(carry.stow_time),
                    int(carry.dock_time),
                    carry.total_distance,
                    carry.avg_trip_distance,
                    carry.avg_trip_time)
        if self.active:
            self.cursor.execute(sql.rstrip(','))
            self.db_connection.commit()

        for carry in carries:
            self.__save_trips(carry)
        # print('\n')
        # print(sql)

    def __save_trips(self, carry):
        """
        Inserts all trips into the DB.

        This method is invoked by
        :func:`save_carries <database.Database.save_carries>`
        on each carry.

        :param carry: The carry whose trips must be inserted into the database.
        :type carry: :class:`Carry <models.Carry>`
        """
        sql = "INSERT INTO carry_trips (job_id, carry_number, origin, destination, distance, "
        sql += "avg_speed, travel_time, start_time, finish_time) VALUES "
        for trip in carry.trips:
            sql += "({}, {}, {}, {}, {}, {}, {}, '{}', '{}')," \
                .format(
                    self.job_id,
                    trip.carry_num,
                    trip.origin,
                    trip.dest,
                    trip.distance,
                    trip.avg_speed,
                    trip.travel_time,
                    trip.start_time,
                    trip.finish_time)
        self.log.info(sql)
        if self.active:
            self.cursor.execute(sql.rstrip(','))
            self.db_connection.commit()

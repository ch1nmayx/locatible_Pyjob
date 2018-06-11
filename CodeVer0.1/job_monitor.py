"""
Contains implementation of the job monitor's run loop
"""

import sys
import time
from datetime import datetime
from helpers import get_config, get_distance
from models import Carry, Task
from database import Database
from logger import MonitorLog


class JobMonitor(object):
    """
    Monitors a given truck and job.
    """
    # >>>>>>>>>>>>>>>>>>>>>>
    # the Location name in the 
    # The description of the NOE location in clase of the "Cannot_Place_Alert"/"Damaged item alert"
    __NOE_loc = 79
    ## name = 02TK149 
    ## geo_id = 79 (as extracted from the geo_features table)

    def __init__(self, job_id, truck_id, config=None):
        """
        Constructs a *Job Monitor* for the specified job and truck.

        :param job_id: The job ID
        :type job_id: int
        :param truck_id: The truck ID
        :type truck_id: int
        """
        # get contents of config file
        self.config = config if config is not None else get_config()
        # create the db
        self.db_connection = Database(job_id, truck_id, self.config)
        # short now time func
        self.now = lambda: str(datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S'))
        # create logger
        self.log = MonitorLog(job_id, truck_id, 'info', 'JM')
        # current location data, gotten from loc_data table
        self.curr_loc_id = None
        self.curr_loc_type = None
        self.curr_loc_time = None
        self.curr_loc_coords = None
        self.prev_loc_time = None
        self.pickup_check = False
        # store correct possible origins and destinations
        # which are location ids extracted from tasks
        self.correct_origins = []
        self.correct_dests = []
        self.pickup_history = []
        self.drop_history = []
        self.latest_pickup_item_ids = []
        # store tasks
        self.tasks = []
        self.task_completion_times = []
        self.speed_accumulator = []
        # store carries
        self.carries = []
        self.job_start_time = self.now()
        self.previous_clamp_status = 0
        self.set_tasks()

    def run(self):
        """
        The *Job Monitor*'s main run loop.

        This implementation extracts location and clamp data from the
        database in a loop, doing the following for each location tuple:

        - Detects pickup and drop events based on the clamp status
        - Keeps track of when to trigger the actual pickup or drop check
          once the clamp truck drives away from the pickup or drop location.
        - Invocations to
          :func:`check_drop <job_monitor.JobMonitor.check_drop>` and
          :func:`check_pickup <job_monitor.JobMonitor.check_pickup>`
          include the logic that checks task completion and carry/trip
          finalization.

        """
        curr_pickup_coords = None
        curr_pickup_time = None
        curr_drop_coords = None
        curr_drop_time = None
        loc_data_start_time = self.job_start_time
        drop_check = False
        active_pickup_event = False
        while True:
            time.sleep(0.2)
            # for manual job deactivation through the database
            self.is_job_active()
            loc_data = self.db_connection.get_loc_data(loc_data_start_time)
            for loc in loc_data:
                self.set_loc_data(loc)
                if not self.carries:
                    self.carries.append(Carry(1, self.curr_loc_time, self.curr_loc_id))
                self.update_carry_times()
                self.carries[-1].trips[-1].append_speed(loc['speed'])
                self.carries[-1].trips[-1].append_coords(self.curr_loc_coords)
                current_clamp_status = loc['clamp_status']
                drop_signal = True if not self.previous_clamp_status & 0x40 and current_clamp_status & 0x40 else False
                pickup_signal = True if self.previous_clamp_status & 0x80 and not current_clamp_status & 0x80 else False
                self.previous_clamp_status = current_clamp_status

                if pickup_signal:
                    self.log.info('\n- PICKUP @ {} at {}'.format(self.curr_loc_id, self.curr_loc_coords))
                    if self.clamp_check_enabled():
                        self.pickup_history.append(self.curr_loc_id)
                        clamp_warning_name = 'clamps_closed_event' if self.curr_loc_id in self.correct_origins else 'clamps_closed_warning'
                        if self.has_active_tasks() and self.curr_loc_id not in self.correct_dests:
                            self.create_alert(clamp_warning_name, self.curr_loc_id)
                        self.log.info('Initializing pickup distance check')
                        self.pickup_check = True
                        curr_pickup_coords = self.curr_loc_coords
                        curr_pickup_time = self.curr_loc_time
                        if self.curr_loc_id in self.correct_origins:
                            active_pickup_event = True
                            self.db_connection.cancel_alerts('clamps_closed_warning')
                            self.finalize_trip(self.curr_loc_id, self.curr_loc_time, False)

                if drop_signal:
                    self.log.info('\n- DROP @ {} at {}'.format(self.curr_loc_id, self.curr_loc_coords))
                    if self.clamp_check_enabled() and not drop_check:
                        self.check_pickup(curr_pickup_coords, curr_pickup_time)
                        self.drop_history.append(self.curr_loc_id)
                        self.log.info('Initializing drop distance check')
                        drop_check = True
                        curr_drop_coords = self.curr_loc_coords
                        curr_drop_time = self.curr_loc_time
#                        >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> 
#                        Appending current NOE destination if cannot place alert/ Damaged_item aleret is active
                        self.correct_dests.append(JobMonitor.__NOE_loc) if self.db_connection.has_cannot_place_alerts() or self.db_connection.has_Damaged_Item_alerts() else self.correct_dests
                        if self.curr_loc_id in self.correct_dests:
                            self.db_connection.cancel_alerts('clamps_closed_warning')

                if drop_check and self.event_distance_check(self.config['drop_check_distance'], curr_drop_coords):
                    drop_check = False
                    sensed_items = self.db_connection.get_drop_data(curr_drop_time, self.curr_loc_time)
#                    >>>>> Adding the cannot place alert and damaged_item alert checkpoint in the check_drop() function
                    self.check_drop(self.drop_history[-1], sensed_items)

                if active_pickup_event and self.event_distance_check(self.config['pickup_check_distance_trigger'], curr_pickup_coords):
                    active_pickup_event = False
                    self.db_connection.cancel_alerts('clamps_closed_event')

            if loc_data:
                loc_data_start_time = self.curr_loc_time

    def clamp_check_enabled(self):
        """
        Returns whether the current location can contain items.

        This method excludes aisles and the charging area from
        pickup and drop checks, so as to avoid false positives
        and spurious alerts while trucks are maneuvering.

        :returns: *True* if the current location can contain items,
                  *False* otherwise.
        :rtype: bool
        """
        return self.curr_loc_type != 'aisle' and self.curr_loc_type != 'charging'

    def update_carry_times(self):
        """
        Updates stow and dock time for the current carry.

        The stow or dock time, if the truck is located in any
        geo-feature of one of these types, is incremented by the
        difference between this location's timestamp and the
        previous timestamp.
        """
        if self.prev_loc_time is None:
            return
        if self.curr_loc_type == 'stow':
            self.carries[-1].add_stow_time(self.prev_loc_time, self.curr_loc_time)
        elif self.curr_loc_type == 'dock' or self.curr_loc_type == 'dockOS':
            self.carries[-1].add_dock_time(self.prev_loc_time, self.curr_loc_time)

    def should_check_item_at_drop(self, item):
        """
        Returns whether items from the specified location
        should be processed or discarded at drop time.

        At drop time, items are always included in the load check
        if they were also detected at the previous pickup, regardless
        of their origin.

        Items at drop time are ignored if:

        - Their origin is not in the correct origins and has
          active 'drop_location' alerts. This policy is useful
          to avoid false positives from neighboring stows in case
          the driver is fixing an alert.
        - Their origin does not belong to the pickup history.

        :param item: The item to check.
        :type item: dict
        """
        if item['id'] in self.latest_pickup_item_ids:
            return True

        item_origin = item['item_origin']
        if item_origin not in self.correct_origins and self.db_connection.loc_has_active_dl_alerts(item_origin):
            return False

        return True if item_origin in self.pickup_history else False

    def check_pickup(self, curr_pickup_coords, curr_pickup_time):
        """
        Updates set of picked up items.

        No alerts are produced by the pickup check, as it only updates
        the *latest_pickup_item_ids* list with the detected items.
        This list will be used by
        :func:`check_drop <job_monitor.JobMonitor.check_drop>` to include
        the picked up items in the check of the drop load, if also detected
        at drop time.

        :param curr_pickup_coords: Coordinates of the pickup event.
        :type curr_pickup_coords: dict
        :param curr_pickup_time: Timestamp of the pickup event.
        :type curr_pickup_time: str
        """
        self.log.info('checking pickup load')
        pickup_data = []

        pickup_trigger_distance = self.config['pickup_check_distance_trigger']
        if self.pickup_check and self.event_distance_check(pickup_trigger_distance, curr_pickup_coords):
            pickup_data = self.db_connection.get_pickup_data(curr_pickup_coords, curr_pickup_time)

        self.pickup_check = False

        for pickup_id in pickup_data:
            self.latest_pickup_item_ids.append(pickup_id)

    def check_alleged_wrong_item(self, item, drop_location, correct_items, returned_items, wrong_items):
        """
        The specified item did not satisfy the requirements of any open task
        while checking the sensed items at drop. It may still have been correctly
        moved in the following case:

        - The item had been previously used by the *Job Monitor* to close a task
          in a situation where multiple valid items were dropped at a correct location.
        - In this case, the driver will have to bring the excess items back to their
          origin or to their correct destination.
        - If the driver chooses to move an item which had been previously used to
          close a task, its ID should be swapped with one of the items left at the
          location where the task was closed.

        This method takes care of handling this without generating 'correction tasks'.

        Example:

        Consider a task list structured like this:

        - T1 requires to move one model ABC123 from location A to B
        - T2 requires to move one model ABC123 from location A to Z

        If the driver moves items 1 and 2 (of model ABC123) from A to B, the following
        may happen:

        - Item 1 is used to close T1 and its current location is moved to B
        - Item 2 generates alert A1 with *loc_id* == B and *correct_loc_id* == Z

        From a workflow point of view, the driver can fix this situation by moving
        either Item 1 or Item 2 to location Z, and should not be forced to move Item 2.

        Let's suppose that he moves Item 1 to Z, leaving Item 2 at B. Then, the
        correct outcome is that T1 is closed by Item 2, and Item 1 closes T2 instead of T1.

        Item 1's location had been updated to B when it was used to close task T1, so
        it will not automatically close T2 too, because the movement detected by
        :func:`check_drop <job_monitor.JobMonitor.check_drop>` is from B to Z instead of
        from A to Z as required by T2. :func:`check_drop <job_monitor.JobMonitor.check_drop>`
        would mark Item 1 as wrong, but delegates its handling to this method.

        This method processes the allegedly wrong Item 1 in the following way:

        - It detects that Item 1 had been already used to close T1
        - It notices that there is an open task, T2, which *could* be closed by Item 1
        - It checks, by looking at the alerts table, if an item of the same model as Item 1
          also coming from its same origin, has been left behind at T1's destination
        - If it is found, then it can be used to close T1 instead of Item 1, leaving Item 1
          'free' to be used to close T2.

        :param item: The allegedly wrong item.
        :type item: dict
        :param drop_location: The location where the allegedly wrong item
                              was dropped.
        :type drop_location: int
        :param correct_items: The list of correct items.
        :type correct_items: list
        :param returned_items: The list of returned items.
        :type returned_items: list
        :param wrong_items: The list of wrong items.
        :type wrong_items: list
        """
        if item['serial_lock'] != 0:
            wrong_items.append(item)
            return

        model_tasks = [t for t in self.tasks if t.model == item['model']]

        task_completed_by_item = None
        for task in model_tasks:
            if task.complete and task.item_id == item['id']:
                task_completed_by_item = task
                break

        alerts = self.db_connection.get_model_alerts(item)

        if task_completed_by_item is None or not alerts:
            wrong_items.append(item)
            return

        correction_task = None
        alert_to_cancel = None

        if task_completed_by_item.origin != drop_location:
            for task in model_tasks:
                if task.dest == drop_location and not task.complete:
                    correction_task = task
                    break

            for alert in alerts:
                if alert['correct_loc_id'] == drop_location:
                    alert_to_cancel = alert
                    break

            if correction_task is None or alert_to_cancel is None:
                wrong_items.append(item)
                return
        else:
            alert_to_cancel = alerts[0]

        task_completed_by_item.item_id = alert_to_cancel['item_id']
        self.db_connection.save_task(task_completed_by_item)
        if correction_task is not None:
            correction_task.item_id = item['id']
            correction_task.complete = True
            self.db_connection.save_task(correction_task)
            correct_items.append(item)
        else:
            returned_items.append(item)

        self.db_connection.cancel_alert(alert_to_cancel['id'])

    def check_drop(self, drop_location, sensed_items):
        """
        When drop of items is sensed compare dropped items to tasks for validation.

        This method first filters the items detected at drop time. Only the ones
        which satisfy at least one of the following constraints are checked,
        the others are discarded:

        - Items must come from an admissible origin for this drop (see
          :func:`should_check_item_at_drop
          <job_monitor.JobMonitor.should_check_item_at_drop>`).
        - Otherwise, items must have been detected in the latest pickup item set.

        Each item of the filtered list is compared against open tasks to check
        if it can be used to close one of them. If a matching open task is found,
        the task is updated as completed and the item is labeled as a **correct_item**.

        If no matching task exists but the drop location equals the item's origin,
        the item is labeled as a **returned_item**, as it is being put back where it was
        picked up (e.g. to fix an alert).

        If no matching task exists and the drop location is *not* the item's origin,
        this item may have been wrongly moved. The call to
        :func:`check_alleged_wrong_item <job_monitor.JobMonitor.check_alleged_wrong_item>`
        checks whether the item can be swapped with an outstanding item to avoid an
        alert. The function can label the allegedly wrong item as a **correct_item**,
        **returned_item** or confirm it as a **wrong_item**.

        Once all items have been labelled, this implementation proceeds in the following
        way:

        - If at least one label category is not empty, the current trip is finalized.
        - If **returned_items** exist, their alerts are cancelled because they were put
          back into their original location.
        - If **wrong_items** exist, their correct location is determined and an alert
          for each of them is created.
        - If **correct_items** exist, their previous alerts are cancelled and the
          current carry is finalized.
        - The set of items accumulated by
          :func:`check_pickup <job_monitor.JobMonitor.check_pickup>` is cleared.
        - The job completion is checked by invoking
          :func:`check_job <job_monitor.JobMonitor.check_job>`.

        :param drop_location: The drop location's ID.
        :type drop_location: int
        :param sensed_items: List of sensed items.
        :type sensed_items: list
        """
        self.log.info('checking drop load')

        correct_items = []
        wrong_items = []
        returned_items = []

        self.log.info('Pickup set: {}'.format(self.latest_pickup_item_ids))
        self.log.info('Sensed items at drop: {}'.format(sensed_items))

        for item in sensed_items:
            item_origin = item['item_origin']
            if not self.should_check_item_at_drop(item):
                continue
            tasks_to_check = [t for t in self.tasks if not t.complete]
            for task in tasks_to_check:
                if item['model'] == task.model and item['serial_lock'] == 0 and item_origin == task.origin and drop_location == task.dest:
                    # set the tasks item id to be that of the correctly validated item
                    self.db_connection.save_item_loc(item, drop_location)
                    self.finalize_task(task, item)
                    self.db_connection.save_task(task)
                    correct_items.append(item)
                    break
                    """
                    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>...
                    In the below else statemtnt, Adding the NOE location as the new drop_location in order to close the cannnot_alert or the damaged_alert task
                    However, this is only testing the model,serial_lock and item_origin to close the task and there should be an upgrade
                    to close the specific item for the cannot place alert or damaged_item_alert
                    """
                else:
                    if item['model'] == task.model and item['serial_lock'] == 0 and item_origin == task.origin and drop_location == JobMonitor.__NOE_loc:
                        self.log.info('Finalising the NOE location drop for model {}'.format(task.model))
                        # set the tasks item id to be that of the correctly validated item
                        self.db_connection.save_item_loc(item, drop_location)
                        self.finalize_task(task, item)
                        self.db_connection.save_task(task)
                        correct_items.append(item)
                        break
            else:
                if item_origin != drop_location:
                    self.check_alleged_wrong_item(item, drop_location, correct_items, returned_items, wrong_items)
                else:
                    returned_items.append(item)

        incomplete_tasks = [t for t in self.tasks if not t.complete]
        checked_tasks = []
        for wrong_item in wrong_items:
            tasks_to_check = [t for t in incomplete_tasks if t.task_id not in checked_tasks]
            for task in tasks_to_check:
                if wrong_item['model'] == task.model and wrong_item['serial_lock'] == 0 and wrong_item['item_origin'] == task.origin:
                    wrong_item['correct_loc_id'] = task.dest
                    checked_tasks.append(task.task_id)
                    break
            else:
                wrong_item['correct_loc_id'] = wrong_item['item_origin']

        if correct_items and drop_location in self.correct_dests:
            self.speed_accumulator = []
            self.task_completion_times.append(self.curr_loc_time)

        if returned_items:
            self.db_connection.cancel_item_alerts(returned_items)

        if wrong_items:
            alert_type = 'drop_items' if drop_location in self.correct_dests else 'drop_location'
            self.log.info('wrong items in drop location {}: {}'.format(drop_location, wrong_items))
            self.create_alert(alert_type, drop_location, wrong_items)

        if (correct_items or wrong_items or returned_items) and drop_location in self.correct_dests:
            self.finalize_trip(drop_location, self.curr_loc_time, True if correct_items else False)

        # only create a new carry if there were correct items in the drop
        if correct_items:
            self.db_connection.cancel_item_alerts(correct_items)
            self.finalize_carry(drop_location, self.curr_loc_time, len(correct_items))
            self.check_remaining_tasks(drop_location)

        self.check_job()
        self.latest_pickup_item_ids = []

    def finalize_trip(self, location, event_time, carry_finished):
        """
        Finalizes the currently open trip and creates a new one
        if the job is not finished.

        The trip can only be closed if the end location differs
        from the start location, unless also the carry has been
        finished.

        :param location: The trip end location.
        :type location: int
        :param event_time: The trip end timestamp
        :type event_time: str
        :param carry_finished: Whether the carry also finished at
                               this time.
        :type carry_finished: bool
        """
        if not self.carries or not self.carries[-1].trips:
            return

        if self.carries[-1].trips[-1].origin == location and not carry_finished:
            return

        self.carries[-1].trips[-1].finished(location, event_time)
        if self.has_active_tasks() and not carry_finished:
            self.carries[-1].append_trip(event_time, location)

    def finalize_carry(self, location, event_time, correct_item_count):
        """
        Finalizes the currently open carry and creates a new one if the
        job is not finished.

        :param location: The carry's end location ID.
        :type location: int
        :param event_time: The carry's end timestamp.
        :type event_time: str
        :param correct_item_count: The carry's unit count.
        :type correct_item_count: int
        """
        if self.carries:
            self.carries[-1].finished(location, correct_item_count, event_time)

        if self.has_active_tasks():
            self.carries.append(Carry(len(self.carries) + 1, event_time, location))

    def finalize_task(self, task, item):
        """
        Finalizes the specified task with the item that fulfilled it.

        :param task: The task to finalize.
        :type task: :class:`Task <models.Task>`
        :param item: The item which satisfied the specified task's
                     requirements.
        :type item: dict
        """
        task.item_id = item['id']
        task.start_time = self.job_start_time if not self.task_completion_times else self.task_completion_times[-1]
        task.finish_time = self.curr_loc_time
        task.avg_speed = self.get_task_avg_speed()
        task.complete = True

    def check_remaining_tasks(self, drop_location):
        """
        Checks if there are open tasks with the specified
        location set as their destination.

        This is invoked by
        :func:`check_drop <job_monitor.JobMonitor.check_drop>`
        when at least one task is completed at the drop location.
        In case the driver has only completed part of the tasks
        which had that location as target, an alert of type
        *remaining_tasks* is generated. This function removes that
        alert when no missing open tasks are found.

        :param drop_location: The location to check.
        :type drop_location: id
        """
        incomplete_tasks = []
        for task in self.tasks:
            if not task.complete and task.dest == drop_location:
                incomplete_tasks.append(task)
        if incomplete_tasks:
            # alert type (5) Missing items at drop location
            self.create_alert('remaining_tasks', drop_location)
            self.log.info('{} incomplete tasks'.format(len(incomplete_tasks)))
        else:
            self.db_connection.cancel_remaining_tasks_alert(drop_location)

    def event_distance_check(self, threshold, clamp_event_coords):
        """
        Checks whether the distance between the current coordinates
        and the specified one is greater than the specified threshold.

        This is invoked to monitor when the truck drives away from the
        pickup or drop coordinates, to trigger the pickup and drop
        checks at the proper time.

        :param threshold: The distance threshold.
        :type threshold: float
        :param clamp_event_coords: The reference coordinates.
        :type clamp_event_coords: dict
        :return: *True* if the distance is greater than the threshold,
                 *False* otherwise.
        :rtype: bool
        """
        distance = get_distance(self.curr_loc_coords, clamp_event_coords)
        if distance > threshold:
            return True
        return False

    def create_alert(self, alert_type, loc_id, wrong_items=None):
        """
        Inserts an alert into the database and logs the event.

        :param alert_type: The alert type.
        :type alert_type: str
        :param loc_id: The location where the alert has been generated.
        :type loc_id: int
        :param wrong_items: The optional list of wrong items associated
                            to the alert being created.
        :type wrong_items: list or None
        """
        self.db_connection.create_alert(loc_id, alert_type, wrong_items, self.curr_loc_time)
        self.log.info('{} alert created at {}'.format(alert_type, loc_id))

    def get_task_avg_speed(self):
        """
        Computes the average speed for the current task.

        :return: The average speed, or *0* if it could not be determined.
        :rtype: number
        """
        if not self.speed_accumulator:
            return 0

        return round(sum(self.speed_accumulator) / len(self.speed_accumulator), 2)

    def set_tasks(self):
        """
        Initializes this *Job Monitor*'s task-related members.

        This invoked by
        :func:`__init__ <job_monitor.JobMonitor.__init__>`.
        """
        tasks = self.db_connection.get_task_data()
        for task in tasks:
            self.correct_origins.append(task['origin'])
            self.correct_dests.append(task['dest'])
            self.tasks.append(
                Task(task['id'],
                     task['model'],
                     task['origin'],
                     task['dest']))
        self.log.info(self.tasks)

    def set_loc_data(self, loc):
        """
        Updates this *Job Monitor*'s location-related members.

        This is done at each iteration of the
        :func:`run <job_monitor.JobMonitor.run>` loop, for
        each coordinate extracted from the database.

        This implementation unwraps the *dict* returned by
        MySQL.

        :param loc: The location data as returned by the
                    database handler.
        :type loc: dict
        """
        self.prev_loc_time = self.curr_loc_time
        self.curr_loc_type = loc['type']
        self.curr_loc_id = loc['geo_feature_id']
        self.curr_loc_time = loc['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')
        self.curr_loc_coords = {'x': loc['x'], 'y': loc['y']}
        self.speed_accumulator.append(loc['speed'])

    def is_job_active(self):
        """
        Triggers a *sys.exit()*, effectively terminating this
        *Job Monitor*, if the job is deactivated in the database.

        This is deactivation method is used by the *Job Manager*
        to stop previous *Job Monitor* instances before starting a
        new one.
        """
        if not self.db_connection.is_job_active():
            self.log.info('\nDEACTIVATED at {}\n'.format(self.now()))
            self.db_connection.close_db()
            sys.exit()

    def has_active_tasks(self):
        """
        Returns whether there are active (incomplete) tasks.

        :returns: *True* if at least one not complete task exists,
                  *False* otherwise.
        :rtype: bool
        """
        for task in self.tasks:
            if not task.complete:
                return True
        return False

    def check_job(self):
        """
        If there are no tasks left to complete then persist
        all data and end the job.

        This implementation returns immediately if the job is
        not complete or if active alerts exist.

        In case the job has been completed carry, trip and job
        data are updated in the database. Moreover, the lists of
        tasks, correct origins and correct destinations maintained
        internally by this *Job Monitor* are cleared, as from this
        moment on no inventory can be moved by this truck without
        generating an alert.

        This *Job Monitor* will keep on monitoring the truck until
        a new job is launched; then it will be terminated by the
        *Job Manager* before starting a new *Job Monitor*.
        """
        if not self.tasks or self.has_active_tasks() or self.db_connection.has_active_alerts():
            return

        self.log.info('\njob completed at: {}\n'.format(self.now()))
        self.__log_all_data()
        self.db_connection.save_carries(self.carries)
        self.db_connection.save_job(self.job_start_time, self.now(), self.carries)
        self.tasks = []
        self.correct_origins = []
        self.correct_dests = []

    def __log_all_data(self):
        """
        Logs all job data when the job is completed.
        """
        self.log.info('\n\n:::::: TASKS ::::::')
        for task in self.tasks:
            self.log.info('\n')
            for key, value in vars(task).items():
                self.log.info('{}: {}'.format(key, value))
        self.log.info('\n\n:::::: CARRIES ::::::')
        for carry in self.carries:
            self.log.info('\n')
            for key, value in vars(carry).items():
                self.log.info('{}: {}'.format(key, value))


if __name__ == '__main__':
    try:
        JOB_ID = int(sys.argv[1])
        TRUCK_ID = int(sys.argv[2])
    except IndexError:
        sys.exit('Missing arguments')
    except ValueError:
        sys.exit('Invalid arguments provided')
    JOB_MONITOR = JobMonitor(JOB_ID, TRUCK_ID)
    try:
        JOB_MONITOR.run()
    except Exception as exception:
        import traceback
        TRACE_BACK = traceback.format_exc()
        JOB_MONITOR.log.info('\nan error in job {} has occured: {}\n\n{}'.format(JOB_ID, exception, TRACE_BACK))
    finally:
        JOB_MONITOR.db_connection.close_db()

"""
This module contains classes which implement the data models representing
tasks, trips and carries.
"""

from datetime import datetime
from helpers import get_distance, get_time_delta


class Trip(object):
    """
    Represents a trip. Trips are finalized when one of the following scenarios
    takes place:

    - The clamps are closed in a correct origin for the ongoing job
    - Items, regardless of their correctness, are dropped at a correct
      destination for the ongoing job

    A trip must start and end in two different locations, unless it is the
    final trip of a carry.

    """

    def __init__(self, carry_num, start_time, start_loc):
        """
        Constructs an open trip.

        :param carry_num: ID of the carry this trip belongs to.
        :type carry_num: int
        :param start_time: This trip's start time.
        :type start_time: str
        :param start_loc: This trip's start location ID.
        :type start_loc: int

        """
        self.carry_num = carry_num
        self.start_time = start_time
        self.finish_time = None
        self.origin = start_loc
        self.dest = None
        self.travel_time = 0
        self.distance = 0
        self.avg_speed = 0
        self.speeds = []
        self.latest_coords = None

    def __repr__(self):
        return '[c{} {} to {}]'.format(self.carry_num, self.origin, self.dest)

    def append_speed(self, speed):
        """
        Appends a new speed value. The average speed will be computed upon
        trip finalization.

        :param speed: The speed in meters per second
        :type speed: float
        """
        self.speeds.append(speed)

    def append_coords(self, coords):
        """
        Updates the driven distance, which is incremented by the distance
        between the specified coordinates and the previous ones.

        :param coords: The latest coordinates
        :type coords: dictionary

        """
        if self.latest_coords:
            self.distance += get_distance(self.latest_coords, coords)

        self.latest_coords = coords

    def finished(self, location, time):
        """
        Finalizes this trip. The travel time is computed as the difference
        between the start and end times, and the accumulated speeds are
        averaged to find out the average trip speed.

        :param location: The trip's end location ID
        :type location: int
        :param time: The trip's end timestamp
        :type time: str
        """
        if not self.speeds:
            self.avg_speed = 0
        else:
            self.avg_speed = round(sum(self.speeds) / len(self.speeds), 2)

        self.finish_time = time
        f_time = datetime.strptime(self.finish_time, '%Y-%m-%d %H:%M:%S.%f')
        s_time = datetime.strptime(self.start_time, '%Y-%m-%d %H:%M:%S.%f')
        diff = f_time - s_time
        self.travel_time = diff.total_seconds()
        self.dest = location


class Carry(object):
    """
    Represents a carry. Carries are finalized when at least one correct item
    is dropped at a correct destination (i.e. when a task is completed).
    Each carry contains statistics which cover the time span between the
    closure of the previous carry (or the moment the job started if at the
    first carry) to the completion of a task, which closes the ongoing carry.
    """

    def __init__(self, carry_num, start_time, start_loc):
        """
        Constructs an open carry.

        :param carry_num: The carry ID, assigned progressively
        :type carry_num: int
        :param start_time: The carry's start time
        :type start_time: str
        :param start_loc: The carry's start location ID
        :type start_loc: int

        """
        self.carry_num = carry_num
        self.start_time = start_time
        self.finish_time = None
        self.unit_count = None
        self.origin = start_loc
        self.dest = None
        self.trips = []
        self.stow_time = 0
        self.dock_time = 0
        self.total_distance = 0
        self.avg_trip_distance = 0
        self.avg_trip_time = 0
        self.append_trip(start_time, start_loc)

    def __repr__(self):
        return '[{} to {}]'.format(self.origin, self.dest)

    def add_stow_time(self, prev_loc_time, curr_loc_time):
        """
        Updates the stow time.

        :param prev_loc_time: Timestamp of the previous location data.
        :type prev_loc_time: str
        :param curr_loc_time: Timestamp of the current location data.
        :type curr_loc_time: str
        """
        self.stow_time += get_time_delta(prev_loc_time, curr_loc_time)

    def add_dock_time(self, prev_loc_time, curr_loc_time):
        """
        Updates the dock time.

        :param prev_loc_time: Timestamp of the previous location data.
        :type prev_loc_time: str
        :param curr_loc_time: Timestamp of the current location data.
        :type curr_loc_time: str

        """
        self.dock_time += get_time_delta(prev_loc_time, curr_loc_time)

    def append_trip(self, start_time, start_loc):
        """
        Constructs a new trip and appends it to this carry.

        :param start_time: The trip start time.
        :type start_time: str
        :param start_loc: The trip start location ID.
        :type start_loc: int

        """
        self.trips.append(Trip(self.carry_num, start_time, start_loc))

    def finished(self, location, item_count, time):
        """
        Finalizes this carry.
        When this is invoked, the carry's total driven distance is computed
        based on the distance driven during each trip this carry consists of.
        The average trip distance and average trip duration are also computed.

        :param location: The current location ID.
        :type location: int
        :param item_count: The count of carried items.
        :type item_count: int
        :param time: The current location timestamp.
        :type time: str
        """
        self.dest = location
        self.unit_count = item_count
        self.finish_time = time

        travel_time_accumulator = 0
        for trip in self.trips:
            self.total_distance += trip.distance
            travel_time_accumulator += trip.travel_time

        trip_count = len(self.trips)
        if trip_count > 0:
            self.avg_trip_distance = self.total_distance / trip_count
            self.avg_trip_time = travel_time_accumulator / trip_count


class Task(object):
    """
    Represents a task.
    """

    def __init__(self, task_id, model, origin, dest):
        """
        Constructs a task.

        :param task_id: The task ID as found in the database.
        :type task_id: int
        :param model: The model code.
        :type model: str
        :param origin: The origin geo-feature ID.
        :type origin: int
        :param dest: The destination geo-feature ID.
        :type dest: int
        """
        self.task_id = task_id
        self.complete = False
        self.model = model
        self.item_id = None
        self.origin = origin
        self.dest = dest
        self.start_time = None
        self.finish_time = None
        self.avg_speed = None

    def __repr__(self):
        return '[Task-{} model: {} from: {} to: {} fin: {}]' \
            .format(self.task_id, self.model, self.origin, self.dest, self.complete)

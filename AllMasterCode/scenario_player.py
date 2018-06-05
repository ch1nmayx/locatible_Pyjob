"""
Plays testing scenarios.
"""

import sys
import json
from datetime import datetime
from job_monitor import JobMonitor
from models import Carry


def get_curr_time():
    return str(datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S.%f'))


class ScenarioPlayer(object):

    def __init__(self, scenario_file_name):
        try:
            with open(scenario_file_name, 'r') as config_file:
                scenario_data = config_file.read()
        except EnvironmentError:
            sys.exit('error opening config file')
        try:
            self.scenario = json.loads(scenario_data)
        except ValueError as json_parse_exception:
            sys.exit('Invalid configuration file format: {}'.format(json_parse_exception))
        self.job_monitor = JobMonitor(self.scenario['job_id'], self.scenario['truck_id'])

    def simulate_pickup(self, event):
        self.job_monitor.log.info('Simulating pickup event: {}'.format(event))
        self.job_monitor.pickup_history.append(event['location'])
        if event['location'] in self.job_monitor.correct_origins:
            self.job_monitor.finalize_trip(event['location'], self.job_monitor.curr_loc_time, False)
        for item_id in event['items']:
            self.job_monitor.latest_pickup_item_ids.append(item_id)

    def simulate_drop(self, event):
        self.job_monitor.log.info('Simulating drop event: {}'.format(event))
        self.job_monitor.drop_history.append(event['location'])
        sensed_items = self.job_monitor.db_connection.get_item_data(event['items'])
        self.job_monitor.check_drop(self.job_monitor.drop_history[-1], sensed_items)

    def run(self):
        self.job_monitor.carries.append(Carry(1, get_curr_time(), self.scenario['initial_location']))
        for event in self.scenario['events']:
            self.job_monitor.curr_loc_time = get_curr_time()
            if event['type'] == 'pickup':
                self.simulate_pickup(event)
            elif event['type'] == 'drop':
                self.simulate_drop(event)
            else:
                self.job_monitor.log.info('Unrecognized event: {}'.format(event))


if __name__ == '__main__':
    SCENARIO_PLAYER = ScenarioPlayer(sys.argv[1])
    try:
        SCENARIO_PLAYER.run()
    except Exception as exception:
        import traceback
        TRACE_BACK = traceback.format_exc()
        SCENARIO_PLAYER.job_monitor.log.info('\nAn error has occurred: {}\n\n{}'.format(exception, TRACE_BACK))
    finally:
        SCENARIO_PLAYER.job_monitor.db_connection.close_db()

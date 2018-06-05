System configuration
====================

All system options are stored in the *config.txt* file placed in the project's
root directory. An example file has the following structure:

::

  pickup_check_distance_trigger: 3
  pickup_check_distance_window: 1
  pickup_post_seconds: 2
  drop_check_distance: 1
  drop_pre_seconds: 2
  rfid_wait_timeout: 5
  job_manager_port: 5000
  database_name: ll_remote
  database_password: logos01mysql
  database_user: root
  database_host: 192.168.1.12
  activate_queries: True

The options contained in the configuration file belong to two main areas:
**Job Monitor configuration** and **Database configuration**.

*Job Monitor* configuration
---------------------------

The *Job Monitor* configuration includes the following options:

============================= =================================================
Name                          Description
============================= =================================================
drop_check_distance           Distance threshold in meters from the drop
                              location that has to be exceeded in order to
                              trigger the check of dropped items.
drop_pre_seconds              Quantity of seconds *before* the drop time that
                              are included in the dropped items check.
pickup_check_distance_trigger Distance threshold in meters from the pickup
                              location that has to be exceeded in order to
                              trigger the check of picked up items.
pickup_check_distance_window  The picked up items query will include items
                              starting from the moment the clamp truck's
                              distance from the pickup location went below
                              this threshold, expressed in meters.
pickup_post_seconds           Quantity of seconds *after* the pickup time that
                              are included in the picked up items check.
rfid_wait_timeout             Timeout in seconds of the blocking wait for RFID
                              data. This is used when extracting clamp load
                              data at pickup or drop time: the RFID board may
                              have processed the data but the transmission
                              could have been delayed due to network issues.
============================= =================================================

Database configuration
----------------------

The database configuration includes the following options:

===================== =========================================================
Name                  Description
===================== =========================================================
activate_queries      If *True*, enables database INSERT and UPDATE
                      operations. Set to *False* for debug or simulation
                      purposes.
database_host         IP address of the server where the DBMS is hosted
database_name         Name of the database schema
database_password     Password to access the DBMS
database_user         Username to access the DBMS
===================== =========================================================

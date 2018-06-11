# loc_Pyjob
Locatible Python job

## For CodeVer0.1

Below are the listed changes in the Database.py and the JobMonitor.py codes:

>#### Database.py :
=============

1)Added a function has_cannot_place_alerts, which checks the alerts table and returns the Returns whether this job has currently active 'Cannot_Place_Alert' alerts.It returns *True* if the monitored job has active active 'Cannot_Place_Alert'.
-- have checked it on the local db and seems to be working fine


2)Added a function has_Damaged_Item_alerts, which checks the alerts table and returns the Returns whether this job has currently active 'has_Damaged_Items' alerts.It returns *True* if the monitored job has active active 'has_Damaged_Item_alerts'.

-- have checked it on the local db and seems to be working fine

>#### job_monitor.py :
=================

0) A Class variable for the NOE location is defined as __NOE_loc = 79 (for the geo_location name '02TK149')

1)Changes in the run() function, where the correct_destinations are appended by NOE location id = 79 in case any of the above two alerts are active.

2)check_drop() function is updated for the current job_id, where task.dest in the NOE location id '79' to finalize_task()

The runs to do are as follows:

Run-1)
1) Generate a "Cannot_Place_Alert" which updates the alerts table for the particular job_id and sets the above alert to be active. To check if the alerts table is getting updated.
2) Once the items has been dropped at the NOE location 79, to check if for that item_id the curr_loc_id is changing in the "items" table.
3) Once the task has been finalied we should see that the job_tasks table for that job_id table should also change with the task details
4) Finally, we should see that the alert in the step-1) should be inactive for that job_id in the alerts table

Run-1)
1) Generate a "Cannot_Place_Alert" which updates the alerts table for the particular job_id and sets the above alert to be active. To check if the alerts table is getting updated.
2) Once the items has been dropped at the NOE location 79, to check if for that item_id the curr_loc_id is changing in the "items" table.
3) Once the task has been finalied we should see that the job_tasks table for that job_id table should also change with the task details
4) Finally, we should see that the alert in the step-1) should be inactive for that job_id in the alerts table

Run-2)
1) Generate a "Damaged_Item" which updates the alerts table for the particular job_id and sets the above alert to be active. To check if the alerts table is getting updated.
2) Once the items has been dropped at the NOE location 79, to check if for that item_id the curr_loc_id is changing in the "items" table.
3) Once the task has been finalied we should see that the job_tasks table for that job_id table should also change with the task details
4) Finally, we should see that the alert in the step-1) should be inactive for that job_id in the alerts table







*Job Monitor* overview
======================

Each *Job Monitor* process monitors a given truck ID while it is carrying out
an assigned **job**. A job is a set of **tasks** that require the clamp truck
driver to move inventory in the warehouse. Each task is characterized by the
following properties:

- A model code
- An origin location ID
- A destination location ID

Therefore, a task corresponds to the transport of a single item of the
specified model from a given origin to the required destination.

Each *Job Monitor* process consists of a run loop that polls location data and
clamp status information from the database to detect when and where the
monitored clamp truck picks up and drops items. Cross-checking this data with
the RFID tags detected by the reader placed between the clamps allows a
*Job Monitor* to notify the front end that a job has been completed when all
tasks have been correctly carried out, or to produce alerts in case of driver
errors.

The job monitor output consists of the following:

- Updating the database when a job has been completed.
- Inserting into the database the analytics data about carries and trips, such
  as average speed, distance driven, etc.
- Inserting alerts, warnings and notifications into the database when events
  relevant to the front end are detected. All events are automatically cleared
  by the *Job Monitor* that created them.

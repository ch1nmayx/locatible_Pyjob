Getting started with the *Job Manager*
======================================

Prerequisites
-------------

The *Job Manager* is a Flask App written in Python 3 which interacts with a
DBMS, so the following is required:

- Python 3
- Flask
- Flask CORS
- MySQL Connector

The *pip3* tool can be used to install dependencies:

::

  pip3 install flask
  pip3 install flask-cors
  pip3 install mysql-connector-python

How to run
----------

The following command can be used to start the *Job Manager* from a terminal
window whose current directory is the root of the project source:

::

  FLASK_APP=job_manager.py flask run

Starting *Job Monitor* processes
--------------------------------

Starting *Job Monitors* with the *Job Manager* is done through the
**start_job** endpoint:

::

  http://localhost:<port>/job_manager/start_job

This endpoint listens for JSON requests, so the Content-Type in the header must
be set to *application/json*. JSON requests sent to the job manager’s endpoint
have the following fields:

================= ========= ===================================================
Field             Required  Description
================= ========= ===================================================
job_id            Yes       ID of the job which must be monitored by the new
                            *Job Monitor*.
================= ========= ===================================================

The JSON request to start a job monitor will therefore look like this:

::

  { "job_id": 1234 }

When the job manager receives such a request, it automatically retrieves the
truck ID from the database and starts a *Job Monitor* for the specified job.

At some point in time, it may be needed to monitor a truck which has no
assigned job: for example, this happens when the operator logs out from the
truck’s tablet. In this case, the front end will insert into the database a job
without any job tasks pointing to it, and start a new job monitor using the
JSON described above.

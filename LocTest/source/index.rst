.. Job Monitor documentation master file, created by
   sphinx-quickstart on Tue Jan 30 09:41:02 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Introduction
============

The Job Monitor software package's purpose is to monitor clamp truck
drivers and their actions in the warehouse.

The main entities which implement the monitoring functionality are the
following:

- The *Job Manager* is the front end of this package. It exposes an HTTP
  endpoint that enables the web app to trigger the monitoring of a
  specific job ID through a POST request.
- A *Job Monitor* is spawned in a separate process by the *Job Manager* upon
  receiving a POST request: each *Job Monitor* follows the actions of a
  specific truck during a specific job.

Input and Output
----------------

This software package interacts with the other components of the Logistics
Location Tracking System in the following ways:

- Spawning of *Job Monitor* processes by the *Job Manager* is triggered by
  the web app with HTTP POST requests.
- Each *Job Monitor* polls the database to extract truck location data and
  clamp status.
- Each *Job Monitor* updates the database to signal that a job has been
  completed, or to create alerts in case a driver error is detected.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   howtorun.rst
   config.rst
   monitor_overview.rst
   alerts.rst
   project_structure.rst

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

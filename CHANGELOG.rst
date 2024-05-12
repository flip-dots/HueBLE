=========
Changelog
=========

All notable changes to this project will be documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

`1.0.2`_ (2024-05-12)
=====================

Added
-----

* Definable delay between connecting and disconnecting in the re-connect method.
* Definable maximum attempts for automatic re-connection.

Changed
-------

* Exceptions from ``connect()`` and ``poll_state()`` are now caught and logged instead of
  causing an exception in the callee.

Fixed
-----

* Resolved issue where module would attempt to infinitely retry to connect to a light 
  that failed pairing. Module now will only attempt automatic re-connect when it has
  connected to the light successfully at least once.
* Fixed EOF error in demo program on Linux based systems

`1.0.1`_ (2024-05-05)
=====================

Added
-----

* Code badges to README and docs

Fixed
-----

* Project logo in README
* Hyperlinks to module functions in docs

`1.0.0`_ (2024-05-05)
=====================

* HueBLE created.


.. _1.0.2: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.2
.. _1.0.1: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.1
.. _1.0.0: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.0
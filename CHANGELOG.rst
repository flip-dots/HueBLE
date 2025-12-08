=========
Changelog
=========

All notable changes to this project will be documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

`2.1.0`_ (2025-12-08)
=====================

Added
-----

* ``HueBleError``
* ``ConnectionError``
* ``InitialConnectionError``
* ``PairingError``
* ``ReadWriteError``
* ``ServicesError``
* ``CallbackError``

Changed
-------

* Errors executing callbacks now raise ``CallbackError`` instead of ``Exception``.
* Errors connecting to a light now raise ``ConnectionError`` instead of ``Exception``.
* Errors pairing to a light now raise ``PairingError`` instead of ``Exception``.
* Errors reading or writing to a light now raise ``ReadWriteError`` instead of ``Exception``.

`2.0.0`_ (2025-12-07)
=====================

Added
-----

* Add note to docs about alternate pairing method

Changed
-------

* Values default to ``None`` if support for them is unknown and the relevant default if they are supported.
* ``pair`` now raises Exceptions instead of returning a boolean.
* ``poll_state`` now only returns if the state changed rather than that and a list of errors.
* Increase delay between pairing and checking the result.
* Exceptions in callbacks are now re-raised with added context.
* ``connect`` now raises Exceptions instead of returning a boolean.

Fixed
-----

* Fix polling of unsupported values in ``poll_state``.
* Fix use of deprecated ``logger.warn``.
* Fix exception when connecting to a light on MacOS.
* Fix printing of services on light in debug mode.

`1.0.8`_ (2025-11-06)
=====================

Added
-----

* Add GitHub Actions workflow to publish releases

`1.0.7`_ (2025-05-11)
=====================

Fixed
-----

* Fix debug printing of available services (GATT characteristics)

`1.0.6`_ (2024-06-30)
=====================

Fixed
-----

* Fixed incorrect type hint for colour_temp property
* Fixed exception on light.authenticated if Linux system does not return the expected data

`1.0.5`_ (2024-05-19)
=====================

Changed
-------

* Registered callbacks are now run when the `connect()` method achieves a connection.

`1.0.4`_ (2024-05-18)
=====================

Changed
-------

* Increment minimum Python version to `3.11`. `asyncio.timeout` requires `> 3.10` not `>= 3.10`.

Fixed
-----

* Resolved issue which could cause module to get stuck in a connection loop after an
  unexpected disconnect in an edge case.

`1.0.3`_ (2024-05-12)
=====================

Changed
-------

* Formatting changes

Fixed
-----

* Resolved issue with automatic re-connect causing an exception due to missing brackets :P 

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


.. _2.1.0: https://github.com/flip-dots/HueBLE/releases/tag/v2.1.0
.. _2.0.0: https://github.com/flip-dots/HueBLE/releases/tag/v2.0.0
.. _1.0.8: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.8
.. _1.0.7: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.7
.. _1.0.6: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.6
.. _1.0.5: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.5
.. _1.0.4: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.4
.. _1.0.3: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.3
.. _1.0.2: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.2
.. _1.0.1: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.1
.. _1.0.0: https://github.com/flip-dots/HueBLE/releases/tag/v1.0.0
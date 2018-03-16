.. _main_page:

farcy: a code review bot for github pull requests
=================================================

.. image:: https://travis-ci.org/appfolio/farcy.svg?branch=master
               :target: https://travis-ci.org/appfolio/farcy
.. image:: https://coveralls.io/repos/appfolio/farcy/badge.svg?branch=master
               :target: https://coveralls.io/r/appfolio/farcy?branch=master

**Definition**:

    a form of glanders chiefly affecting the skin and superficial lymphatic
    vessels of horses and mules.

While horses and mules function with farcy, such animals would *likely* prefer
not to have them, and they are an eyesore to those viewing such
animals. Unreviewed source code is analogous to farcy for equines, where the
resulting execution of the source code will likely work as intended, but may be
an eyesore to those working with the source. Farcy attempts to instruct authors
of pull requests to remove eyesores they've added by commenting on changes
introduced in pull requests.

Installation and execution
--------------------------

Farcy is easiest to install using ``pip``:

.. code-block:: bash

    $ pip install farcy

Farcy is run by specifying a github repository owner (or organization), the
repository name, and an optional log level:

.. code-block:: bash

    $ farcy --level INFO appfolio farcy

Configuration
~~~~~~~~~~~~~

Farcy allows to be configured using configuration files. Existence of a configuration
file is optional and values can be overwritten by commandline arguments. On boot,
Farcy will look for a configuration file at ``~/.config/farcy/farcy.conf``.

The configuration file can contain a ``DEFAULT`` section and a section per repository
with specific settings. The ``DEFAULT`` section can take an optional ``repository`` key.

.. code-block::

    [DEFAULT]
    log_level: INFO
    repository:appfolio/farcy

    [appfolio/farcy]
    debug: true
    exclude_paths: npm_modules, vendor, db
    limit_users: balloob, bboe
    pr_issue_report_limit: 32

    [appfolio/gemsurance]
    exclude_users: bboe
    log_level: WARNING
    pr_issue_report_limit: 10


Configuration files for the various linters can be placed in
``~/.config/farcy/handler_NAME.conf``. Replace ``NAME`` with the name of the handler.


Optional external packages needed for various file types
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Python**: ``farcy`` will take advantage of two tools for python files:
``flake8`` and ``pep257``. These can be installed alongside ``farcy`` via:

.. code-block:: bash

    $ pip install farcy[python]

**Ruby**: In order to provide code review of ruby files, ``rubocop`` is
required. Install via:

.. code-block:: bash

    $ gem install rubocop

**JavaScript**: jsxhint is used to provide code review for JavaScript and JSX files. Install via:

.. code-block:: bash

    $ npm install -g jsxhint


Docker
------
Farcy is available as a Docker image with all the handlers installed and ready to be used.

To get started, create a config folder with a configuration file `farcy.conf` that points at your repository.

.. code-block::

    [DEFAULT]
    repository: appfolio/farcy

After that, run the Docker container in interactive mode to setup your GitHub credentials. This will create the file `github_auth` in your configuration folder. This file can be reused if you plan on creating multiple containers.

.. code-block:: bash

    $ docker run -t -i -v /path/to/local/farcy/config:/config appfolio/farcy

After the initial setup, Farcy is ready to go and you can run the Docker container in daemon mode.

.. code-block:: bash

    $ docker run -d --name="farcy" -v /path/to/local/farcy/config:/config appfolio/farcy

Copyright and license
---------------------

Source released under the Simplified BSD License.

* Copyright (c), 2014, AppFolio, Inc
* Copyright (c), 2014, Bryce Boe
* Copyright (c), 2015, Paulus Schoutsen

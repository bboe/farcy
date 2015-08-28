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

The configuration file can contain a ``DEFAULT`` section and a section with repository
specific settings. The ``DEFAULT`` section can take an optional ``repsitory`` key.

.. code-block::

    [DEFAULT]
    repository:appfolio/farcy
    log_level: INFO
    
    [appfolio/farcy]
    debug: true
    exclude_paths: npm_modules, vendor, db 
    limit_users: balloob, bboe
    pr_issue_report_limit: 32

Configuration files for the various linters can be placed in
``~/.config/farcy/handler_NAME.conf``. Replace ``NAME`` with the name of the handler.


Optional external pacakges needed for various file types
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Python**: ``farcy`` will take advantage of two tools for python files:
``flake8`` and ``pep257``. These can be installed alongside ``farcy`` via:

.. code-block:: bash

    $ pip install farcy[python]

**Ruby**: In order to provide code review of ruby files, ``rubycop`` is
required. Install via:

.. code-block:: bash

    $ gem install rubocop

**JavaScript**: jsxhint is used to provide code review for JavaScript and JSX files. Install via:

.. code-block:: bash

    $ npm install -g jsxhint


Copyright and license
---------------------

Source released under the Simplified BSD License.

* Copyright (c), 2014, AppFolio, Inc
* Copyright (c), 2014, Bryce Boe

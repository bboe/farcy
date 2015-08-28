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


Docker
------
Farcy can be run from a Docker container. Run it in interactive mode from the desktop to setup the GitHub credentials. This has to be done once and can be shared between containers.

.. code-block:: bash

    $ docker run -t -i --name="farcy" -v /path/to/local/farcy/config:/config appfolio/farcy

After the initials are setup, you can run it in the background.

.. code-block:: bash

    $ docker run -d --name="farcy" -v /path/to/local/farcy/config:/config appfolio/farcy

Copyright and license
---------------------

Source released under the Simplified BSD License.

* Copyright (c), 2014, AppFolio, Inc
* Copyright (c), 2014, Bryce Boe

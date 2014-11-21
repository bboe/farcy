# Farcy: A code review bot for github pull requests.

__Definition__:

> a form of glanders chiefly affecting the skin and superficial lymphatic
  vessels of horses and mules.

While horses and mules function with farcy, such animals would [likely] prefer
not to have them, and they are an eyesore to those viewing such
animals. Unreviewed source code is analogous to farcy for equines, where the
resulting execution of the source code will likely work as intended, but may be
an eyesore to those working with the source. Farcy attempts to instruct authors
of pull requests to remove eyesores they've added by commenting on changes
introduced in pull requests.

## Installation and execution

Farcy is easiest to install using _pip_:

    pip install farcy

Farcy is run by specifying a github repository owner (or organization), the
repository name, and an optional log level:

    farcy --level INFO appfolio farcy

### Optional external pacakges needed for various file types

__Python__: _Farcy_ will take advantage of two tools for python files: _flake8_
and _pep257_. These can be installed alongside _farcy_ via:

    pip install farcy[python]

__Ruby__: In order to provide code review of ruby files, `rubycop` is
required. Install via:

    gem install rubocop


## Copyright and license

Source released under the Simplified BSD License.

* Copyright (c), 2014, Appfolio, Inc
* Copyright (c), 2014, Bryce Boe

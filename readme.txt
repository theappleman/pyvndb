PyVNDB is a python module containing methods to access VNDB (the visual novel
database) via it's API method.

PyVNDB is written in Py3k and is tested on 3.2a0.

VNDB can be found on the web at http://vndb.org.
VNDB API documentation can be found at http://vndb.org/d11.


Getting started
===============

>>> from vndb import VNDB
>>> vndb = VNDB()
>>> result = vndb.search("star", flags="basic,detailed")
>>> vndb.results(\**res) # Pretty print


Roadmap
=======

The module is also a partially functional command-line program built around the
module. This allows extensibility towards graphical user interfaces for the
more complex tasks (e.g. modifing search filters).


Config
======

The first time you initialise a VNDB object, the module will prompt you for a
VNDB username and password, and will store it for future reference.

The password is stored in plaintext.


"""
General
=======
  The Debian Archive Kit web api, AKA the **FTP-Master api**, allows
  anyone to query the database of the Debian archive kit for information
  related to the archive. That is, it provides information about the
  archive, its suites and all the packages.

  Development
  -----------

  .. note::

     The API is still new and we are adding new features
     whenever someone asks for them. Or better yet, provides a patch.
     The APIs code lives in the DAK codebase, if you want to provide
     a patch with a new feature, or fix a bug, feel free to fork it on
     Salsa and send us a merge request::

     https://salsa.debian.org/ftp-team/dak/

Usage
=====
  The API responds to simple http queries and (usually) replies with
  JSON formatted data. Some commands may require an extra parameter to
  output JSON (notably the madison one).

  ``https://api.ftp-master.debian.org/`` is the base path for all
  requests.

  Available Methods
  -----------------
  The list of available methods can be seen by browsing the
  automatically generated documentation for the :mod:`dakweb.queries`
  module. There are various submodules dealing with different parts of
  the api. Every *public* function of those modules corresponds to
  one available method. The input parameters and the output format are
  documented with each of those functions.


@contact: "Debian FTPMaster <ftpmaster@debian.org>".
"""

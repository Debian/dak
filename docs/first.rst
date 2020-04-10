Notes
=====

- Please be careful: dak sends out a lot of emails and if not
  configured properly will happily send them to lots of people who
  probably didn't want those emails.

- Don't use the debian dak.conf, cron.* etc. as starting
  points for your own configuration files; they are highly Debian
  specific. Start from scratch and refer to the security.debian.org
  config files (-security) as they're a better example for a private
  archive.

What do all these scripts do?
=============================

Generic and generally useful
----------------------------

- To process queue/:

  * ``dak process-upload`` - processes queue/unchecked
  * ``dak process-new`` - allows ftp administrator to process queue/new and queue/byhand
  * ``dak process-policy`` - processes policy queues (including new and byhand)

- To generate indices files:

  * ``dak dominate`` - removes obsolete packages from suites
  * ``dak generate-packages-sources2`` - generate Packages, Sources
  * ``dak generate-releases`` - generates Release

- To clean things up:

  * ``dak clean-suites`` - to remove obsolete files from the pool
  * ``dak clean-queues`` - to remove obsolete/stray files from the queue
  * ``dak rm`` - to remove package(s) from suite(s)
  * ``dak override`` - to change individual override entries

- Information display:

  * ``dak ls`` - shows information about package(s)
  * ``dak queue-report`` - shows information about package(s) in queue/
  * ``dak override`` - can show you individual override entries
  * ``dak graph`` - creates some pretty graphs of queue sizes over time

Generic and useful, but only for those with existing archives
-------------------------------------------------------------

- ``dak init-archive`` - initializes a projectb database from an existing archive

Generic but not overly useful (in normal use)
---------------------------------------------

- ``dak import-users-from-passwd`` - sync PostgreSQL users with system users
- ``dak cruft-report`` - check for obsolete or duplicated packages
- ``dak init-dirs`` - directory creation in the initial setup of an archive
- ``dak check-archive`` - various sanity checks of the database and archive
- ``dak control-overrides`` - manipulates/lists override entries
- ``dak control-suite`` - removes/adds/lists package(s) from/to/for a suite
- ``dak stats`` - produces various statistics
- ``dak find-null-maintainers`` - checks for users with no packages in the archive

Semi-generic
------------

To generate less-used indices files:

- ``dak make-maintainers`` - generates Maintainers file used by, e.g. debbugs
- ``dak make-overrides`` - generates override.<foo> files

Mostly Debian(.org) specific
----------------------------

- ``dak security-install`` - wrapper for Debian security team
- ``dak import-ldap-fingerprints`` - syncs fingerprint and uid information with a debian.org LDAP DB

Very Incomplete or otherwise not generally useful
-------------------------------------------------

- ``dak init-db`` - currently only initializes a DB from a dak.conf config file
- ``dak check-overrides`` - override cruft checker that doesn't work well with New Incoming

Scripts invoked by other scripts
--------------------------------

- ``dak examine-package`` - invoked by 'dak process-new' to "check" NEW packages

How do I get started?
=====================

Please refer to ``setup/development.rst`` for instructions on how to set up dak.

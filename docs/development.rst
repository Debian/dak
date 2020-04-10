Hacking on DAK
==============

Pre-requisites:

- Debian (stable) host
- A non-root user
- git (to clone this repository)

Initial Setup
-------------

Grab a copy of the repository::

    dev@dakdev:~$ git clone https://salsa.debian.org/ftp-team/dak.git

Install additional dependencies::

    cd dak
    sudo apt build-dep -y .

Generate some test packages::

    make -C ~/dak/tests/fixtures/packages

DAK Subshell
------------

**NOTE:** Make sure the hostname is configured correctly (/etc/hosts is sufficient).

Working with a development version of DAK is best done from a testing subshell.

To start the shell::

    ~/dak/integration-tests/interactive-shell
    # Do not use ~/ within this shell

This will create a temporary directory and database to work from.

Once loaded, we need to load some commands::

    cd ~/dak
    . integration-tests/common
    . integration-tests/dinstall

The database can now be poked at using psql::

    psql -c 'select * from suite;'

To populate the database, such that it mimics the Debian archive::

    setup_debian_like_archive


In order to import any test packages, the test key must also be imported::

    import-fixture-signing-key

Useful reference: ``integration-tests/tests/0001-basic``

Workflow
--------

When a package is uploaded, it's dropped into a shared directory. A cron job
will periodically process this data with the ``upload_changes`` command. For
development and testing, the previously built packages can be used::

    upload_changes tests/fixtures/packages/*.changes

This will create symlinks in the temporary upload location pointing at the
packages that were previously generated.

With packages uploaded (symlinked, copied, etc.), they can now be processed::

    process_uploads

If DAK determines there is a problem with the package, then it will be
automatically REJECTed with an email sent to the maintainer. If an ACCEPTed
package has binaries that are not currently in the archive, DAK will move the
package into the NEW queue for manual review.

To manually process these NEW uploaded packages::

    dak process-new

Tests
-----

The full test suite can be run using ``integration-tests/run-tests``. This
should not be done from within an existing subshell; one will be created.

New tests should be written within subshells, as a "unit" separator and should
include a comment.

Common Problems
---------------

Hostname::

    dev@dakdev:~$ ~/dak/integration-tests/interactive-shell
    [...]
    Ver Cluster Port Status Owner Data directory                            Log file
    11  regress 5433 online dev   /tmp/pg_virtualenv.hIxN2u/data/11/[...]-regress.log

    hostname: Name or service not known
    hostname: Name or service not known
    psql: FATAL:  database "projectb" does not exist
    hostname: Name or service not known
    Creating components

Verify the system hostname is present in ``/etc/hosts``.

No project::

    psql: FATAL:  database "projectb" does not exist

Exit the subshell, refer to ``Hostname``, open a new subshell.

Packages not processed::

    dev@dakdev:/home/dev/dak$ upload_changes tests/fixtures/packages/*.changes
    [...]
    dev@dakdev:/home/dev/dak$ process_uploads
    dev@dakdev:/home/dev/dak$

Make sure the appropriate signing key was imported.

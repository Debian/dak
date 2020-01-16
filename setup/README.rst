DAK Setup
=========

This document describes deployment for use in production. For information
about development, see ``docs/development.rst``.

Initialising a dak database schema
----------------------------------

The following packages are needed for the database::

    postgresql-9.6 postgresql-client-9.6 postgresql-9.6-debversion

and the following packages for dak itself::

    python-psycopg2 python-sqlalchemy python-apt gnupg dpkg-dev lintian
    binutils-multiarch python-yaml less python-ldap python-pyrss2gen python-rrdtool
    symlinks python-debian python-debianbts

(the schema assumes at least postgresql 9.1; ftpmaster in Debian currently uses
the postgresql 9.6 version from Debian 9)

The following roles are assumed to exist:

* dak: database superuser: needs to be an actual user
* ftpmaster: role which should be given to archive administrators
* ftpteam: people who can do NEW processing, overrides, removals, etc
* ftptrainee: people who can add notes to packages in NEW

For the purposes of this document, we'll be working in /srv/dak

Set up the dak user::

    sudo addgroup ftpmaster
    sudo adduser dak --disabled-login --ingroup ftpmaster --shell /bin/bash

Set up the dak directory::

    sudo mkdir /etc/dak
    sudo mkdir /srv/dak

Create a symlink to /srv/dak/etc/dak.conf in /etc/dak
(The actual file will be created by the setup script)::

    sudo ln -s /srv/dak/etc/dak.conf /etc/dak/dak.conf

This script does the rest of the work.  It uses the generic variables set in
init_vars, which can be customized if needed::

    setup/dak-setup.sh

The above script symlinks the dak.py script to /srv/dak/bin/dak, you should also
update your PATH variable to be able to execute dak::

    export PATH="/srv/dak/bin:${PATH}"

**WARNING:** Please check the templates in /srv/dak/templates over and customise
as necessary

Set up a private signing key: don't set a passphrase as dak will not
pass one through to gpg.  Guard this key carefully!
The key only needs to be able to sign, it doesn't need to be able
to encrypt.
::
    # gpg --homedir /srv/dak/keyrings/s3kr1t/dot-gnupg --gen-key
Remember the signing key id for when creating the suite below.
Here we'll pretend it is DDDDDDDD for convenience

Import some developer keys.
Either import from keyservers (here AAAAAAAA)::

    # gpg --no-default-keyring --keyring /srv/dak/keyrings/upload-keyring.gpg --recv-key AAAAAAAA

or import from files::

    # gpg --no-default-keyring --keyring /srv/dak/keyrings/upload-keyring.gpg --import /path/to/keyfile

Import the developer keys into the database
The -U '%s' tells dak to add UIDs automatically::

    # dak import-keyring -U '%s' /srv/dak/keyrings/upload-keyring.gpg

Add some architectures you care about::

    # dak admin architecture add i386 "Intel x86 port"
    # dak admin architecture add amd64 "AMD64 port"

Add a suite (origin=, label= and codename= are optional)::

    signingkey= will ensure that Release files are signed
    # dak admin suite add-all-arches unstable x.y.z origin=MyDistro label=Master codename=sid signingkey=DDDDDDDD

Add the components to the suite::

    # dak admin s-c add unstable main contrib non-free

Re-run dak init-dirs to add new suite directories to /srv/dak::

    # dak init-dirs

Example package flow
--------------------

For this example, we've grabbed and built the hello source package
for AMD64 and copied it into /srv/dak/queue/unchecked.

We start by performing initial package checks which will
result in the package being moved to NEW::

    # dak process-upload -d /srv/dak/queue/unchecked

    -----------------------------------------------------------------------
    hello_2.6-1_amd64.changes

    hello (2.6-1) unstable; urgency=low
     .
       * New upstream release.
       * Drop unused INSTALL_PROGRAM stuff.
       * Switch to 3.0 (quilt) source format.
       * Standards-Version: 3.9.1 (no special changes for this).

    source:hello
    binary:hello

    binary:hello is NEW.
    source:hello is NEW.

    [N]ew, Skip, Quit ? N
    ACCEPT-TO-NEW
    Installed 1 package set, 646 KB.
    -----------------------------------------------------------------------

We can now look at the NEW queue-report::

    # dak queue-report

    -----------------------------------------------------------------------
    NEW
    ---

    hello | 2.6-1 | source amd64 | 42 seconds old

    1 new source package / 1 new package in total / 0 new package to be processed.
    -----------------------------------------------------------------------

And we can then process the NEW queue::

    # dak process-new

    -----------------------------------------------------------------------
    hello_2.6-1_amd64.changes
    -------------------------

       Target:     unstable
       Changed-By: Santiago Vila <sanvila@debian.org>

    NEW

    hello                optional             devel
    dsc:hello            extra                misc
    Add overrides, Edit overrides, Check, Manual reject, Note edit, Prod, [S]kip, Quit ?A

PENDING ACCEPT
++++++++++++++

At this stage, the package has been marked as ACCEPTed from NEW.
We now need to process the NEW policy queue::

    # dak process-policy new

    -----------------------------------------------------------------------
    Processing changes file: hello_2.6-1_amd64.changes
      ACCEPT
    -----------------------------------------------------------------------

We can now see that dak knows about the package::

    # dak ls -S hello

    -----------------------------------------------------------------------
         hello |      2.6-1 |      unstable | source, amd64
    -----------------------------------------------------------------------

    # dak control-suite -l unstable

    -----------------------------------------------------------------------
    hello 2.6-1 amd64
    hello 2.6-1 source
    -----------------------------------------------------------------------

Next, we can generate the packages and sources files::

    # dak generate-packages-sources2
    (zcat /srv/dak/ftp/dists/unstable/main/binary-amd64/Packages.gz for instance)

And finally, we can generate the signed Release files::

    # dak generate-release

    -----------------------------------------------------------------------
    Processing new
    Processing byhand
    Processing unstable
    -----------------------------------------------------------------------

(Look at ``/srv/dak/ftp/dists/unstable/Release``, ``Release.gpg``, and
``InRelease``)


Next steps
++++++++++

The debian archive automates most of these steps in jobs called
cron.unchecked, cron.hourly and cron.dinstall.

TODO: Write example (simplified) versions of these cronjobs which will
do for most installs.

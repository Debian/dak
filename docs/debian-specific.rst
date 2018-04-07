DEBIAN-SPECIFIC NOTES
************************************************************************

Git, Salsa Project, Workflow
------------------------------------------------------------------------

General
========================================================================
Our git repositories are hosted by the Salsa_ Service and available in
the FTP-Team_ group. The team has all FTPMasters_ set as owner, all
other team members are developers. The team and most of our repositories
are visible to the public, one exception is an internal repository for
notes used within the team only.


dak.git_
========================================================================
This project contains the main code running the Debian archive,
processing uploads, managing the various suites and releases.

Contributing and workflow
........................................................................
Development is done in the **master** branch, be it direct commits
from FTPMasters_ or via merges from other people (anyone is welcome to
contribute!).

If you want to contribute, please fork the code using the functions
offered by Salsa_ and work in a branch ideally named after the
feature/bugfix/whatever your attention is on. Try creating a
meaningful history - it may be a single commit is all that is needed,
it may be you need a dozen. No worry, git and its rebase function can
help you to arrive at that easily.

Please write meaningful commit messages. "Change", "Bugfix" is not
one. It may be obvious to you now, but how about in a year? The git
log is our changelog, *what* is changed is visible by the diff, so
please describe *why* it changed.

Whenever you arrive at something you want to merge into ``master`` (and
consequently later into ``deploy`` to actually have it live), create a
merge request out of it. Use the Salsa_ web interface, describe what
it is and off it goes. You may want to allow removal of the source
branch at merge time, then your own forked project gets cleaned up
when the |MR| is accepted. A more detailed write up on how to navigate
the web UI of Salsa_ for this is available at the `gitlab MR
documentation`_ page.

Next someone will review your |MR| - this can be anyone and is not
limited to the FTPTeam_ or even FTPMasters_. Discussions may be opened
for (parts) of your changes, please be ready to engage in them, and -
if warranted, adjust your merge request.

When all discussions are resolved and everyone is happy with the |MR|,
one of the FTPMasters_ will merge it into the ``master`` branch.
From there, an action from one of the FTPMasters_ will move it into
``deploy``, which then gets installed on the Debian machines running
the archive.

The famous ``deploy`` branch
########################################################################
This branch is the code actually in use on the Debian machines, and it
gets deployed (hence the name) on them automatically.

To not make that a complete nightmare, the commits need to be signed
with a gpg key from an active FTPMaster_. As such it consists of
manual merges from the ``master`` branch, followed by a push.

The cronjob for deploying the code (will) run(s) every 15 minutes.

Todo/Fixme: We want to provide a script so that fetching the latest
changes in master as well as preparing the merge commit into
``deploy`` is one single action.

security archive
------------------------------------------------------------------------

NEW processing
========================================================================
- ``cronoff``
- ``CHANGES=FILENAME.changes``
- ``dak process-new``, ACCEPT
- ``cd /srv/security-master.debian.org/queue/new/COMMENTS``
- Change first line to **NOTOK**, add comment "Moving back to unchecked."
- Rename ACCEPT.* to REJECT.*
- ``dak process-policy new; dak clean-suites``
- ``cd /srv/security-master.debian.org/queue/reject``
- ``dak admin forget-signature ${CHANGES}``
- ``dcmd mv -n ${CHANGES} ../unchecked``
- ``/srv/security-master.debian.org/dak/config/debian-security/cron.unchecked``
- ``cronon``

Built-Using
========================================================================
Source packages referred to via Built-Using need to be included in the
security archive:

- Obtain & verify .dsc
- ``dak import built-using updates/<component> <.dsc...>``

If the .dsc is signed by an old key no longer in the keyring, use
``--ignore-signature``. Make **extra sure** the .dsc is *correct*.



.. Links and Stuff
.. _Salsa: http://salsa.debian.org/
.. _FTP-Team: https://salsa.debian.org/ftp-team/
.. _FTPMasters: https://www.debian.org/intro/organization#ftpmasters
.. _FTPTeam: https://www.debian.org/intro/organization#ftpmaster
.. _dak.git: https://salsa.debian.org/ftp-team/dak
.. _gitlabsmrdocs: https://docs.gitlab.com/ce/gitlab-basics/add-merge-request.html
.. _gitlab MR documentation: https://docs.gitlab.com/ce/gitlab-basics/add-merge-request.html
.. |MR| replace:: Merge request


DEBIAN-SPECIFIC NOTES
=====================

Git, Salsa Project, Workflow

General
-------
Our git repositories are hosted by the Salsa_ Service and available in
the FTP-Team_ group. The team has all FTPMasters_ set as owner, all
other team members are developers. The team and most of our repositories
are visible to the public, one exception is an internal repository for
notes used within the team only.


dak.git_
--------

This project contains the main code running the Debian archive,
processing uploads, managing the various suites and releases.

Contributing and workflow
~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This branch is the code actually in use on the Debian machines, and it
gets deployed (hence the name) on them automatically.

To not make that a complete nightmare, the commits need to be signed
with a gpg key from an active FTPMaster_. As such it consists of
manual merges from the ``master`` branch, followed by a push.

The cronjob for deploying the code run(s) every 5 minutes.

Todo/Fixme: We want to provide a script so that fetching the latest
changes in master as well as preparing the merge commit into
``deploy`` is one single action.

Deployment details
-------------------
As of today (2020-04-13) the code gets deployed on the following
machines: coccia fasolo respighi seger suchon usper

Also, to seperate code and actual runtime, the code is deployed (and
owned by) the seperate user dak-code

General
~~~~~~~

Rotating Secure Boot Keys
-------------------------

Four keys are used: dak signs a JSON file used by the signing service
(one key for main archive and security archive), the code-signing
service signs files trusted by Debian's Secure Boot CA and uploads
using a key trusted by dak.

To rotate keys used by dak:

- Generate new key::

    export GNUPGHOME=${base}/s3kr1t/dot-gnupg
    gpg --list-secret-keys
    gpg --homedir --full-generate-key
    gpg --keyring /srv/keyring.debian.org/keyrings/debian-keyring.gpg \
      --local-user ${OLD_FINGERPRINT} --edit-key ${NEW_FINGERPRINT}
    gpg -a --export ${NEW_FINGERPRINT}

  When editing key, run `sign` command and `addrevoker` to add current
  FTP masters as designated revokers.

- Tell dak to use new key.  Edit dak.conf, update fingerprint used in
  `ExportSigningKeys`.

- Tell code-signing to use new key (in `code-signing` project)::

    gpg --no-default-keyring --keyring etc/external-signature-requests.kbx \
      --import

To rotate Secure Boot key (in `code-signing` project):

- Get new key installed in YubiKey and `etc/debian-prod-cert.pem`

- Update `trusted_keys` in `etc/debian-prod.yaml` using::

    openssl x509 -in etc/debian-prod-cert.pem -noout -text
    openssl x509 -in etc/debian-prod-cert.pem -outform der | openssl dgst -sha256

- Update certificate comman name in `etc/debian-prod.yaml`; there are
  two occurances in the `efi` group: `token` and part of `pkcs11_uri`.

To rotate upload key for code-signing service:

- Generate new key (as above for dak keys), except::

    export GNUPGHOME=$HOME/secret/gnupg

- Update `maintainer.key_id` in `etc/debian-prod.yaml` (in `code-signing`
  project).

- Tell dak about new key::

    gpg --no-default-keyring \
      --keyring config/debian-common/keyrings/automatic-source-uploads.kbx \
      --import

  and update fingerprint `AllowSourceOnlyNewKeys` setting in
  `config/debian/external-signatures.conf`

- Import key on `ftp-master` and `security-master`::

    dak import-keyring -U "%s" \
      ${base}/config/debian-common/keyrings/automatic-source-uploads.kbx

- Update ACL on `ftp-master` and `security-master`::

    dak acl export-per-source automatic-source-uploads
    dak acl allow automatic-source-uploads ${NEW_FINGERPRINT} ${SOURCES}
    dak acl deny automatic-source-uploads ${OLD_FINGERPRINT} ${SOURCES}

security archive
~~~~~~~~~~~~~~~~

Switch suite to Long Term Support (LTS)
---------------------------------------

::
    cronoff

::
    \set codename 'stretch'

    begin;
    update suite set
      policy_queue_id = null,
      announce = array['debian-lts-changes@lists.debian.org', 'dispatch@tracker.debian.org']
    where codename = :'codename';
    commit;

::
    suite=oldstable
    codename=stretch

    mkdir ~/${codename}-lts
    cd ~/${codename}-lts
    dak control-suite -l ${suite} > ${codename}.list
    awk '$3 !~ "^source|all|amd64|arm64|armel|armhf|i386$"' < ${codename}.list > ${codename}-remove-for-lts.list
    dak control-suite --remove ${suite} < ${codename}-remove-for-lts.list
    dak control-suite --remove buildd-${suite} < ${codename}-remove-for-lts.list
    for arch in mips mips64el mipsel ppc64el s390x; do
      dak admin suite-architecture rm ${suite} ${arch}
      dak admin suite-architecture rm buildd-${suite} ${arch}
    done
    cd ${ftpdir}/dists/${suite}/updates
    for arch in mips mips64el mipsel ppc64el s390x; do
      rm -r \
        main/binary-${arch} main/debian-installer/binary-${arch} \
        main/Contents-${arch}.gz main/Contents-udeb-${arch}.gz \
        contrib/binary-${arch} contrib/debian-installer/binary-${arch} \
        contrib/Contents-${arch}.gz contrib/Contents-udeb-${arch}.gz \
        non-free/binary-${arch} non-free/debian-installer/binary-${arch} \
        non-free/Contents-${arch}.gz non-free/Contents-udeb-${arch}.gz
    done
    cd ${base}/build-queues/dists/buildd-${suite}/updates
    rm -r main contrib non-free
    dak generate-packages-sources2 -s ${suite},buildd-${suite}
    dak generate-releases -s ${suite} buildd-${suite}

::
    cronon


Built-Using
-----------

Source packages referred to via Built-Using need to be included in the
security archive:

- Obtain & verify .dsc
- ``dak import built-using updates/<component> <.dsc...>``

If the .dsc is signed by an old key no longer in the keyring, use
``--ignore-signature``. Make **extra sure** the .dsc is *correct*.



.. _Salsa: http://salsa.debian.org/
.. _FTP-Team: https://salsa.debian.org/ftp-team/
.. _FTPMasters: https://www.debian.org/intro/organization#ftpmasters
.. _FTPTeam: https://www.debian.org/intro/organization#ftpmaster
.. _dak.git: https://salsa.debian.org/ftp-team/dak
.. _gitlabsmrdocs: https://docs.gitlab.com/ce/gitlab-basics/add-merge-request.html
.. _gitlab MR documentation: https://docs.gitlab.com/ce/gitlab-basics/add-merge-request.html
.. |MR| replace:: Merge request

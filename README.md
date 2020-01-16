# dak - Debian Archive Kit

dak is the collection of programs used to maintain the Debian
project's archives. It is highly optimized for the Debian project,
though can be used by others too.

## More reading
There are some manual pages and READMEs in the [docs](docs) sub-directory.  The
[TODO](docs/TODO) file is an incomplete list of things needing to be done.

There's a mailing list for discussion, development of and help with
dak.  See:

  https://lists.debian.org/debian-dak/

for archives and details on how to subscribe.

# Contributing
We love to get patches for dak. Enhancements, bugfixes,
make-code-nicer/easier, anything.

## Merge requests
With dak being available at the [Salsa Service](https://salsa.debian.org), we 
now prefer receiving merge requests there. They allow simple reviews
using the webinterface and also allow discussing (parts of) the code
within the Salsa UI. They also allow much easier tracking the state of
different requests than a mail on a list ever allows.

To create merge requests that, simply go to [the Salsa project
page](https://salsa.debian.org/ftp-team/dak), select **Fork** followed
by the namespace you want to put it in (usually your private one).
Then simply clone this fork and work it in, preferably in a branch
named after whatever-you-are-doing.

When you are happy with what you coded, use the UI on Salsa to create
a merge request from your feature branch, either using the web
interface or by using e-mail, see the [Gitlab MR
documentation](https://docs.gitlab.com/ce/user/project/merge_requests/)
for details on this process.


### Alternative to using Salsa
While we do prefer merge requests as described above, we also accept
patches send by mail to our mailing list, see above for details on
the list.

# Set Up DAK
You can find more info about setting dak up inside the [setup](setup)
Folder and its [README](setup/README).

# License

dak is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation; either version 2 of the License, a copy of which
is provided under the name COPYING, or (at your option) any later
version.

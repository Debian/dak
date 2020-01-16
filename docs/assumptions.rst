Assumptions
-----------

- Usernames do not contain ",". [dak import-users-from-passwd]
- Package names and versions do not contain "_" [dak cruft-report]
- Suites are case-independent in conf files, but forced lower case in use. [dak make-suite-file-list]
- Components are case-sensitive. [dak make-suite-file-list]
- There's always source of some sort

- If you have a large archive, you have a lot of memory and don't mind
  it being used. [dak make-suite-file-list[, dak import-archive]]

[Very incomplete...]

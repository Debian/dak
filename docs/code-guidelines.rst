Code Guidelines
===============

Patches to DAK are always welcome. However, to avoid the disappointment of
rejection, a few guidelines and expectations need to be established.

For anything that is not a trivial fix, git trees are strongly preferred over
simple patch files. These are much easier to import, review, and so on.

Please keep different features in their own branch and keep the repository in
an accessible location until merged.

Code related:

- Use readable and self-speaking variable names.

- Its 4 spaces per indentation. No tab.

- You want to make sure to not add useless whitespaces. If your editor
  doesn't hilight them, Git can help you with that, just add the following
  in your ~/.gitconfig, and a git diff should hilight them.
  Even better, if you enable the hook pre-commit in your copy of the dak
  code (chmod +x most probably), git will refuse to commit such things.

~/.gitconfig,::

  [color "diff"]
     new = green
     old = red
     frag = yellow
     meta = cyan
     commit = normal

- Describe *every* function you write using a docstring. No matter how small.

- Also describe every file.

- And every test unit.

- Don't forget the Copyright/License header in a file. We expect GPLv2 :)

- Don't write long functions. If it goes above a sane limit (like 50
  lines) - split it up.

- Look at / read http://www.python.org/dev/peps/pep-0008/


VCS related:

- History rewriting is considered bad.

- Always have a "Signed-off-by" line in your commit. `git commit -s`
  automatically does it for you. Alternatively you can enable the hook
  "prepare-commit-msg, that should also do it for you.

- Write good, meaningful, commit messages. We do not have a Changelog
  file anymore, the git commit is *the* place to tell others what you
  did.
  Also, try to use the standard format used in the Git world:

    First comes a summary line, of around 72 caracters at most.

    Then, a blank line, and as many lines and paragraphs as needed
    to describe the change in detail. Beware, though, of including
    in the commit message explanations that would be better to have
    as comments in the code itself!

    Signed-off-by: Your Name <and@address.com>

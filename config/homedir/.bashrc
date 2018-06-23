# bashrc for dak user

# If not running interactively, don't do anything
[ -z "$PS1" ] && return


# append to the history file, don't overwrite it
shopt -s histappend
export HISTCONTROL=ignoreboth

# check the window size after each command and, if necessary,
# update the values of LINES and COLUMNS.
shopt -s checkwinsize

# make less more friendly for non-text input files, see lesspipe(1)
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

## A little nice prompt.
PS1='`_ret=$?; if test $_ret -ne 0; then echo "\[\033[01;31m\]$_ret "; set ?=$_ret; unset _ret; fi`\[\033[01;33m\][`git branch 2>/dev/null|cut -f2 -d\* -s` ] \[\033[01;32m\]\u@\[\033[00;36m\]\h\[\033[01m\]:\[\033[00;37m\]\w\[\033[00m\]\$ '

# If this is an xterm set the title to user@host:dir
case "$TERM" in
xterm*|rxvt*)
    PS1="\[\e]0;\u@\h: \w\a\]$PS1"
    ;;
*)
    ;;
esac

case "$HOSTNAME" in
    franck|coccia|fasolo)
        export SCRIPTVARS=/srv/ftp-master.debian.org/dak/config/debian/vars
        ;;
    seger)
        export SCRIPTVARS=/srv/security-master.debian.org/dak/config/debian-security/vars
        ;;
    *)
        echo "Unconfigured dak host, not importing the usual vars"
        ;;
esac

if [[ -n ${SCRIPTVARS} ]]; then
    . $SCRIPTVARS
fi

function evim() {
    export EDITOR=$(which vim)
}

export PAGER=less
export LESS="-X"
export EDITOR=$(which emacs)
export HISTFILESIZE=6000
export CDPATH=".:~:${base}:${public}:${queuedir}"
export PATH="~/bin/:${PATH}"

alias base='cd ${base}'
alias config='cd ${configdir}'
alias ls='ls --color=auto'
alias sshx='ssh -O exit'
alias killsync='ssh -O exit upload-master'

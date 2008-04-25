# -*- make -*-
BASE=..
SUBDIR=cmdline

# Bring in the default rules
include ../buildlib/defaults.mak

# Program to test the File Filter
PROGRAM=dsync-flist
SLIBS = -ldsync
SOURCE = dsync-flist.cc path-utils.cc
include $(PROGRAM_H)

# Program to test the File Filter
PROGRAM=dsync-cdimage
SLIBS = -ldsync
SOURCE = dsync-cdimage.cc
include $(PROGRAM_H)

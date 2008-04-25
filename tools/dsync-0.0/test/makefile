# -*- make -*-
BASE=..
SUBDIR=test

# Bring in the default rules
include ../buildlib/defaults.mak

# Program to test the File Filter
PROGRAM=fftest
SLIBS = -ldsync
SOURCE = fftest.cc
include $(PROGRAM_H)

# Program to test the File Filter
PROGRAM=pathtest
SLIBS = -ldsync
SOURCE = pathtest.cc
include $(PROGRAM_H)

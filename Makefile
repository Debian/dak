#!/usr/bin/make -f

CXXFLAGS	= -I/usr/include/postgresql/ -fPIC -Wall
CFLAGS		= -fPIC -Wall
LDFLAGS		= -fPIC
LIBS		= -lapt-pkg

LD		= ld
CC		= gcc
C++		= g++
CPP		= cpp

SUBDIRS		= docs

all: sql-aptvc.so $(patsubst %,%.make,$(SUBDIRS))

%.make:
	$(MAKE) -C $* $(MAKECMDGOALS)

sql-aptvc.o: sql-aptvc.cpp
sql-aptvc.so: sql-aptvc.o
	$(LD) $(LDFLAGS) $(LIBS) -shared -o $@ $<
clean: $(patsubst %,%.make,$(SUBDIRS))
	rm -f sql-aptvc.so sql-aptvc.o


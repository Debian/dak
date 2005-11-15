#!/usr/bin/make -f

CXXFLAGS	= -I/usr/include/postgresql/ -I/usr/include/postgresql/server/ -fPIC -Wall
CFLAGS		= -fPIC -Wall
LDFLAGS		= -fPIC
LIBS		= -lapt-pkg

C++		= g++

all: sql-aptvc.so

sql-aptvc.o: sql-aptvc.cpp
sql-aptvc.so: sql-aptvc.o
	$(C++) $(LDFLAGS) $(LIBS) -shared -o $@ $<
clean:
	rm -f sql-aptvc.so sql-aptvc.o


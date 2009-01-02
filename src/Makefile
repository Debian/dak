#!/usr/bin/make -f

CXXFLAGS	= -I/usr/include/postgresql/ -I`pg_config --includedir-server` -fPIC -Wall
CFLAGS		= -fFIC -Wall `pg_config --cflags`
LDFLAGS		= `pg_config --ldflags`
LIBS		= -lapt-pkg `pg_config --libs`

C++		= g++

all: sql-aptvc.so

sql-aptvc.o: sql-aptvc.cpp
sql-aptvc.so: sql-aptvc.o
	$(CC) $(LDFLAGS) $(LIBS) -shared -o $@ $<
clean:
	rm -f sql-aptvc.so sql-aptvc.o


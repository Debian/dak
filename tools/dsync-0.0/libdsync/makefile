# -*- make -*-
BASE=..
SUBDIR=libdsync

# Header location
SUBDIRS = contrib
HEADER_TARGETDIRS = dsync

# Bring in the default rules
include ../buildlib/defaults.mak

# The library name
LIBRARY=dsync
MAJOR=0.0
MINOR=0
SLIBS=$(PTHREADLIB)

# Source code for the contributed non-core things
SOURCE = contrib/error.cc contrib/fileutl.cc contrib/strutl.cc \
         contrib/configuration.cc contrib/cmndline.cc \
	 contrib/md5.cc contrib/md4.cc contrib/mmap.cc contrib/bitmap.cc \
	 contrib/slidingwindow.cc

# Source code for the main library
SOURCE+= filefilter.cc genfilelist.cc filelist.cc filelistdb.cc compare.cc \
         rsync-algo.cc

# Public header files
HEADERS = error.h configuration.h cmndline.h md5.h md4.h fileutl.h mmap.h \
          filefilter.h genfilelist.h filelist.h filelistdb.h compare.h \
          strutl.h bitmap.h slidingwindow.h rsync-algo.h

HEADERS := $(addprefix dsync/,$(HEADERS))

# Private header files
HEADERS+= system.h 

include $(LIBRARY_H)

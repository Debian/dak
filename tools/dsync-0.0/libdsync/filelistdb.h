// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: filelistdb.h,v 1.2 1999/01/10 07:34:05 jgg Exp $
/* ######################################################################
   
   File List DB
   
   This scans a file list and generates a searchable list of all 
   directories in the list. It can then do a lookup of a given file,
   directory pair.
   
   The memory mapped IO class is recommended for use with the DB class 
   for speed.
   
   ##################################################################### */
									/*}}}*/
#ifndef DSYNC_FILELISTDB
#define DSYNC_FILELISTDB

#ifdef __GNUG__
#pragma interface "dsync/filelistdb.h"
#endif 

#include <dsync/filelist.h>
#include <dsync/mmap.h>
#include <map>

class dsFileListDB
{
   struct Location
   {
      unsigned long Offset;
      string LastSymlink;
   };
   
   dsFList::IO *IO;
   map<string,Location> Map;
   string LastDir;
   public:

   bool Generate(dsFList::IO &IO);
   bool Lookup(dsFList::IO &IO,const char *Dir,const char *File,dsFList &List);
   
   dsFileListDB();
};

class dsMMapIO : public dsFList::IO
{
   FileFd Fd;
   MMap Map;
   unsigned long Pos;
   
   public:
   
   virtual bool Read(void *Buf,unsigned long Len);
   virtual bool Write(const void *Buf,unsigned long Len);
   virtual bool Seek(unsigned long Bytes);
   virtual unsigned long Tell();
   
   dsMMapIO(string File);
};

#endif

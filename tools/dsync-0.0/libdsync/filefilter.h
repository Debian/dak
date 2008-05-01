// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: filefilter.h,v 1.2 1998/12/30 05:36:41 jgg Exp $
/* ######################################################################
   
   File Filter - Regular Expression maching filter
   
   This implements an ordered include/exclude filter list that can be used
   to filter filenames.

   Pattern matching is done identically to rsync, the key points are:
    - Patterns containing / are matched against the whole path, otherwise
      only the file name is used.
    - Patterns that end in a / only match directories
    - Wildcards supported by fnmatch (?*[)
   
   ##################################################################### */
									/*}}}*/
#ifndef DSYNC_FILEFILTER
#define DSYNC_FILEFILTER

#ifdef __GNUG__
#pragma interface "dsync/filefilter.h"
#endif 

#include <string>
#include <dsync/configuration.h>

class dsFileFilter
{
   protected:
   
   struct Item
   {
      enum {Include, Exclude} Type;
      string Pattern;
      
      // Various flags.
      enum {MatchAll = (1<<0), MatchPath = (1<<1)};
      unsigned long Flags;
      
      Item *Next;

      bool Test(const char *Directory,const char *File);
   };
   Item *List;
   
   public:

   // Members to see if the filter hits or misses
   bool Test(const char *Directory,const char *File);
   
   // Load the filter from a configuration space
   bool LoadFilter(Configuration::Item const *Root);
      
   dsFileFilter();
   ~dsFileFilter();
};

#endif

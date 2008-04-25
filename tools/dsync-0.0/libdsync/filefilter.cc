// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: filefilter.cc,v 1.4 1999/08/05 03:22:55 jgg Exp $
/* ######################################################################

   File Filter - Regular Expression maching filter
   
   The idea for this was stolen shamelessly from rsync.

   Doesn't work:
    dsync-flist -e binary-alpha -i binary-all -i binary-i386 generate /tmp/listing
   
   And various other incantations like that.
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync/filefilter.h"
#endif

#include <dsync/filefilter.h>
#include <dsync/error.h>

#include <fnmatch.h>
using namespace std;
									/*}}}*/

// FileFilter::dsFileFilter - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsFileFilter::dsFileFilter() : List(0)
{
}
									/*}}}*/
// FileFilter::~dsFileFilter - Destructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsFileFilter::~dsFileFilter()
{
   while (List != 0)
   {
      Item *Tmp = List;
      List = Tmp->Next;
      delete Tmp;
   }
}
									/*}}}*/
// FileFilter::Test - Test a directory and file				/*{{{*/
// ---------------------------------------------------------------------
/* This will return true if the named entity is included by the filter, false
   otherwise. By default all entries are included. */
bool dsFileFilter::Test(const char *Directory,const char *File)
{
   for (Item *I = List; I != 0; I = I->Next)
   {
      bool Res = I->Test(Directory,File);
      if (Res == false)
	 continue;
      
      if (I->Type == Item::Include)
	 return true;
      
      if (I->Type == Item::Exclude)
	 return false;
   }
   
   return true;
}
									/*}}}*/
// FileFilter::LoadFilter - Load the filter list from the configuration	/*{{{*/
// ---------------------------------------------------------------------
/* When given the root of a configuration tree this will parse that sub-tree
   as an ordered list of include/exclude directives. Each value in the list
   must be prefixed with a + or a - indicating include/exclude */
bool dsFileFilter::LoadFilter(Configuration::Item const *Top)
{
   if (Top != 0)
      Top = Top->Child;
   
   // Advance to the end of the list
   Item **End = &List;
   for (; *End != 0; End = &(*End)->Next);
      
   for (; Top != 0;)
   {
      Item *New = new Item;
      
      // Decode the type
      if (Top->Value[0] == '+')
	 New->Type = Item::Include;
      else
      {
	 if (Top->Value[0] == '-')
	    New->Type = Item::Exclude;
         else
         {
	    delete New;
	    return _error->Error("Malformed filter directive %s",Top->Tag.c_str());
	 }
      }

      // Strip off the +/- indicator
      unsigned int Count = 1;
      for (const char *I = Top->Value.c_str() + 1; I < Top->Value.c_str() + strlen(Top->Value.c_str()) &&
	     isspace(*I); I++)
	 Count++;
      New->Pattern = string(Top->Value,Count);
      
      // Set flags
      New->Flags = 0;
      if (New->Pattern == "*")
	 New->Flags |= Item::MatchAll;
      if (New->Pattern.find('/') != string::npos)
	 New->Flags |= Item::MatchPath;
      
      // Link it into the list
      New->Next = 0;
      *End = New;
      End = &New->Next;
      
      Top = Top->Next;
   }
   return true;
}
									/*}}}*/
// FileFilter::Item::Test - Test a single item				/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFileFilter::Item::Test(const char *Directory,const char *File)
{
   // Catch all
   if ((Flags & MatchAll) == MatchAll)
      return true;
 
   // Append the direcotry
   if ((Flags & MatchPath) == MatchPath)
   {
      char S[1024];
      if (strlen(Directory) + strlen(File) > sizeof(S))
	  return _error->Error("File field overflow");
      strcpy(S,Directory);
      strcat(S,File);
      
      return fnmatch(Pattern.c_str(),S,FNM_PATHNAME) == 0;
   }
   
   return fnmatch(Pattern.c_str(),File,FNM_PATHNAME) == 0;
}
									/*}}}*/

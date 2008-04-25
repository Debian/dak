// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: filelistdb.cc,v 1.4 1999/02/27 08:00:05 jgg Exp $
/* ######################################################################
   
   File List Database

   The mmap class should probably go someplace else..
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync/filelistdb.h"
#endif

#include <dsync/filelistdb.h>
#include <dsync/error.h>
									/*}}}*/

// FileListDB::dsFileListDB - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsFileListDB::dsFileListDB()
{
}
									/*}}}*/
// FileListDB::Generate - Build the directory map			/*{{{*/
// ---------------------------------------------------------------------
/* This sucks the offset of every directory record into a stl map for 
   quick lookup. */
bool dsFileListDB::Generate(dsFList::IO &IO)
{
   // Iterate over the file
   dsFList List;
   while (List.Step(IO) == true)
   {
      // Record the current location so we can jump to it
      unsigned long Pos = IO.Tell();
      string LastSymlink = IO.LastSymlink;

      if (List.Tag == dsFList::tTrailer)
	 return true;
	 
      // We only index directory start records
      if (List.Tag != dsFList::tDirStart)
	 continue;
      
      // Store it in the map
      Location &Loc = Map[List.Dir.Name];
      Loc.Offset = Pos;
      Loc.LastSymlink = LastSymlink;
   }
  
   return false;
}
									/*}}}*/
// FileListDB::Lookup - Find a directory and file 			/*{{{*/
// ---------------------------------------------------------------------
/* We use a caching scheme, if the last lookup is in the same directory
   we do not re-seek but mearly look at the next entries till termination
   then wraps around. In the case of a largely unchanged directory this 
   gives huge speed increases. */
bool dsFileListDB::Lookup(dsFList::IO &IO,const char *Dir,const char *File,
			  dsFList &List)
{
   map<string,Location>::const_iterator I = Map.find(Dir);
   if (I == Map.end())
      return false;
   
   // See if we should reseek
   bool Restart = true;
   if (LastDir != Dir || LastDir.empty() == true)
   {
      Restart = false;
      IO.LastSymlink = I->second.LastSymlink;
      if (IO.Seek(I->second.Offset) == false)
	 return false;
      LastDir = Dir;
   }

   List.Head = IO.Header;
   while (List.Step(IO) == true)
   {
      // Oops, ran out of directories
      if (List.Tag == dsFList::tDirEnd ||
	  List.Tag == dsFList::tDirStart ||
	  List.Tag == dsFList::tTrailer)
      {
	 if (Restart == false)
	 {
	    LastDir = string();
	    return false;
	 }
	 
	 Restart = false;
	 IO.LastSymlink = I->second.LastSymlink;
	 if (IO.Seek(I->second.Offset) == false)
	    return false;
	 LastDir = Dir;

	 continue;
      }
      
      // Skip over non directory contents
      if (List.Tag == dsFList::tDirMarker ||
	  List.Tag == dsFList::tDirEnd ||
	  List.Tag == dsFList::tDirStart ||
	  List.Entity == 0)
	 continue;

      if (List.Entity->Name == File)
	 return true;
   }
   return false;
}
									/*}}}*/

// MMapIO::dsMMapIO - Constructor					/*{{{*/
// ---------------------------------------------------------------------
/* */
dsMMapIO::dsMMapIO(string File) : Fd(File,FileFd::ReadOnly), 
              Map(Fd,MMap::Public | MMap::ReadOnly)
{
   Pos = 0;
}
									/*}}}*/
// MMapIO::Read - Read bytes from the map				/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsMMapIO::Read(void *Buf,unsigned long Len)
{
   if (Pos + Len > Map.Size())
      return _error->Error("Attempt to read past end of mmap");
   memcpy(Buf,(unsigned char *)Map.Data() + Pos,Len);
   Pos += Len;
   return true;
}
									/*}}}*/
// MMapIO::Write - Write bytes (fail)					/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsMMapIO::Write(const void *Buf,unsigned long Len)
{
   return _error->Error("Attempt to write to read only mmap");
}
									/*}}}*/
// MMapIO::Seek - Jump to a spot					/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsMMapIO::Seek(unsigned long Bytes)
{
   if (Bytes > Map.Size())
      return _error->Error("Attempt to seek past end of mmap");
   Pos = Bytes;
   return true;
}
									/*}}}*/
// MMapIO::Tell - Return the current location				/*{{{*/
// ---------------------------------------------------------------------
/* */
unsigned long dsMMapIO::Tell()
{
   return Pos;
}
									/*}}}*/

// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: path-utils.cc,v 1.2 1999/03/22 02:52:46 jgg Exp $
/* ######################################################################

   Misc utility functions for dsync-flist to make use of.
   
   ##################################################################### */
									/*}}}*/
#include "dsync-flist.h"
#include <unistd.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <dsync/error.h>
#include <string.h>

// SimplifyPath - Short function to remove relative path components	/*{{{*/
// ---------------------------------------------------------------------
/* This short function removes relative path components such as ./ and ../
   from the path and removes double // as well. It works by seperating
   the path into a list of components and then removing any un-needed
   compoments */
bool SimplifyPath(char *Buffer)
{
   // Create a list of path compoments
   char *Pos[100];
   unsigned CurPos = 0;
   Pos[CurPos] = Buffer;
   CurPos++;   
   for (char *I = Buffer; *I != 0;)
   {
      if (*I == '/')
      {
	 *I = 0;
	 I++;
	 Pos[CurPos] = I;
	 CurPos++;
      }
      else
	 I++;
   }
   
   // Strip //, ./ and ../
   for (unsigned I = 0; I != CurPos; I++)
   {
      if (Pos[I] == 0)
	 continue;
      
      // Double slash
      if (Pos[I][0] == 0)
      {
	 if (I != 0)
	    Pos[I] = 0;
	 continue;
      }
      
      // Dot slash
      if (Pos[I][0] == '.' && Pos[I][1] == 0)
      {
	 Pos[I] = 0;
	 continue;
      }
      
      // Dot dot slash
      if (Pos[I][0] == '.' && Pos[I][1] == '.' && Pos[I][2] == 0)
      {
	 Pos[I] = 0;
	 unsigned J = I;
	 for (; Pos[J] == 0 && J != 0; J--);
	 if (Pos[J] == 0)
	    return _error->Error("Invalid path, too many ../s");
	 Pos[J] = 0;	 
	 continue;
      }
   }  

   // Recombine the path into full path
   for (unsigned I = 0; I != CurPos; I++)
   {
      if (Pos[I] == 0)
	 continue;
      memmove(Buffer,Pos[I],strlen(Pos[I]));
      Buffer += strlen(Pos[I]);
      
      if (I + 1 != CurPos)
	 *Buffer++ = '/';
   }   		
   *Buffer = 0;
   
   return true;
}
									/*}}}*/
// ResolveLink - Resolve a file into an unsymlinked path		/*{{{*/
// ---------------------------------------------------------------------
/* The returned path is a path that accesses the same file without 
   traversing a symlink, the memory buffer used should be twice as large
   as the largest path. It uses an LRU cache of past lookups to speed things
   up, just don't change directores :> */
struct Cache
{
   string Dir;
   string Trans;
   unsigned long Age;
};
static Cache DirCache[400];
static unsigned long CacheAge = 0;
bool ResolveLink(char *Buffer,unsigned long Max)
{
   if (Buffer[0] == 0 || (Buffer[0] == '/' && Buffer[1] == 0))
      return true;

   // Lookup in the cache
   Cache *Entry = 0;
   for (int I = 0; I != 400; I++)
   {
      // Store an empty entry
      if (DirCache[I].Dir.empty() == true)
      {
	 Entry = &DirCache[I];
	 Entry->Age = 0;
	 continue;
      }
      
      // Store the LRU entry
      if (Entry != 0 && Entry->Age > DirCache[I].Age)
	 Entry = &DirCache[I];
      
      if (DirCache[I].Dir != Buffer || DirCache[I].Trans.empty() == true)
	 continue;
      strcpy(Buffer,DirCache[I].Trans.c_str());
      DirCache[I].Age = CacheAge++;
      return true;
   }
   
   // Prepare the cache for our new entry
   if (Entry != 0 && Buffer[strlen(Buffer) - 1] == '/')
   {
      Entry->Age = CacheAge++;
      Entry->Dir = Buffer;
   }   
   else
      Entry = 0;

   // Resolve any symlinks
   unsigned Counter = 0;
   while (1)
   {
      Counter++;
      if (Counter > 50)
	 return _error->Error("Exceeded allowed symlink depth");
      
      // Strip off the final component name
      char *I = Buffer + strlen(Buffer);
      for (; I != Buffer && (*I == '/' || *I == 0); I--);
      for (; I != Buffer && *I != '/'; I--);
      if (I != Buffer)
	 I++;

      if (strlen(I) == 0)
	 break;
      

      /* We need to remove the final slash in the directory component for
         readlink to work right */
      char *End = 0;
      if (I[strlen(I) - 1] == '/')
      {
	 End = I + strlen(I) - 1;
	 *End = 0;
      }
      
      int Res = readlink(Buffer,I,Max - (I - Buffer) - 2);
            
      // If it is a link then read the link dest over the final component
      if (Res > 0)
      {
	 I[Res] = 0;
	 
	 // Absolute path..
	 if (*I == '/')
	    memmove(Buffer,I,strlen(I)+1);

	 // Put the slash back.. 
	 if (End != 0)
	 {	 
	    I[Res] = '/';
	    I[Res + 1] = 0;
	 }
	 
	 if (SimplifyPath(Buffer) == false)
	    return false;	 
      }
      else
      {
	 // Put the slash back.. 
	 if (End != 0)
	    *End = '/';	 
	 break;
      }
      
   }
   
   /* Here we are abusive and move the current path component to the end 
      of the buffer to advoid allocating space */
   char *I = Buffer + strlen(Buffer);
   for (; I != Buffer && (*I == '/' || *I == 0); I--);
   for (; I != Buffer && *I != '/'; I--);
   if (I != Buffer)
      I++;
   unsigned Len = strlen(I) + 1;
   char *End = Buffer + Max - Len;
   memmove(End,I,Len);
   *I = 0;

   
   // Recurse to deal with any links in the files path
   if (ResolveLink(Buffer,Max - Len) == false)
      return false;
   I = Buffer + strlen(Buffer);
   memmove(I,End,Len);

   // Store in the cache
   if (Entry != 0)
      Entry->Trans = Buffer;
   
   return true;
}
									/*}}}*/

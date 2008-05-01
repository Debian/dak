// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: compare.cc,v 1.6 1999/12/26 06:59:00 jgg Exp $
/* ######################################################################
   
   Compare a file list with a local directory
   
   The first step in the compare is to read the names of each entry
   in the local directory into ram. This list is the first step to
   creating a delete list. Next we begin scanning the file list, checking
   each entry against the dir contents, if a match is found it is removed
   from the dir list and then stat'd to verify against the file list
   contents. If no match is found then the entry is marked for download.
   When done the local directory in ram will only contain entries that 
   need to be erased.
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync/compare.h"
#endif

#include <dsync/compare.h>
#include <dsync/error.h>
#include <dsync/fileutl.h>
#include <dsync/md5.h>

#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <dirent.h>
#include <utime.h>
#include <stdio.h>
									/*}}}*/

// DirCompre::dsDirCompare - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsDirCompare::dsDirCompare() : IndexSize(0), IndexAlloc(0), Indexes(0),
                     NameAlloc(0), Names(0), Verify(true), HashLevel(Md5Date)
{
   IndexAlloc = 1000;
   Indexes = (unsigned int *)malloc(sizeof(*Indexes)*IndexAlloc);
   NameAlloc = 4096*5;
   Names = (char *)malloc(sizeof(*Names)*NameAlloc);
   if (Names == 0 || Indexes == 0)
      _error->Error("Cannot allocate memory");
}
									/*}}}*/
// DirCompare::~dsDirCompare - Destructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsDirCompare::~dsDirCompare()
{
   free(Names);
   free(Indexes);
}
									/*}}}*/
// DirCompare::LoadDir - Load all the names in the directory		/*{{{*/
// ---------------------------------------------------------------------
/* Such in every name in the directory, we store them as a packed, indexed
   array of strings */
bool dsDirCompare::LoadDir()
{
   // Scan the directory
   DIR *DirSt = opendir(".");
   if (DirSt == 0)
      return _error->Errno("opendir","Unable to open directory %s",SafeGetCWD().c_str());
   struct dirent *Ent;
   IndexSize = 0;
   char *End = Names + 1;
   while ((Ent = readdir(DirSt)) != 0)
   {
      // Skip . and ..
      if (strcmp(Ent->d_name,".") == 0 ||
	  strcmp(Ent->d_name,"..") == 0)
	 continue;
      
      // Grab some more bytes in the name allocation
      if ((unsigned)(NameAlloc - (End - Names)) <= strlen(Ent->d_name)+1)
      {
	 unsigned long OldEnd = End - Names;
	 char *New = (char *)realloc(Names,sizeof(*Names)*NameAlloc + 4*4096);
	 if (New == 0)
	 {
	    closedir(DirSt);
	    return _error->Error("Cannot allocate memory");
	 }
	 
	 Names = New;
	 NameAlloc += 4*4096;
	 End = Names + OldEnd;
      }
      
      // Grab some more bytes in the index allocation
      if (IndexSize >= IndexAlloc)
      {
	 unsigned int *New = (unsigned int *)realloc(Indexes,
			     sizeof(*Indexes)*IndexAlloc + 1000);
	 if (New == 0)
	 {   
	    closedir(DirSt);
	    return _error->Error("Cannot allocate memory");
	 }
	 
	 Indexes = New;
	 IndexAlloc += 4*4096;
      }
      
      // Store it
      Indexes[IndexSize] = End - Names;
      IndexSize++;
      strcpy(End,Ent->d_name);
      End += strlen(End) + 1;
   }
   
   closedir(DirSt);
   return true;
}
									/*}}}*/
// DirCompare::Process - Process the file list stream			/*{{{*/
// ---------------------------------------------------------------------
/* This scans over the dirs from the IO and decides what to do with them */
bool dsDirCompare::Process(string Base,dsFList::IO &IO)
{
   // Setup the queues and store the current directory
   string StartDir = SafeGetCWD();
   
   // Change to the base directory
   if (chdir(Base.c_str()) != 0)
      return _error->Errno("chdir","Could not change to %s",Base.c_str());
   Base = SafeGetCWD();
   this->Base = Base;
   
   string CurDir;
   dsFList List;
   bool Missing = false;
   while (List.Step(IO) == true)
   {
      if (Visit(List,CurDir) == false)
	 return false;
      
      switch (List.Tag)
      {
	 // Handle a forward directory reference
	 case dsFList::tDirMarker:
	 {
	    // Ingore the root directory
	    if (List.Entity->Name.empty() == true)
	       continue;
	    
	    char S[1024];

	    snprintf(S,sizeof(S),"%s%s",Base.c_str(),List.Entity->Name.c_str());
	    
	    /* We change the path to be absolute for the benifit of the 
	       routines below */
	    List.Entity->Name = S;
	    
	    // Stat the marker dir
	    struct stat St;
	    bool Res;
	    if (lstat(S,&St) != 0)
	       Res = Fetch(List,string(),0);
	    else
	       Res = Fetch(List,string(),&St);

	    if (Res == false)
	       return false;
	    break;
	 }
	 
	 // Start a directory
	 case dsFList::tDirStart:
	 {	    
	    if (DoDelete(CurDir) == false)
	       return false;
	    if (chdir(Base.c_str()) != 0)
	       return _error->Errno("chdir","Could not change to %s",Base.c_str());
	    
	    CurDir = List.Dir.Name;
	    Missing = false;
	    IndexSize = 0;
	    if (List.Dir.Name.empty() == false)
	    {
	       /* Instead of erroring out we just mark them as missing and
	          do not re-stat. This is to support the verify mode, the
		  actual downloader should never get this. */
	       if (chdir(List.Dir.Name.c_str()) != 0)
	       {
		  if (Verify == false)
		     return _error->Errno("chdir","Unable to cd to %s%s.",Base.c_str(),List.Dir.Name.c_str());
		  Missing = true;
	       }	       
	    }
	    
	    if (Missing == false)
	       LoadDir();
	    break;
	 }
	 
	 // Finalize the directory
	 case dsFList::tDirEnd:
	 {
	    if (DoDelete(CurDir) == false)
	       return false;
	    IndexSize = 0;
	    if (chdir(Base.c_str()) != 0)
	       return _error->Errno("chdir","Could not change to %s",Base.c_str());
	    break;
	 }	 
      }
      
      // We have some sort of normal entity
      if (List.Entity != 0 && List.Tag != dsFList::tDirMarker &&
	  List.Tag != dsFList::tDirStart)
      {
	 // See if it exists, if it does then stat it
	 bool Res = true;
	 if (Missing == true || DirExists(List.Entity->Name) == false)
	    Res = Fetch(List,CurDir,0);
	 else
	 {
	    struct stat St;
	    if (lstat(List.Entity->Name.c_str(),&St) != 0)
	       Res = Fetch(List,CurDir,0);
	    else
	       Res = Fetch(List,CurDir,&St);
	 }
	 if (Res == false)
	    return false;
      }
      
      // Fini
      if (List.Tag == dsFList::tTrailer)
      {
	 if (DoDelete(CurDir) == false)
	    return false;
	 return true;
      }      
   }
   
   return false;
}
									/*}}}*/
// DirCompare::DoDelete - Delete files in the delete list		/*{{{*/
// ---------------------------------------------------------------------
/* The delete list is created by removing names that were found till only
   extra names remain */
bool dsDirCompare::DoDelete(string Dir)
{
   for (unsigned int I = 0; I != IndexSize; I++)
   {
      if (Indexes[I] == 0)
	 continue;
      if (Delete(Dir,Names + Indexes[I]) == false)
	 return false;
   }
   
   return true;
}
									/*}}}*/
// DirCompare::Fetch - Fetch an entity					/*{{{*/
// ---------------------------------------------------------------------
/* This examins an entry to see what sort of fetch should be done. There
   are three sorts, 
     New - There is no existing data
     Changed - There is existing data
     Meta - The data is fine but the timestamp/owner/perms might not be */
bool dsDirCompare::Fetch(dsFList &List,string Dir,struct stat *St)
{
   if (List.Tag != dsFList::tNormalFile && List.Tag != dsFList::tDirectory &&
       List.Tag != dsFList::tSymlink && List.Tag != dsFList::tDeviceSpecial &&
       List.Tag != dsFList::tDirMarker)
      return _error->Error("dsDirCompare::Fetch called for an entity "
			   "that it does not understand");
   
   // This is a new entitiy
   if (St == 0)
      return GetNew(List,Dir);

   /* Check the types for a mis-match, if they do not match then 
      we have to erase the entity and get a new one */
   if ((S_ISREG(St->st_mode) != 0 && List.Tag != dsFList::tNormalFile) ||
       (S_ISDIR(St->st_mode) != 0 && (List.Tag != dsFList::tDirectory && 
				      List.Tag != dsFList::tDirMarker)) ||
       (S_ISLNK(St->st_mode) != 0 && List.Tag != dsFList::tSymlink) ||
       ((S_ISCHR(St->st_mode) != 0 || S_ISBLK(St->st_mode) != 0 || 
	 S_ISFIFO(St->st_mode) != 0) && List.Tag != dsFList::tDeviceSpecial))
   {
      return Delete(Dir,List.Entity->Name.c_str(),true) && GetNew(List,Dir);
   }
   
   // First we check permissions and mod time
   bool ModTime = (signed)(List.Entity->ModTime + List.Head.Epoch) == St->st_mtime;
   bool Perm = true;
   if ((List.Head.Flags[List.Tag] & dsFList::DirEntity::FlPerm) != 0)
      Perm = List.Entity->Permissions == (unsigned)(St->st_mode & ~S_IFMT);
      
   // Normal file
   if (List.Tag == dsFList::tNormalFile)
   {
      // Size mismatch is an immedate fail
      if (List.NFile.Size != (unsigned)St->st_size)
	 return GetChanged(List,Dir);

      // Try to check the stored MD5
      if (HashLevel == Md5Always || 
	  (HashLevel == Md5Date && ModTime == false))
      {
	 if ((List.Head.Flags[List.Tag] & dsFList::NormalFile::FlMD5) != 0)
	 {
	    if (CheckHash(List,Dir,List.NFile.MD5) == true)
	       return FixMeta(List,Dir,*St);
	    else
	       return GetChanged(List,Dir);
	 }	 
      }
      
      // Look at the modification time
      if (ModTime == true)
	 return FixMeta(List,Dir,*St);
      return GetChanged(List,Dir);
   }

   // Check symlinks
   if (List.Tag == dsFList::tSymlink)
   {
      char Buf[1024];
      int Res = readlink(List.Entity->Name.c_str(),Buf,sizeof(Buf));
      if (Res > 0)
	 Buf[Res] = 0;
      
      // Link is invalid
      if (Res < 0 || List.SLink.To != Buf)
	 return GetNew(List,Dir);
      
      return FixMeta(List,Dir,*St);
   }

   // Check directories and dev special files
   if (List.Tag == dsFList::tDirectory || List.Tag == dsFList::tDeviceSpecial ||
       List.Tag == dsFList::tDirMarker)
      return FixMeta(List,Dir,*St);
   
   return true;
}
									/*}}}*/
// DirCompare::DirExists - See if the entry exists in our dir table	/*{{{*/
// ---------------------------------------------------------------------
/* We look at the dir table for one that exists */
bool dsDirCompare::DirExists(string Name)
{
   for (unsigned int I = 0; I != IndexSize; I++)
   {
      if (Indexes[I] == 0)
	 continue;
      if (Name == Names + Indexes[I])
      {
	 Indexes[I] = 0;
	 return true;
      }
   }
   return false;
}
									/*}}}*/
// DirCompare::CheckHash - Check the MD5 of a entity			/*{{{*/
// ---------------------------------------------------------------------
/* This is invoked to see of the local file we have is the file the remote
   says we should have. */
bool dsDirCompare::CheckHash(dsFList &List,string Dir,unsigned char MD5[16])
{
   // Open the file
   MD5Summation Sum;
   FileFd Fd(List.Entity->Name,FileFd::ReadOnly);
   if (_error->PendingError() == true)
      return _error->Error("MD5 generation failed for %s%s",Dir.c_str(),
			   List.Entity->Name.c_str());

   if (Sum.AddFD(Fd.Fd(),Fd.Size()) == false)
      return _error->Error("MD5 generation failed for %s%s",Dir.c_str(),
			   List.Entity->Name.c_str());

   unsigned char MyMD5[16];
   Sum.Result().Value(MyMD5);

   return memcmp(MD5,MyMD5,sizeof(MyMD5)) == 0;
}
									/*}}}*/
// DirCompare::FixMeta - Fix timestamps, ownership and permissions	/*{{{*/
// ---------------------------------------------------------------------
/* This checks if it is necessary to correct the timestamps, ownership and
   permissions of an entity */
bool dsDirCompare::FixMeta(dsFList &List,string Dir,struct stat &St)
{   
   // Check the mod time
   if (List.Tag != dsFList::tSymlink)
   {
      if ((signed)(List.Entity->ModTime + List.Head.Epoch) != St.st_mtime)
	 if (SetTime(List,Dir) == false)
	    return false;
   
      // Check the permissions
      if ((List.Head.Flags[List.Tag] & dsFList::DirEntity::FlPerm) != 0)
      {
	 if (List.Entity->Permissions != (St.st_mode & ~S_IFMT))
	    if (SetPerm(List,Dir) == false)
	       return false;
      }
   }
      
   return true;
}
									/*}}}*/

// DirCorrect::GetNew - Create a new entry				/*{{{*/
// ---------------------------------------------------------------------
/* We cannot create files but we do generate everything else. */
bool dsDirCorrect::GetNew(dsFList &List,string Dir)
{
   if (List.Tag == dsFList::tDirectory)
   {
      unsigned long PermDir = 0666;
      if ((List.Head.Flags[List.Tag] & dsFList::DirEntity::FlPerm) != 0)
	 PermDir = List.Entity->Permissions;
	 
      if (mkdir(List.Entity->Name.c_str(),PermDir) != 0)
	 return _error->Errno("mkdir","Unable to create directory, %s%s",
			      Dir.c_str(),List.Entity->Name.c_str());

      // Stat the newly created file for FixMeta's benifit
      struct stat St;
      if (lstat(List.Entity->Name.c_str(),&St) != 0)
	 return _error->Errno("stat","Unable to stat directory, %s%s",
			      Dir.c_str(),List.Entity->Name.c_str());

      return FixMeta(List,Dir,St);
   }

   if (List.Tag == dsFList::tSymlink)
   {
      if (symlink(List.SLink.To.c_str(),List.Entity->Name.c_str()) != 0)
	 return _error->Errno("symlink","Unable to create symlink, %s%s",
			      Dir.c_str(),List.Entity->Name.c_str());

      // Stat the newly created file for FixMeta's benifit
      struct stat St;
      if (lstat(List.Entity->Name.c_str(),&St) != 0)
	 return _error->Errno("stat","Unable to stat directory, %s%s",
			      Dir.c_str(),List.Entity->Name.c_str());

      return FixMeta(List,Dir,St);
   }
   
   if (List.Tag == dsFList::tDeviceSpecial)
   {
      unsigned long PermDev;
      if ((List.Head.Flags[List.Tag] & dsFList::DirEntity::FlPerm) != 0)
	 PermDev = List.Entity->Permissions;
      else
	 return _error->Error("Corrupted file list");
      
      if (mknod(List.Entity->Name.c_str(),PermDev,List.DevSpecial.Dev) != 0)
	 return _error->Errno("mkdir","Unable to create directory, %s%s",
			      Dir.c_str(),List.Entity->Name.c_str());

      // Stat the newly created file for FixMeta's benifit
      struct stat St;
      if (lstat(List.Entity->Name.c_str(),&St) != 0)
	 return _error->Errno("stat","Unable to stat directory, %s%s",
			      Dir.c_str(),List.Entity->Name.c_str());
      return FixMeta(List,Dir,St);
   }   
}
									/*}}}*/
// DirCorrect::DirUnlink - Unlink a directory				/*{{{*/
// ---------------------------------------------------------------------
/* This just recursively unlinks stuff */
bool dsDirCorrect::DirUnlink(const char *Path)
{
   // Record what dir we were in
   struct stat Dir;
   if (lstat(".",&Dir) != 0)
      return _error->Errno("lstat","Unable to stat .!");

   if (chdir(Path) != 0)
      return _error->Errno("chdir","Unable to change to %s",Path);
	     
   // Scan the directory
   DIR *DirSt = opendir(".");
   if (DirSt == 0)
   {
      chdir("..");
      return _error->Errno("opendir","Unable to open directory %s",Path);
   }
   
   // Erase this directory
   struct dirent *Ent;
   while ((Ent = readdir(DirSt)) != 0)
   {
      // Skip . and ..
      if (strcmp(Ent->d_name,".") == 0 ||
	  strcmp(Ent->d_name,"..") == 0)
	 continue;

      struct stat St;
      if (lstat(Ent->d_name,&St) != 0)
	 return _error->Errno("stat","Unable to stat %s",Ent->d_name);
      if (S_ISDIR(St.st_mode) == 0)
      {
	 // Try to unlink the file
	 if (unlink(Ent->d_name) != 0)
	 {
	    chdir("..");
	    return _error->Errno("unlink","Unable to remove file %s",Ent->d_name);
	 }	 
      }
      else
      {
	 if (DirUnlink(Ent->d_name) == false)
	 {
	    chdir("..");
	    closedir(DirSt);
	    return false;
	 }	 
      }	 
   }
   closedir(DirSt);
   chdir("..");
   
   /* Make sure someone didn't screw with the directory layout while we
      were erasing */
   struct stat Dir2;
   if (lstat(".",&Dir2) != 0)
      return _error->Errno("lstat","Unable to stat .!");
   if (Dir2.st_ino != Dir.st_ino || Dir2.st_dev != Dir.st_dev)
      return _error->Error("Hey! Someone is fiddling with the dir tree as I erase it!");

   if (rmdir(Path) != 0)
      return _error->Errno("rmdir","Unable to remove directory %s",Ent->d_name);
   
   return true;
}
									/*}}}*/
// DirCorrect::Delete - Delete an entry					/*{{{*/
// ---------------------------------------------------------------------
/* This obliterates an entity - recursively, use with caution. */
bool dsDirCorrect::Delete(string Dir,const char *Name,bool Now)
{
   struct stat St;
   if (lstat(Name,&St) != 0)
      return _error->Errno("stat","Unable to stat %s%s",Dir.c_str(),Name);
      
   if (S_ISDIR(St.st_mode) == 0)
   {
      if (unlink(Name) != 0)
	 return _error->Errno("unlink","Unable to remove %s%s",Dir.c_str(),Name);
   }
   else
   {
      if (DirUnlink(Name) == false)
	 return _error->Error("Unable to erase directory %s%s",Dir.c_str(),Name);
   }
   return true;   
}
									/*}}}*/
// DirCorrect::GetChanged - Get a changed entry				/*{{{*/
// ---------------------------------------------------------------------
/* This is only called for normal files, we cannot do anything here. */
bool dsDirCorrect::GetChanged(dsFList &List,string Dir)
{   
   return true;
}
									/*}}}*/
// DirCorrect::SetTime - Change the timestamp				/*{{{*/
// ---------------------------------------------------------------------
/* This fixes the mod time of the file */
bool dsDirCorrect::SetTime(dsFList &List,string Dir)
{
   struct utimbuf Time;
   Time.actime = Time.modtime = List.Entity->ModTime + List.Head.Epoch;
   if (utime(List.Entity->Name.c_str(),&Time) != 0)
      return _error->Errno("utimes","Unable to change mod time for %s%s",
			   Dir.c_str(),List.Entity->Name.c_str());
   return true;
}
									/*}}}*/
// DirCorrect::SetPerm - Change the permissions				/*{{{*/
// ---------------------------------------------------------------------
/* This fixes the permissions */
bool dsDirCorrect::SetPerm(dsFList &List,string Dir)
{
   if (chmod(List.Entity->Name.c_str(),List.Entity->Permissions) != 0)
      return _error->Errno("chmod","Unable to change permissions for %s%s",
			   Dir.c_str(),List.Entity->Name.c_str());
   return true;
}
									/*}}}*/
// Dircorrect::SetOwner - Change ownership				/*{{{*/
// ---------------------------------------------------------------------
/* This fixes the file ownership */
bool dsDirCorrect::SetOwners(dsFList &List,string Dir)
{
   return _error->Error("Ownership is not yet supported");
}
									/*}}}*/
   

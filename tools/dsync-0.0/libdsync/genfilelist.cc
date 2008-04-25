// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: genfilelist.cc,v 1.10 1999/12/26 06:59:01 jgg Exp $
/* ######################################################################
   
   Generate File List 

   File list generation can be done with modification to the generation
   order, ordering can be done by depth, breadth or by tree with and
   a fitler can be applied to delay a directory till the end of processing.
   
   The emitter simply generates the necessary structure and writes it to
   the IO. The client can hook some of the functions to provide progress
   reporting and md5 caching if so desired.
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync/genfilelist.h"
#endif

#include <dsync/genfilelist.h>
#include <dsync/error.h>
#include <dsync/fileutl.h>
#include <dsync/md5.h>
#include <dsync/fileutl.h>
#include <dsync/rsync-algo.h>

#include <sys/stat.h>
#include <unistd.h>
#include <dirent.h>
#include <stdio.h>
									/*}}}*/

// GenFileList::dsGenFileList - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsGenFileList::dsGenFileList() : IO(0), Type(Tree)
{
}
									/*}}}*/
// GenFileList::~dsGenFileList - Destructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsGenFileList::~dsGenFileList()
{
}
									/*}}}*/
// GenFileList::Go - Generate the list					/*{{{*/
// ---------------------------------------------------------------------
/* This invokes the proper recursive directory scanner to build the file
   names. Depth and Breath use a queue */
bool dsGenFileList::Go(string Base,dsFList::IO &IO)
{
   // Setup the queues and store the current directory
   string StartDir = SafeGetCWD();
   Queue.erase(Queue.begin(),Queue.end());
   DelayQueue.erase(Queue.begin(),Queue.end());

   struct stat St;
   if (stat(Base.c_str(),&St) != 0)
      return _error->Errno("stat","Could not stat the base directory");
   
   // Begin
   this->IO = &IO;
   IO.Header.Write(IO);
   
   switch (Type)
   {
      case Depth:
      {
	 // Change to the base directory
	 if (chdir(Base.c_str()) != 0)
	    return _error->Errno("chdir","Could not change to %s",Base.c_str());
	 Base = SafeGetCWD();
	 
	 char Cwd[1024];
	 Cwd[0] = 0;
	 if (DirDepthFirst(Cwd) == false)
	 {
	    chdir(StartDir.c_str());
	    return false;
	 }

	 // Now deal with the delay list
	 while (DelayQueue.empty() == false)
	 {
	    // Get the first delayed directory
	    string Dir = DelayQueue.front();
	    DelayQueue.pop_front();
	    
	    // Change to it and emit it.
	    strcpy(Cwd,Dir.c_str());
	    chdir(Base.c_str());
	    chdir(Cwd);
	    if (DirDepthFirst(Cwd) == false)
	    {
	       chdir(StartDir.c_str());
	       return false;
	    }	    
	 }
	 
	 break;
      }
      
      case Tree:
      case Breadth:
      {
	 // Change to the base directory
	 if (chdir(Base.c_str()) != 0)
	    return _error->Errno("chdir","Could not change to %s",Base.c_str());
	 Base = SafeGetCWD();

	 Queue.push_back("");
	 while (Queue.empty() == false || DelayQueue.empty() == false)
	 {
	    if (DirTree() == false)
	    {
	       chdir(StartDir.c_str());
	       return false;
	    }

	    chdir(Base.c_str());
	 }
	 break;
      }

      default:
      return _error->Error("Internal Error");
   }; 

   chdir(StartDir.c_str());
   
   dsFList::Trailer Trail;
   return Trail.Write(IO);
}
									/*}}}*/
// GenFileList::DirDepthFirst - Depth first directory ordering		/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsGenFileList::DirDepthFirst(char *CurDir)
{
   // Scan the directory, first pass is to descend into the sub directories
   DIR *DirSt = opendir(".");
   if (DirSt == 0)
      return _error->Errno("opendir","Unable to open direcotry %s",CurDir);
   struct dirent *Ent;
   bool EmittedThis = false;
   struct stat St;
   while ((Ent = readdir(DirSt)) != 0)
   {
      // Skip . and ..
      if (strcmp(Ent->d_name,".") == 0 ||
	  strcmp(Ent->d_name,"..") == 0)
	 continue;
      
      if (lstat(Ent->d_name,&St) != 0)
      {
	 closedir(DirSt);
	 return _error->Errno("stat","Could not stat %s%s",CurDir,Ent->d_name);
      }
      
      // it is a directory
      if (S_ISDIR(St.st_mode) != 0)
      {
	 char S[1024];
	 snprintf(S,sizeof(S),"%s/",Ent->d_name);
	 
	 // Check the Filter
	 if (Filter.Test(CurDir,S) == false)
	    continue;

	 // Emit a directory marker record for this directory
	 if (EmittedThis == false)
	 {
	    EmittedThis = true;

	    if (lstat(".",&St) != 0)
	    {
	       closedir(DirSt);
	       return _error->Errno("stat","Could not stat %s",CurDir);
	    }
	    
	    if (DirectoryMarker(CurDir,St) == false)
	    {
	       closedir(DirSt);
	       return false;
	    }	    
	 }

	 // Check the delay filter
	 if (PreferFilter.Test(CurDir,S) == false)
	 {
	    snprintf(S,sizeof(S),"%s%s/",CurDir,Ent->d_name);
	    DelayQueue.push_back(S);	    
	    continue;
	 }
	 
	 // Append the new directory to CurDir and decend
	 char *End = CurDir + strlen(CurDir);
	 strcat(End,S);
	 if (chdir(S) != 0)
	 {
	    closedir(DirSt);
	    return _error->Errno("chdir","Could not chdir to %s%s",CurDir,S);
	 }
	 
	 // Recurse
	 if (DirDepthFirst(CurDir) == false)
	 {
	    closedir(DirSt);
	    return false;
	 }

	 if (chdir("..") != 0)
	 {
	    closedir(DirSt);
	    return _error->Errno("chdir","Could not chdir to %s%s",CurDir,S);
	 }
	 
	 // Chop off the directory we added to the current dir
	 *End = 0;
      }
   }
   rewinddir(DirSt);

   // Begin emitting this directory
   if (lstat(".",&St) != 0)
   {
      closedir(DirSt);
      return _error->Errno("stat","Could not stat %s",CurDir);
   }
   
   if (EnterDir(CurDir,St) == false)
   {
      closedir(DirSt);
      return false;
   }
      
   while ((Ent = readdir(DirSt)) != 0)
   {
      // Skip . and ..
      if (strcmp(Ent->d_name,".") == 0 ||
	  strcmp(Ent->d_name,"..") == 0)
	 continue;
      
      struct stat St;
      if (lstat(Ent->d_name,&St) != 0)
      {
	 closedir(DirSt);
	 return _error->Errno("stat","Could not stat %s%s",CurDir,Ent->d_name);
      }
      
      // it is a directory
      if (S_ISDIR(St.st_mode) != 0)
      {
	 char S[1024];
	 snprintf(S,sizeof(S),"%s/",Ent->d_name);
	 
	 // Check the Filter
	 if (Filter.Test(CurDir,S) == false)
	    continue;
      }
      else
      {
	 // Check the Filter
	 if (Filter.Test(CurDir,Ent->d_name) == false)
	    continue;
      }
      
      if (DoFile(CurDir,Ent->d_name,St) == false)
      {
	 closedir(DirSt);
	 return false;
      }      
   }
   closedir(DirSt);
   
   if (LeaveDir(CurDir) == false)
      return false;
   
   return true;
}
									/*}}}*/
// GenFileList::DirTree - Breadth/Tree directory ordering		/*{{{*/
// ---------------------------------------------------------------------
/* Breadth ordering does all of the dirs at each depth before proceeding 
   to the next depth. We just treat the list as a queue to get this
   effect. Tree ordering does things in a more normal recursive fashion,
   we treat the queue as a stack to get that effect. */
bool dsGenFileList::DirTree()
{
   string Dir;
   if (Queue.empty() == false)
   {
      Dir = Queue.front();
      Queue.pop_front();
   }
   else
   {
      Dir = DelayQueue.front();
      DelayQueue.pop_front();
   }
   
   struct stat St;
   if (Dir.empty() == false && chdir(Dir.c_str()) != 0 || stat(".",&St) != 0)
      return _error->Errno("chdir","Could not change to %s",Dir.c_str());

   if (EnterDir(Dir.c_str(),St) == false)
      return false;
   
   // Scan the directory
   DIR *DirSt = opendir(".");
   if (DirSt == 0)
      return _error->Errno("opendir","Unable to open direcotry %s",Dir.c_str());
   struct dirent *Ent;
   while ((Ent = readdir(DirSt)) != 0)
   {
      // Skip . and ..
      if (strcmp(Ent->d_name,".") == 0 ||
	  strcmp(Ent->d_name,"..") == 0)
	 continue;
      
      if (lstat(Ent->d_name,&St) != 0)
      {
	 closedir(DirSt);
	 return _error->Errno("stat","Could not stat %s%s",Dir.c_str(),Ent->d_name);
      }
      
      // It is a directory
      if (S_ISDIR(St.st_mode) != 0)
      {
	 char S[1024];
	 snprintf(S,sizeof(S),"%s/",Ent->d_name);
	 
	 // Check the Filter
	 if (Filter.Test(Dir.c_str(),S) == false)
	    continue;

	 // Check the delay filter
	 if (PreferFilter.Test(Dir.c_str(),S) == false)
	 {
	    snprintf(S,sizeof(S),"%s%s/",Dir.c_str(),Ent->d_name);
	    if (Type == Tree)
	       DelayQueue.push_front(S);
	    else
	       DelayQueue.push_back(S);	    
	    continue;
	 }
	 
	 snprintf(S,sizeof(S),"%s%s/",Dir.c_str(),Ent->d_name);
	 
	 if (Type == Tree)
	    Queue.push_front(S);
	 else
	    Queue.push_back(S);
      }
      else
      {
	 // Check the Filter
	 if (Filter.Test(Dir.c_str(),Ent->d_name) == false)
	    continue;
      }
      
      if (DoFile(Dir.c_str(),Ent->d_name,St) == false)
      {
	 closedir(DirSt);
	 return false;
      }      
   }
   closedir(DirSt);
   
   if (LeaveDir(Dir.c_str()) == false)
      return false;
   
   return true;
}
									/*}}}*/

// GenFileList::EnterDir - Called when a directory is entered		/*{{{*/
// ---------------------------------------------------------------------
/* This is called to start a directory block the current working dir
   should be set to the directory entered. This emits the directory start
   record */
bool dsGenFileList::EnterDir(const char *Dir,struct stat const &St)
{
   if (Visit(Dir,0,St) != 0)
      return false;

   dsFList::Directory D;
   D.Tag = dsFList::tDirStart;
   D.ModTime = St.st_mtime - IO->Header.Epoch;
   D.Permissions = St.st_mode & ~S_IFMT;
   D.Name = Dir;
   return EmitOwner(St,D.User,D.Group,D.Tag,dsFList::Directory::FlOwner) && 
      D.Write(*IO);    
}
									/*}}}*/
// GenFileList::LeaveDir - Called when a directory is left		/*{{{*/
// ---------------------------------------------------------------------
/* Don't do anything for now */
bool dsGenFileList::LeaveDir(const char *Dir)
{
   return true;
}
									/*}}}*/
// GenFileList::DirectoryMarker - Called when a dir is skipped		/*{{{*/
// ---------------------------------------------------------------------
/* This is used by the depth first ordering, when a dir is temporarily
   skipped over this function is called to emit a marker */
bool dsGenFileList::DirectoryMarker(const char *Dir,
				    struct stat const &St)
{
   dsFList::Directory D;
   D.Tag = dsFList::tDirMarker;
   D.ModTime = St.st_mtime - IO->Header.Epoch;
   D.Permissions = St.st_mode & ~S_IFMT;
   D.Name = Dir;
   return EmitOwner(St,D.User,D.Group,D.Tag,dsFList::Directory::FlOwner) && 
      D.Write(*IO);    
}
									/*}}}*/
// GenFileList::DoFile - This does all other items in a directory	/*{{{*/
// ---------------------------------------------------------------------
/* The different file types are emitted as perscribed by the file list
   document */
bool dsGenFileList::DoFile(const char *Dir,const char *File,
			   struct stat const &St)
{
   int Res = Visit(Dir,File,St);
   if (Res < 0)
      return false;
   if (Res > 0)
      return true;
   
   // Regular file
   if (S_ISREG(St.st_mode) != 0)
   {
      dsFList::NormalFile F;
      
      F.Tag = dsFList::tNormalFile;
      F.ModTime = St.st_mtime - IO->Header.Epoch;
      F.Permissions = St.st_mode & ~S_IFMT;
      F.Name = File;
      F.Size = St.st_size;

      if (EmitOwner(St,F.User,F.Group,F.Tag,dsFList::NormalFile::FlOwner) == false)
	 return false;
      
      // See if we need to emit rsync checksums
      if (NeedsRSync(Dir,File,F) == true)
      {
	 dsFList::RSyncChecksum Ck;
	 if (EmitRSync(Dir,File,St,F,Ck) == false)
	    return false;

	 // Write out the file record, the checksums and the end marker
	 return F.Write(*IO) && Ck.Write(*IO);
      }
      else
      {
	 if (EmitMD5(Dir,File,St,F.MD5,F.Tag,
		     dsFList::NormalFile::FlMD5) == false)
	    return false;
      
	 return F.Write(*IO);
      }      
   }
   
   // Directory
   if (S_ISDIR(St.st_mode) != 0)
   {
      dsFList::Directory D;
      D.Tag = dsFList::tDirectory;
      D.ModTime = St.st_mtime - IO->Header.Epoch;
      D.Permissions = St.st_mode & ~S_IFMT;
      D.Name = File;
      return EmitOwner(St,D.User,D.Group,D.Tag,dsFList::Directory::FlOwner) && 
	 D.Write(*IO);    
   }

   // Link
   if (S_ISLNK(St.st_mode) != 0)
   {
      dsFList::Symlink L;
      L.Tag = dsFList::tSymlink;
      L.ModTime = St.st_mtime - IO->Header.Epoch;
      L.Name = File;

      char Buf[1024];
      int Res = readlink(File,Buf,sizeof(Buf));
      if (Res <= 0)
	 return _error->Errno("readlink","Unable to read symbolic link");
      Buf[Res] = 0;
      L.To = Buf;

      return EmitOwner(St,L.User,L.Group,L.Tag,dsFList::Symlink::FlOwner) && 
	 L.Write(*IO);    
   }
   
   // Block special file
   if (S_ISCHR(St.st_mode) != 0 || S_ISBLK(St.st_mode) != 0 || 
       S_ISFIFO(St.st_mode) != 0)
   {
      dsFList::DeviceSpecial D;
      D.Tag = dsFList::tDeviceSpecial;
      D.ModTime = St.st_mtime - IO->Header.Epoch;
      D.Permissions = St.st_mode & ~S_IFMT;
      D.Dev = St.st_dev;
      D.Name = File;
      
      return EmitOwner(St,D.User,D.Group,D.Tag,dsFList::DeviceSpecial::FlOwner) && 
	 D.Write(*IO);
   }
   
   return _error->Error("File %s%s is not a known type",Dir,File);
}
									/*}}}*/
// GenFileList::EmitOwner - Set the entitiy ownership			/*{{{*/
// ---------------------------------------------------------------------
/* This emits the necessary UID/GID mapping records and sets the feilds
   in */
bool dsGenFileList::EmitOwner(struct stat const &St,unsigned long &UID,
			      unsigned long &GID,unsigned int Tag,
			      unsigned int Flag)
{
   if ((IO->Header.Flags[Tag] & Flag) != Flag)
      return true;
   
   return _error->Error("UID/GID storage is not supported yet");
}
									/*}}}*/
// GenFileList::EmitMd5 - Generate the md5 hash for the file		/*{{{*/
// ---------------------------------------------------------------------
/* This uses the MD5 class to generate the md5 hash for the entry. */
bool dsGenFileList::EmitMD5(const char *Dir,const char *File,
			    struct stat const &St,unsigned char MD5[16],
			    unsigned int Tag,unsigned int Flag)
{
   if ((IO->Header.Flags[Tag] & Flag) != Flag)
      return true;

   // Open the file
   MD5Summation Sum;
   FileFd Fd(File,FileFd::ReadOnly);
   if (_error->PendingError() == true)
      return _error->Error("MD5 generation failed for %s%s",Dir,File);

   if (Sum.AddFD(Fd.Fd(),Fd.Size()) == false)
      return _error->Error("MD5 generation failed for %s%s",Dir,File);
   
   Sum.Result().Value(MD5);
   
   return true;
}
									/*}}}*/
// GenFileList::EmitRSync - Emit a RSync checksum record		/*{{{*/
// ---------------------------------------------------------------------
/* This just generates the checksum into the memory structure. */
bool dsGenFileList::EmitRSync(const char *Dir,const char *File,
			      struct stat const &St,dsFList::NormalFile &F,
			      dsFList::RSyncChecksum &Ck)
{
   FileFd Fd(File,FileFd::ReadOnly);
   if (_error->PendingError() == true)
      return _error->Error("RSync Checksum generation failed for %s%s",Dir,File);
   
   if (GenerateRSync(Fd,Ck,F.MD5) == false)
      return _error->Error("RSync Checksum generation failed for %s%s",Dir,File);
   
   return true;
}
									/*}}}*/

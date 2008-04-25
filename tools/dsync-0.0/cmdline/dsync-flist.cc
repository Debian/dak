// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: dsync-flist.cc,v 1.27 1999/12/26 06:59:00 jgg Exp $
/* ######################################################################

   Dsync FileList is a tool to manipulate and generate the dsync file 
   listing
   
   Several usefull functions are provided, the most notable is to generate
   the file list and to dump it. There is also a function to compare the
   file list against a local directory tree.
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync-flist.h"
#endif 

#include "dsync-flist.h"
#include <dsync/cmndline.h>
#include <dsync/error.h>
#include <dsync/md5.h>
#include <dsync/strutl.h>

#include <config.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <utime.h>
#include <unistd.h>
#include <termios.h>
#include <signal.h>

#include <iostream>
using namespace std;

									/*}}}*/

// Externs								/*{{{*/
ostream c0out(cout.rdbuf());
ostream c1out(cout.rdbuf());
ostream c2out(cout.rdbuf());
ofstream devnull("/dev/null");
unsigned int ScreenWidth = 80;
									/*}}}*/

// Progress::Progress - Constructor					/*{{{*/
// ---------------------------------------------------------------------
/* */
Progress::Progress()
{
   Quiet = false;
   if (_config->FindI("quiet",0) > 0)
      Quiet = true;
   DirCount = 0;
   FileCount = 0;
   LinkCount = 0;
   Bytes = 0;
   CkSumBytes = 0;
   gettimeofday(&StartTime,0);
}
									/*}}}*/
// Progress::Done - Clear the progress meter				/*{{{*/
// ---------------------------------------------------------------------
/* */
void Progress::Done()
{
   if (Quiet == false)
      c0out << '\r' << BlankLine << '\r' << flush;
   BlankLine[0] = 0;
}
									/*}}}*/
// Progress::ElaspedTime - Return the time that has elapsed		/*{{{*/
// ---------------------------------------------------------------------
/* Computes the time difference with maximum accuracy */
double Progress::ElapsedTime()
{
   // Compute the CPS and elapsed time
   struct timeval Now;
   gettimeofday(&Now,0);

   return Now.tv_sec - StartTime.tv_sec + (Now.tv_usec - 
					   StartTime.tv_usec)/1000000.0;
}
									/*}}}*/
// Progress::Update - Update the meter					/*{{{*/
// ---------------------------------------------------------------------
/* */
void Progress::Update(const char *Directory)
{
   LastCount = DirCount+LinkCount+FileCount;
   
   if (Quiet == true)
      return;

   // Put the number of files and bytes at the end of the meter
   char S[1024];
   if (ScreenWidth > sizeof(S)-1)
      ScreenWidth = sizeof(S)-1;
   
   unsigned int Len = snprintf(S,sizeof(S),"|%lu %sb",
			       DirCount+LinkCount+FileCount,
			       SizeToStr(Bytes).c_str());
   
   memmove(S + (ScreenWidth - Len),S,Len+1);
   memset(S,' ',ScreenWidth - Len);
   
   // Put the directory name at the front, possibly shortened
   if (Directory == 0 || Directory[0] == 0)
      S[snprintf(S,sizeof(S),"<root>")] = ' ';
   else
   {
      // If the path is too long fix it and prefix it with '...'
      if (strlen(Directory) >= ScreenWidth - Len - 1)
      {
	 S[snprintf(S,sizeof(S),"%s",Directory + 
		    strlen(Directory) - ScreenWidth + Len + 1)] = ' ';
	 S[0] = '.'; S[1] = '.'; S[2] = '.';
      }
      else
	 S[snprintf(S,sizeof(S),"%s",Directory)] = ' ';
   }
   
   strcpy(LastLine,S);
   c0out << S << '\r' << flush;
   memset(BlankLine,' ',strlen(S));
   BlankLine[strlen(S)] = 0;
}
									/*}}}*/
// Progress::Stats - Show a statistics report				/*{{{*/
// ---------------------------------------------------------------------
/* */
void Progress::Stats(bool CkSum)
{
   // Display some interesting statistics
   double Elapsed = ElapsedTime();
   c1out << DirCount << " directories, " << FileCount <<
      " files and " << LinkCount << " links (" << 
      (DirCount+FileCount+LinkCount) << "). ";
   if (CkSum == true)
   {
      if (CkSumBytes == Bytes)
	 c1out << "Total Size is " << SizeToStr(Bytes) << "b. ";
      else
	 c1out << SizeToStr(CkSumBytes) << '/' <<
           SizeToStr(Bytes) << "b hashed.";
   }   
   else
      c1out << "Total Size is " << SizeToStr(Bytes) << "b. ";
      
   c1out << endl;
   c1out << "Elapsed time " <<  TimeToStr((long)Elapsed) <<
      " (" << SizeToStr((DirCount+FileCount+LinkCount)/Elapsed) <<
      " files/sec) ";
   if (CkSumBytes != 0)
      c1out << " (" << SizeToStr(CkSumBytes/Elapsed) << "b/s hash)";
   c1out << endl;
}
									/*}}}*/

// ListGenerator::ListGenerator - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
ListGenerator::ListGenerator()
{
   Act = !_config->FindB("noact",false);
   StripDepth = _config->FindI("FileList::CkSum-PathStrip",0);
   Verbose = false;
   if (_config->FindI("verbose",0) > 0)
      Verbose = true;
   DB = 0;
   DBIO = 0;

   // Set RSync checksum limits
   MinRSyncSize = _config->FindI("FileList::MinRSyncSize",0);
   if (MinRSyncSize == 0)
      MinRSyncSize = 1;
   if (_config->FindB("FileList::RSync-Hashes",false) == false)
       MinRSyncSize = 0;
       
   // Load the rsync filter
   if (RSyncFilter.LoadFilter(_config->Tree("FList::RSync-Filter")) == false)
      return;
       
   // Load the clean filter
   if (RemoveFilter.LoadFilter(_config->Tree("FList::Clean-Filter")) == false)
      return;
}
									/*}}}*/
// ListGenerator::~ListGenerator - Destructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
ListGenerator::~ListGenerator()
{
   delete DB;
   delete DBIO;
}
									/*}}}*/
// ListGenerator::Visit - Collect statistics about the tree		/*{{{*/
// ---------------------------------------------------------------------
/* */
int ListGenerator::Visit(const char *Directory,const char *File,
			 struct stat const &Stat)
{
   if (Prog.DirCount+Prog.LinkCount+Prog.FileCount - Prog.LastCount > 100 ||
       File == 0)
      Prog.Update(Directory);
   
   // Ignore directory enters
   if (File == 0)
      return 0;
   
   // Increment our counters
   if (S_ISDIR(Stat.st_mode) != 0)
      Prog.DirCount++;
   else
   {
      if (S_ISLNK(Stat.st_mode) != 0)
	 Prog.LinkCount++;
      else
	 Prog.FileCount++;
   }
   
   // Normal file
   if (S_ISREG(Stat.st_mode) != 0)
      Prog.Bytes += Stat.st_size;
   
   // Look for files to erase
   if (S_ISDIR(Stat.st_mode) == 0 &&
       RemoveFilter.Test(Directory,File) == false)
   {
      Prog.Hide();
      c1out << "Unlinking " << Directory << File << endl;
      Prog.Show();
      
      if (Act == true && unlink(File) != 0)
      {
	 _error->Errno("unlink","Failed to remove %s%s",Directory,File);
	 return -1;
      }
      
      return 1;
   }
   
   return 0;
}			 
									/*}}}*/
// ListGenerator::EmitMD5 - Perform md5 lookup caching			/*{{{*/
// ---------------------------------------------------------------------
/* This looks up the file in the cache to see if it is one we already 
   know the hash too */
bool ListGenerator::EmitMD5(const char *Dir,const char *File,
			    struct stat const &St,unsigned char MD5[16],
			    unsigned int Tag,unsigned int Flag)
{
   if ((IO->Header.Flags[Tag] & Flag) != Flag)
      return true;

   // Lookup the md5 in the old file list
   if (DB != 0 && (DBIO->Header.Flags[Tag] & Flag) == Flag)
   {
      // Do a lookup and make sure the timestamps match
      dsFList List;
      bool Hit = false;
      const char *iDir = Dir;
      unsigned int Strip = StripDepth;
      while (true)
      {	 
	 if (DB->Lookup(*DBIO,iDir,File,List) == true && List.Entity != 0)
	 {
	    if ((signed)(List.Entity->ModTime + List.Head.Epoch) == St.st_mtime)
	       Hit = true;	    
	    break;
	 }
	 
	 if (Strip == 0)
	    break;
	 
	 Strip--;
	 for (; *iDir != 0 && *iDir != '/'; iDir++);
	 if (*iDir == 0 || iDir[1] == 0)
	    break;
	 iDir++;
      }
	 
      if (Hit == true)
      {
	 /* Both hardlinks and normal files have md5s, also check that the
	    sizes match */
	 if (List.File != 0 && List.File->Size == (unsigned)St.st_size)
	 {
	    memcpy(MD5,List.File->MD5,sizeof(List.File->MD5));
	    return true;
	 }
      }      
   }
   
   Prog.CkSumBytes += St.st_size;
   
   if (Verbose == true)
   {
      Prog.Hide();
      c1out << "MD5 " << Dir << File << endl;
      Prog.Show();
   }
   
   return dsGenFileList::EmitMD5(Dir,File,St,MD5,Tag,Flag);
}
									/*}}}*/
// ListGenerator::NeedsRSync - Check if a file is rsyncable		/*{{{*/
// ---------------------------------------------------------------------
/* This checks the rsync filter list and the rsync size limit*/
bool ListGenerator::NeedsRSync(const char *Dir,const char *File,
			       dsFList::NormalFile &F)
{
   if (MinRSyncSize == 0)
      return false;
   
   if (F.Size <= MinRSyncSize)
      return false;
   
   if (RSyncFilter.Test(Dir,File) == false)
      return false;
   
   /* Add it to the counters, EmitMD5 will not be called if rsync checksums
      are being built. */
   Prog.CkSumBytes += F.Size;  
   if (Verbose == true)
   {
      Prog.Hide();
      c1out << "RSYNC " << Dir << File << endl;
      Prog.Show();
   }
   
   return true;
}
									/*}}}*/

// Compare::Compare - Constructor					/*{{{*/
// ---------------------------------------------------------------------
/* */
Compare::Compare()
{
   Verbose = false;
   if (_config->FindI("verbose",0) > 0)
      Verbose = true;
   Act = !_config->FindB("noact",false);
   DoDelete = _config->FindB("delete",false);
}
									/*}}}*/
// Compare::Visit - Collect statistics about the tree			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool Compare::Visit(dsFList &List,string Dir)
{
   if (Prog.DirCount+Prog.LinkCount+Prog.FileCount - Prog.LastCount > 100 ||
       List.Tag == dsFList::tDirStart)
      Prog.Update(Dir.c_str());
   
   // Increment our counters
   if (List.Tag == dsFList::tDirectory)
      Prog.DirCount++;
   else
   {
      if (List.Tag == dsFList::tSymlink)
	 Prog.LinkCount++;

      if (List.Tag == dsFList::tNormalFile || 
	  List.Tag == dsFList::tHardLink ||
	  List.Tag == dsFList::tDeviceSpecial)
	 Prog.FileCount++;
   }
   
   // Normal file
   if (List.File != 0)
      Prog.Bytes += List.File->Size;
   
   return true;
}
									/*}}}*/
// Compare::PrintPath - Print out a path string				/*{{{*/
// ---------------------------------------------------------------------
/* This handles the absolute paths that can occure while processing */
void Compare::PrintPath(ostream &out,string Dir,string Name)
{
   if (Name[0] != '/')
      out << Dir << Name << endl;
   else
      out << string(Name,Base.length()) << endl;
}
									/*}}}*/

// LookupPath - Find a full path within the database			/*{{{*/
// ---------------------------------------------------------------------
/* This does the necessary path simplification and symlink resolution
   to locate the path safely. The file must exist locally inorder to 
   resolve the local symlinks. */
bool LookupPath(const char *Path,dsFList &List,dsFileListDB &DB,
		dsFList::IO &IO)
{
   char Buffer[2024];
   strcpy(Buffer,Path);
      
   if (SimplifyPath(Buffer) == false || 
       ResolveLink(Buffer,sizeof(Buffer)) == false)
      return false;
   
   // Strip off the final component name
   char *I = Buffer + strlen(Buffer);
   for (; I != Buffer && (*I == '/' || *I == 0); I--);
   for (; I != Buffer && *I != '/'; I--);
   if (I != Buffer)
   {
      memmove(I+1,I,strlen(I) + 1);
      I++;
      *I = 0;
      I++;
      if (DB.Lookup(IO,Buffer,I,List) == false)
	 return false;
   }
   else
   {
      if (DB.Lookup(IO,"",I,List) == false)
	 return false;
   }
   
   return true;
}
									/*}}}*/
// PrintMD5 - Prints the MD5 of a file in the form similar to md5sum	/*{{{*/
// ---------------------------------------------------------------------
/* */
void PrintMD5(dsFList &List,const char *Dir,const char *File = 0)
{
   if (List.File == 0 || 
       List.Head.Flags[List.Tag] & dsFList::NormalFile::FlMD5 == 0)
      return;

   char S[16*2+1];
   for (unsigned int I = 0; I != 16; I++)
      sprintf(S+2*I,"%02x",List.File->MD5[I]);
   S[16*2] = 0;
   if (File == 0)
      cout << S << "  " << Dir << List.File->Name << endl;
   else
      cout << S << "  " << File << endl;
}
									/*}}}*/

// DoGenerate - The Generate Command					/*{{{*/
// ---------------------------------------------------------------------
/* */
bool DoGenerate(CommandLine &CmdL)
{
   ListGenerator Gen;
   if (_error->PendingError() == true)
      return false;
   
   // Load the filter list
   if (Gen.Filter.LoadFilter(_config->Tree("FileList::Filter")) == false)
      return false;

   // Load the delay filter list
   if (Gen.PreferFilter.LoadFilter(_config->Tree("FileList::Prefer-Filter")) == false)
      return false;
   
   // Determine the ordering to use
   string Ord = _config->Find("FileList::Order","tree");
   if (stringcasecmp(Ord,"tree") == 0)
      Gen.Type = dsGenFileList::Tree;
   else
   {
      if (stringcasecmp(Ord,"breadth") == 0)
	 Gen.Type = dsGenFileList::Breadth;
      else
      {
         if (stringcasecmp(Ord,"depth") == 0)
	    Gen.Type = dsGenFileList::Depth;
	 else
	    return _error->Error("Invalid ordering %s, must be tree, breadth or detph",Ord.c_str());
      }      
   }

   if (CmdL.FileList[1] == 0)
      return _error->Error("You must specify a file name");
   
   string List = CmdL.FileList[1];
   
   // Open the original file to pull cached Check Sums out of
   if (FileExists(List) == true && 
       _config->FindB("FileList::MD5-Hashes",false) == true)
   {
      Gen.DBIO = new dsMMapIO(List);
      if (_error->PendingError() == true)
	 return false;
      Gen.DB = new dsFileListDB;
      if (Gen.DB->Generate(*Gen.DBIO) == false)
	 return false;
   }   

   // Sub scope to close the file
   {      
      FdIO IO(List + ".new",FileFd::WriteEmpty);
      
      // Set the flags for the list
      if (_config->FindB("FileList::MD5-Hashes",false) == true)
      {
	 IO.Header.Flags[dsFList::tNormalFile] |= dsFList::NormalFile::FlMD5;
	 IO.Header.Flags[dsFList::tHardLink] |= dsFList::HardLink::FlMD5;
      }
      if (_config->FindB("FileList::Permissions",false) == true)
      {
	 IO.Header.Flags[dsFList::tDirectory] |= dsFList::Directory::FlPerm;
	 IO.Header.Flags[dsFList::tNormalFile] |= dsFList::NormalFile::FlPerm;
	 IO.Header.Flags[dsFList::tHardLink] |= dsFList::HardLink::FlPerm;
      }
      if (_config->FindB("FileList::Ownership",false) == true)
      {
	 IO.Header.Flags[dsFList::tDirectory] |= dsFList::Directory::FlOwner;
	 IO.Header.Flags[dsFList::tNormalFile] |= dsFList::NormalFile::FlOwner;
	 IO.Header.Flags[dsFList::tSymlink] |= dsFList::Symlink::FlOwner;
	 IO.Header.Flags[dsFList::tDeviceSpecial] |= dsFList::DeviceSpecial::FlOwner;
	 IO.Header.Flags[dsFList::tHardLink] |= dsFList::HardLink::FlOwner;
      }
      
      if (Gen.Go("./",IO) == false)
	 return false;
      Gen.Prog.Done();
      Gen.Prog.Stats(_config->FindB("FileList::MD5-Hashes",false));
      
      delete Gen.DB;
      Gen.DB = 0;
      delete Gen.DBIO;
      Gen.DBIO = 0;
   }
   
   // Just in case :>
   if (_error->PendingError() == true)
      return false;
   
   // Swap files
   bool OldExists = FileExists(List);
   if (OldExists == true && rename(List.c_str(),(List + "~").c_str()) != 0)
      return _error->Errno("rename","Unable to rename %s to %s~",List.c_str(),List.c_str());
   if (rename((List + ".new").c_str(),List.c_str()) != 0)
      return _error->Errno("rename","Unable to rename %s.new to %s",List.c_str(),List.c_str());
   if (OldExists == true && unlink((List + "~").c_str()) != 0)
      return _error->Errno("unlink","Unable to unlink %s~",List.c_str());
   
   return true;
}
									/*}}}*/
// DoDump - Dump the contents of a file list				/*{{{*/
// ---------------------------------------------------------------------
/* This displays a short one line dump of each record in the file */
bool DoDump(CommandLine &CmdL)
{
   if (CmdL.FileList[1] == 0)
      return _error->Error("You must specify a file name");
   
   // Open the file
   dsMMapIO IO(CmdL.FileList[1]);
   if (_error->PendingError() == true)
      return false;
   
   dsFList List;
   unsigned long CountDir = 0;
   unsigned long CountFile = 0;
   unsigned long CountLink = 0;
   unsigned long CountLinkReal = 0;
   unsigned long NumFiles = 0;
   unsigned long NumDirs = 0;
   unsigned long NumLinks = 0;
   double Bytes = 0;
   
   while (List.Step(IO) == true)
   {
      if (List.Print(cout) == false)
	 return false;

      switch (List.Tag)
      {
	 case dsFList::tDirMarker:
	 case dsFList::tDirStart:
	 case dsFList::tDirectory:
	 {
	    CountDir += List.Dir.Name.length();
	    if (List.Tag == dsFList::tDirectory)
	       NumDirs++;
	    break;
	 }

	 case dsFList::tHardLink:
	 case dsFList::tNormalFile:
	 {
	    CountFile += List.File->Name.length();
	    NumFiles++;
	    Bytes += List.File->Size;
	    break;
	 }
	 
	 case dsFList::tSymlink:
	 {
	    CountFile += List.SLink.Name.length();
	    CountLink += List.SLink.To.length();
	    
	    unsigned int Tmp = List.SLink.To.length();
	    if ((List.SLink.Compress & (1<<7)) == (1<<7))
	       Tmp -= List.SLink.Name.length();
	    Tmp -= List.SLink.Compress & 0x7F;
	    CountLinkReal += Tmp;
	    NumLinks++;
	    break;
	 }
      }
      if (List.Tag == dsFList::tTrailer)
	 break;
   }
   cout << "String Sizes: Dirs=" << CountDir << " Files=" << CountFile << 
      " Links=" << CountLink << " (" << CountLinkReal << ")";
   cout << " Total=" << CountDir+CountFile+CountLink << endl;
   cout << "Entries: Dirs=" << NumDirs << " Files=" << NumFiles << 
      " Links=" << NumLinks << " Total=" << NumDirs+NumFiles+NumLinks << endl;
   cout << "Totals " << SizeToStr(Bytes) << "b." << endl;
   
   return true;
}
									/*}}}*/
// DoMkHardLinks - Generate hardlinks for duplicated files		/*{{{*/
// ---------------------------------------------------------------------
/* This scans the archive for any duplicated files, it uses the MD5 of each
   file and searches a map for another match then links the two */
struct Md5Cmp
{
   unsigned char MD5[16];
   int operator <(const Md5Cmp &rhs) const {return memcmp(MD5,rhs.MD5,sizeof(MD5)) < 0;};
   int operator <=(const Md5Cmp &rhs) const {return memcmp(MD5,rhs.MD5,sizeof(MD5)) <= 0;};
   int operator >=(const Md5Cmp &rhs) const {return memcmp(MD5,rhs.MD5,sizeof(MD5)) >= 0;};
   int operator >(const Md5Cmp &rhs) const {return memcmp(MD5,rhs.MD5,sizeof(MD5)) > 0;};
   int operator ==(const Md5Cmp &rhs) const {return memcmp(MD5,rhs.MD5,sizeof(MD5)) == 0;};
   
   Md5Cmp(unsigned char Md[16]) {memcpy(MD5,Md,sizeof(MD5));};
};

struct Location
{
   string Dir;
   string File;
   
   Location() {};
   Location(string Dir,string File) : Dir(Dir), File(File) {};
};

bool DoMkHardLinks(CommandLine &CmdL)
{
   if (CmdL.FileList[1] == 0)
      return _error->Error("You must specify a file name");
   
   // Open the file
   dsMMapIO IO(CmdL.FileList[1]);
   if (_error->PendingError() == true)
      return false;

   dsFList List;
   if (List.Step(IO) == false || List.Tag != dsFList::tHeader)
      return _error->Error("Unable to read header");

   // Make sure we have hashes
   if ((IO.Header.Flags[dsFList::tNormalFile] & 
	dsFList::NormalFile::FlMD5) == 0 ||
       (IO.Header.Flags[dsFList::tHardLink] & 
	dsFList::HardLink::FlMD5) == 0)
      return _error->Error("The file list must contain MD5 hashes");
   
   string LastDir;
   double Savings = 0;
   unsigned long Hits = 0;
   bool Act = !_config->FindB("noact",false);   
   map<Md5Cmp,Location> Map;   
   while (List.Step(IO) == true)
   {
      // Entering a new directory, just store it..
      if (List.Tag == dsFList::tDirStart)
      {
	 LastDir = List.Dir.Name;
	 continue;
      }

      /* Handle normal file entities. Pre-existing hard links we treat
         exactly like a normal file, if two hard link chains are identical
	 one will be destroyed and its items placed on the other 
	 automatcially */
      if (List.File != 0)
      {
	 map<Md5Cmp,Location>::const_iterator I = Map.find(Md5Cmp(List.File->MD5));
	 if (I == Map.end())
	 {
	    Map[Md5Cmp(List.File->MD5)] = Location(LastDir,List.File->Name);
	    continue;
	 }

	 // Compute full file names for both
	 string FileA = (*I).second.Dir + (*I).second.File;
	 struct stat StA;
	 string FileB = LastDir + List.File->Name;
	 struct stat StB;
	 
	 // Stat them
	 if (lstat(FileA.c_str(),&StA) != 0)
	 {
	    _error->Warning("Unable to stat %s",FileA.c_str());
	    continue;
	 }	 
	 if (lstat(FileB.c_str(),&StB) != 0)
	 {
	    _error->Warning("Unable to stat %s",FileB.c_str());
	    continue;
	 }
	 
	 // Verify they are on the same filesystem
	 if (StA.st_dev != StB.st_dev || StA.st_size != StB.st_size)
	    continue;
	 
	 // And not merged..
	 if (StA.st_ino == StB.st_ino)
	    continue;
	 
	 c1out << "Dup " << FileA << endl;
         c1out << "    " << FileB << endl;
      
	 // Relink the file and copy the mod time from the oldest one.
	 if (Act == true)
	 {
	    if (unlink(FileB.c_str()) != 0)
	       return _error->Errno("unlink","Failed to unlink %s",FileB.c_str());
	    if (link(FileA.c_str(),FileB.c_str()) != 0)
	       return _error->Errno("link","Failed to link %s to %s",FileA.c_str(),FileB.c_str());
	    if (StB.st_mtime > StA.st_mtime)
	    {
	       struct utimbuf Time;
	       Time.actime = Time.modtime = StB.st_mtime;
	       if (utime(FileB.c_str(),&Time) != 0)
		  _error->Warning("Unable to set mod time for %s",FileB.c_str());	       
	    }
	 }
	 
	 // Counters
	 Savings += List.File->Size;
	 Hits++;
	 
	 continue;
      }
      
      if (List.Tag == dsFList::tTrailer)
	 break;
   }
   
   cout << "Total space saved by merging " << 
      SizeToStr(Savings) << "b. " << Hits << " files affected." << endl;
   return true;
}
									/*}}}*/
// DoLookup - Lookup a single file in the listing			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool DoLookup(CommandLine &CmdL)
{
   if (CmdL.FileSize() < 4)
      return _error->Error("You must specify a file name, directory name and a entry");
   
   // Open the file
   dsMMapIO IO(CmdL.FileList[1]);
   if (_error->PendingError() == true)
      return false;

   // Index it
   dsFileListDB DB;
   if (DB.Generate(IO) == false)
      return false;

   dsFList List;
   if (DB.Lookup(IO,CmdL.FileList[2],CmdL.FileList[3],List) == false)
      return _error->Error("Unable to locate item");
   List.Print(cout);
   return true;
}
									/*}}}*/
// DoMD5Cache - Lookup a stream of files in the listing			/*{{{*/
// ---------------------------------------------------------------------
/* This takes a list of files names and prints out their MD5s, if possible
   data is used from the cache to save IO */
bool DoMD5Cache(CommandLine &CmdL)
{
   struct timeval Start;
   gettimeofday(&Start,0);
   
   if (CmdL.FileList[1] == 0)
      return _error->Error("You must specify a file name");
   
   // Open the file
   dsMMapIO IO(CmdL.FileList[1]);
   if (_error->PendingError() == true)
      return false;

   dsFList List;
   if (List.Step(IO) == false || List.Tag != dsFList::tHeader)
      return _error->Error("Unable to read header");
   
   // Make sure we have hashes
   if ((IO.Header.Flags[dsFList::tNormalFile] & 
	dsFList::NormalFile::FlMD5) == 0 ||
       (IO.Header.Flags[dsFList::tHardLink] & 
	dsFList::HardLink::FlMD5) == 0)
      return _error->Error("The file list must contain MD5 hashes");

   // Index it
   dsFileListDB DB;
   if (DB.Generate(IO) == false)
      return false;

   // Counters
   double Bytes = 0;
   double MD5Bytes = 0;
   unsigned long Files = 0;
   unsigned long Errors = 0;

   while (!cin == false)
   {
      char Buf2[200];
      cin.getline(Buf2,sizeof(Buf2));
      if (Buf2[0] == 0)
	 continue;
      Files++;
      
      // Stat the file
      struct stat St;
      if (stat(Buf2,&St) != 0)
      {
	 cout << "<ERROR> " << Buf2 << "(stat)" << endl;
	 Errors++;
	 continue;
      }
            
      // Lookup in the cache and make sure the file has not changed
      if (LookupPath(Buf2,List,DB,IO) == false ||
	  (signed)(List.Entity->ModTime + List.Head.Epoch) != St.st_mtime ||
	  (List.File != 0 && List.File->Size != (unsigned)St.st_size))
      {
	 _error->DumpErrors();
	 
	 // Open the file and hash it
	 MD5Summation Sum;
	 FileFd Fd(Buf2,FileFd::ReadOnly);
	 if (_error->PendingError() == true)
	 {
	    cout << "<ERROR> " << Buf2 << "(open)" << endl;
	    continue;
	 }
	 
	 if (Sum.AddFD(Fd.Fd(),Fd.Size()) == false)
	 {
	    cout << "<ERROR> " << Buf2 << "(md5)" << endl;
	    continue;
	 }
	 	 
	 // Store the new hash
	 List.Tag = dsFList::tNormalFile;
	 Sum.Result().Value(List.File->MD5);
	 List.File->Size = (unsigned)St.st_size;
	 
	 MD5Bytes += List.File->Size;
      }

      PrintMD5(List,0,Buf2);
      Bytes += List.File->Size;
   }

   // Print out a summary
   struct timeval Now;
   gettimeofday(&Now,0);
   double Delta = Now.tv_sec - Start.tv_sec + (Now.tv_usec - Start.tv_usec)/1000000.0;
   cerr << Files << " files, " << SizeToStr(MD5Bytes) << "/" << 
      SizeToStr(Bytes) << " MD5'd, " << TimeToStr((unsigned)Delta) << endl;;
      
   return true;
}
									/*}}}*/
// DoMD5Dump - Dump the md5 list					/*{{{*/
// ---------------------------------------------------------------------
/* This displays a short one line dump of each record in the file */
bool DoMD5Dump(CommandLine &CmdL)
{
   if (CmdL.FileList[1] == 0)
      return _error->Error("You must specify a file name");
   
   // Open the file
   dsMMapIO IO(CmdL.FileList[1]);
   if (_error->PendingError() == true)
      return false;
   
   dsFList List;
   if (List.Step(IO) == false || List.Tag != dsFList::tHeader)
      return _error->Error("Unable to read header");
   
   // Make sure we have hashes
   if ((IO.Header.Flags[dsFList::tNormalFile] & 
	dsFList::NormalFile::FlMD5) == 0 ||
       (IO.Header.Flags[dsFList::tHardLink] & 
	dsFList::HardLink::FlMD5) == 0)
      return _error->Error("The file list must contain MD5 hashes");
   
   string Dir;
   while (List.Step(IO) == true)
   {
      if (List.Tag == dsFList::tDirStart)
      {
	 Dir = List.Dir.Name;
	 continue;
      }
      
      PrintMD5(List,Dir.c_str());
      
      if (List.Tag == dsFList::tTrailer)
	 break;
   }   
   return true;
}
									/*}}}*/
// DoVerify - Verify the local tree against a file list			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool DoVerify(CommandLine &CmdL)
{
   if (CmdL.FileList[1] == 0)
      return _error->Error("You must specify a file name");
   
   // Open the file
   dsMMapIO IO(CmdL.FileList[1]);
   if (_error->PendingError() == true)
      return false;
   
   /* Set the hashing type, we can either do a full verify or only a date
      check verify */
   Compare Comp;
   if (_config->FindB("FileList::MD5-Hashes",false) == true)
      Comp.HashLevel = dsDirCompare::Md5Always;
   else
      Comp.HashLevel = dsDirCompare::Md5Date;
   
   // Scan the file list
   if (Comp.Process(".",IO) == false)
      return false;
   Comp.Prog.Done();
   
   // Report stats
   Comp.Prog.Stats((IO.Header.Flags[dsFList::tNormalFile] & dsFList::NormalFile::FlMD5) != 0 ||
		   (IO.Header.Flags[dsFList::tHardLink] & dsFList::HardLink::FlMD5) != 0);
   
   return true;
}
									/*}}}*/
// SigWinch - Window size change signal handler				/*{{{*/
// ---------------------------------------------------------------------
/* */
void SigWinch(int)
{
   // Riped from GNU ls
#ifdef TIOCGWINSZ
   struct winsize ws;
  
   if (ioctl(1, TIOCGWINSZ, &ws) != -1 && ws.ws_col >= 5)
      ScreenWidth = ws.ws_col - 1;
   if (ScreenWidth > 250)
      ScreenWidth = 250;
#endif
}
									/*}}}*/
// ShowHelp - Show the help screen					/*{{{*/
// ---------------------------------------------------------------------
/* */
bool ShowHelp(CommandLine &CmdL)
{
   cout << PACKAGE << ' ' << VERSION << " for " << ARCHITECTURE <<
      " compiled on " << __DATE__ << "  " << __TIME__ << endl;
   
   cout << 
      "Usage: dsync-flist [options] command [file]\n"
      "\n"
      "dsync-flist is a tool for manipulating dsync binary file lists.\n"
      "It can generate the lists and check them against a tree.\n"
      "\n"
      "Commands:\n"
      "   generate - Build a file list\n"
      "   help - This help text\n"
      "   dump - Display the contents of the list\n"
      "   md5sums - Print out 'indices' file, suitable for use with md5sum\n"
      "   md5cache - Print out md5sums of the files given on stdin\n"
      "   link-dups - Look for duplicate files\n"
      "   lookup - Display a single file record\n"
      "   verify - Compare the file list against the local directory\n"
      "\n"   
      "Options:\n"
      "  -h  This help text.\n"
      "  -q  Loggable output - no progress indicator\n"
      "  -qq No output except for errors\n"
      "  -i=? Include pattern\n"
      "  -e=? Exclude pattern\n"
      "  -c=? Read this configuration file\n"
      "  -o=? Set an arbitary configuration option, ie -o dir::cache=/tmp\n"
      "See the dsync-flist(1) and dsync.conf(5) manual\n"
      "pages for more information." << endl;
   return 100;
}
									/*}}}*/

int main(int argc, const char *argv[])
{
   CommandLine::Args Args[] = {
      {'h',"help","help",0},
      {'q',"quiet","quiet",CommandLine::IntLevel},
      {'q',"silent","quiet",CommandLine::IntLevel},
      {'i',"include","FileList::Filter:: + ",CommandLine::HasArg},
      {'e',"exclude","FileList::Filter:: - ",CommandLine::HasArg},
      {'n',"no-act","noact",0},
      {'v',"verbose","verbose",CommandLine::IntLevel},
      {0,"delete","delete",0},
      {0,"prefer-include","FileList::Prefer-Filter:: + ",CommandLine::HasArg},
      {0,"prefer-exclude","FileList::Prefer-Filter:: - ",CommandLine::HasArg},
      {0,"pi","FileList::Prefer-Filter:: + ",CommandLine::HasArg},
      {0,"pe","FileList::Prefer-Filter:: - ",CommandLine::HasArg},
      {0,"clean-include","FList::Clean-Filter:: + ",CommandLine::HasArg},
      {0,"clean-exclude","FList::Clean-Filter:: - ",CommandLine::HasArg},
      {0,"ci","FList::Clean-Filter:: + ",CommandLine::HasArg},
      {0,"ce","FList::Clean-Filter:: - ",CommandLine::HasArg},
      {0,"rsync-include","FList::RSync-Filter:: + ",CommandLine::HasArg},
      {0,"rsync-exclude","FList::RSync-Filter:: - ",CommandLine::HasArg},
      {0,"ri","FList::RSync-Filter:: + ",CommandLine::HasArg},
      {0,"re","FList::RSync-Filter:: - ",CommandLine::HasArg},
      {0,"md5","FileList::MD5-Hashes",0},
      {0,"rsync","FileList::RSync-Hashes",0},
      {0,"rsync-min","FileList::MinRSyncSize",CommandLine::HasArg},
      {0,"perm","FileList::Permissions",0},
      {0,"owner","FileList::Ownership",0},
      {0,"order","FileList::Order",CommandLine::HasArg},
      {'c',"config-file",0,CommandLine::ConfigFile},
      {'o',"option",0,CommandLine::ArbItem},
      {0,0,0,0}};
   CommandLine::Dispatch Cmds[] = {{"generate",&DoGenerate},
                                   {"help",&ShowHelp},
                                   {"dump",&DoDump},
                                   {"link-dups",&DoMkHardLinks},
                                   {"md5sums",&DoMD5Dump},
                                   {"md5cache",&DoMD5Cache},
                                   {"lookup",&DoLookup},
                                   {"verify",&DoVerify},
                                   {0,0}};
   CommandLine CmdL(Args,_config);
   if (CmdL.Parse(argc,argv) == false)
   {
      _error->DumpErrors();
      return 100;
   }
   
   // See if the help should be shown
   if (_config->FindB("help") == true ||
       CmdL.FileSize() == 0)
      return ShowHelp(CmdL);   

   // Setup the output streams
/*   c0out.rdbuf(cout.rdbuf());
   c1out.rdbuf(cout.rdbuf());
   c2out.rdbuf(cout.rdbuf()); */
   if (_config->FindI("quiet",0) > 0)
      c0out.rdbuf(devnull.rdbuf());
   if (_config->FindI("quiet",0) > 1)
      c1out.rdbuf(devnull.rdbuf());

   // Setup the signals
   signal(SIGWINCH,SigWinch);
   SigWinch(0);
   
   // Match the operation
   CmdL.DispatchArg(Cmds);
   
   // Print any errors or warnings found during parsing
   if (_error->empty() == false)
   {
      
      bool Errors = _error->PendingError();
      _error->DumpErrors();
      return Errors == true?100:0;
   }
         
   return 0; 
}

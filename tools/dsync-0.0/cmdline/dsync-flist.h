// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: dsync-flist.h,v 1.5 1999/12/26 06:59:00 jgg Exp $
/* ######################################################################
   
   Some header declarations..
   
   ##################################################################### */
									/*}}}*/
#ifndef DSYNC_FLIST_H
#define DSYNC_FLIST_H

#ifdef __GNUG__
#pragma interface "dsync-flist.h"
#endif 

#include <dsync/genfilelist.h>
#include <dsync/fileutl.h>
#include <dsync/filelistdb.h>
#include <dsync/compare.h>

#include <sys/time.h>
#include <iostream>
#include <fstream>
using namespace std;

extern ostream c0out;
extern ostream c1out;
extern ostream c2out;
extern ofstream devnull;
extern unsigned int ScreenWidth;

class FdIO : public dsFList::IO
{
   FileFd Fd;
   public:
   
   virtual bool Read(void *Buf,unsigned long Len) {return Fd.Read(Buf,Len);};
   virtual bool Write(const void *Buf,unsigned long Len) {return Fd.Write(Buf,Len);};
   virtual bool Seek(unsigned long Bytes) {return Fd.Seek(Bytes);};
   virtual unsigned long Tell() {return Fd.Tell();};
   
   FdIO(string File,FileFd::OpenMode Mode) : Fd(File,Mode) {};
};

class Progress
{
   bool Quiet;   
   
   char LastLine[300];
   char BlankLine[300];
   
   public:
   
   // Counters
   unsigned long DirCount;
   unsigned long FileCount;
   unsigned long LinkCount;
   unsigned long LastCount;
   double Bytes;      
   double CkSumBytes;
   struct timeval StartTime;

   double ElapsedTime();
   void Done();
   void Update(const char *Dir);
   void Stats(bool Md5);
   
   inline void Hide() 
   {
      if (Quiet == false)
	 c0out << '\r' << BlankLine << '\r';
   };
   inline void Show()
   {
      if (Quiet == false)
	 c0out << LastLine << '\r' << flush;
   };

   Progress();
   ~Progress() {Done();};
};

class ListGenerator : public dsGenFileList
{
   protected:
   bool Act;
   bool Verbose;
   unsigned long MinRSyncSize;
   unsigned int StripDepth;
   
   virtual int Visit(const char *Directory,const char *File,
		     struct stat const &Stat);
   virtual bool EmitMD5(const char *Dir,const char *File,
			struct stat const &St,unsigned char MD5[16],
			unsigned int Tag,unsigned int Flag);
   virtual bool NeedsRSync(const char *Dir,const char *File,
			   dsFList::NormalFile &F);
   
   public:

   // Md5 Cache
   dsFileListDB *DB;
   dsMMapIO *DBIO;   
   Progress Prog;
   
   dsFileFilter RemoveFilter;
   dsFileFilter RSyncFilter;
   
   ListGenerator();
   ~ListGenerator();
};

class Compare : public dsDirCorrect
{
   protected:
   
   bool Verbose;
   bool Act;
   bool DoDelete;
   
   virtual bool Visit(dsFList &List,string Dir);
   void PrintPath(ostream &out,string Dir,string Name);
   
   // Display status information
   virtual bool GetNew(dsFList &List,string Dir) 
   {
      Prog.Hide();
      c1out << "N ";
      PrintPath(c1out,Dir,List.Entity->Name);
      Prog.Show();
      return !Act || dsDirCorrect::GetNew(List,Dir);
   };
   virtual bool Delete(string Dir,const char *Name,bool Now = false) 
   {
      Prog.Hide();
      c1out << "D ";
      PrintPath(c1out,Dir,Name);
      Prog.Show();
      return !Act || !DoDelete || dsDirCorrect::Delete(Dir,Name);
   };
   virtual bool GetChanged(dsFList &List,string Dir)
   {
      Prog.Hide();
      c1out << "C ";
      PrintPath(c1out,Dir,List.Entity->Name);
      Prog.Show();
      return !Act || dsDirCorrect::GetChanged(List,Dir);
   };
   virtual bool SetTime(dsFList &List,string Dir)
   {
      if (Verbose == false)
	 return !Act || dsDirCorrect::SetTime(List,Dir);
      
      Prog.Hide();
      c1out << "T ";
      PrintPath(c1out,Dir,List.Entity->Name);
      Prog.Show();
      return !Act || dsDirCorrect::SetTime(List,Dir);
   };
   virtual bool SetPerm(dsFList &List,string Dir)
   {
      if (Verbose == false)
	 return !Act || dsDirCorrect::SetPerm(List,Dir);
      Prog.Hide();
      c1out << "P ";
      PrintPath(c1out,Dir,List.Entity->Name);
      Prog.Show();
      return !Act || dsDirCorrect::SetPerm(List,Dir);
   };
   virtual bool SetOwners(dsFList &List,string Dir)
   {
      if (Verbose == false)
	 return !Act || dsDirCorrect::SetOwners(List,Dir);
      Prog.Hide();
      c1out << "O ";
      PrintPath(c1out,Dir,List.Entity->Name);
      Prog.Show();
      return !Act || dsDirCorrect::SetOwners(List,Dir);
   };
   virtual bool CheckHash(dsFList &List,string Dir,unsigned char MD5[16])
   {
      Prog.CkSumBytes += List.File->Size;
      
      if (Verbose == true)
      {
	 Prog.Hide();
	 c1out << "H ";
	 PrintPath(c1out,Dir,List.Entity->Name);
	 Prog.Show();
      }      
      return dsDirCompare::CheckHash(List,Dir,MD5);
   }
      
   public:

   Progress Prog;
   
   Compare();
};

// Path utilities
bool SimplifyPath(char *Buffer);
bool ResolveLink(char *Buffer,unsigned long Max);

#endif

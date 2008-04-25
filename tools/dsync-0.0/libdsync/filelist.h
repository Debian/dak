// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: filelist.h,v 1.10 1999/12/26 06:59:00 jgg Exp $
/* ######################################################################
   
   File List structures
   
   These structures represent the uncompacted binary records from the
   file list file. Functions are provided to compact and decompact these
   structures for reading and writing.

   The dsFList class can be instantiated to get get a general 'all records'
   storage. It also has a member to read the next record from the IO and
   to print out a record summary.
   
   Be sure to read filelist.sgml which contains the precise meaning of 
   the feilds and the compaction technique used.

   ##################################################################### */
									/*}}}*/
#ifndef DSYNC_FILELIST
#define DSYNC_FILELIST

#ifdef __GNUG__
#pragma interface "dsync/filelist.h"
#endif 

#include <string>
using namespace std;

class dsFList
{
   public:
      
   class IO;

   struct Header
   {
      unsigned long Tag;
      unsigned long Signature;
      unsigned long MajorVersion;
      unsigned long MinorVersion;
      unsigned long Epoch;
      
      unsigned long FlagCount;
      unsigned long Flags[15];

      bool Read(IO &IO);
      bool Write(IO &IO);
      
      Header();
   };
   
   struct DirEntity
   {
      unsigned long Tag;
      signed long ModTime;
      unsigned long Permissions;
      unsigned long User;
      unsigned long Group;
      string Name;

      enum EntFlags {FlPerm = (1<<0), FlOwner = (1<<1)};
      
      /* You know what? egcs-2.91.60 will not call the destructor for Name
         if this in not here. I can't reproduce this in a simpler context
         either. - Jgg [time passes] serious egcs bug, it was mislinking
         the string classes :< */
      ~DirEntity() {};
   };
   
   struct Directory : public DirEntity
   {      
      bool Read(IO &IO);
      bool Write(IO &IO);
   };
   
   struct NormalFile : public DirEntity
   {
      unsigned long Size;
      unsigned char MD5[16];
      
      enum Flags {FlMD5 = (1<<2)};
      
      bool Read(IO &IO);
      bool Write(IO &IO);      
   };
   
   struct Symlink : public DirEntity
   {
      unsigned long Compress;
      string To;
      
      bool Read(IO &IO);
      bool Write(IO &IO);
   };
   
   struct DeviceSpecial : public DirEntity
   {
      unsigned long Dev;
      
      bool Read(IO &IO);
      bool Write(IO &IO);
   };
   
   struct Filter
   {
      unsigned long Tag;
      unsigned long Type;
      string Pattern;
      
      enum Types {Include=1, Exclude=2};
      
      bool Read(IO &IO);
      bool Write(IO &IO);
   };
   
   struct UidGidMap
   {
      unsigned long Tag;
      unsigned long FileID;
      unsigned long RealID;
      string Name;
      
      enum Flags {FlRealID = (1<<0)};
      
      bool Read(IO &IO);
      bool Write(IO &IO);
   };
   
   struct HardLink : public NormalFile
   {
      unsigned long Serial;
      
      bool Read(IO &IO);
      bool Write(IO &IO);
   };
   
   struct Trailer
   {
      unsigned long Tag;   
      unsigned long Signature;
      
      bool Read(IO &IO);
      bool Write(IO &IO);
      Trailer();
   };
   
   struct RSyncChecksum
   {
      unsigned long Tag;
      unsigned long BlockSize;
      unsigned long FileSize;

      // Array of 160 bit values (20 bytes) stored in Network byte order
      unsigned char *Sums;
      
      bool Read(IO &IO);
      bool Write(IO &IO);
      RSyncChecksum();
      ~RSyncChecksum();
   };
  
   struct AggregateFile
   {
      unsigned long Tag;
      string File;
      
      bool Read(IO &IO);
      bool Write(IO &IO);
   };
  
   
   enum Types {tHeader=0, tDirMarker=1, tDirStart=2, tDirEnd=3, tNormalFile=4,
      tSymlink=5, tDeviceSpecial=6, tDirectory=7, tFilter=8, 
      tUidMap=9, tGidMap=10, tHardLink=11, tTrailer=12, tRSyncChecksum=13,
      tAggregateFile=14, tRSyncEnd=15};

   unsigned long Tag;
   Header Head;
   Directory Dir;
   NormalFile NFile;
   Symlink SLink;
   DeviceSpecial DevSpecial; 
   Filter Filt;
   UidGidMap UMap;
   HardLink HLink;
   Trailer Trail;
   DirEntity *Entity;
   NormalFile *File;
   RSyncChecksum RChk;
   AggregateFile AgFile;
      
   bool Step(IO &IO);
   bool Print(ostream &out);
};

class dsFList::IO
{
   public:

   string LastSymlink;
   dsFList::Header Header;
   bool NoStrings;
   
   virtual bool Read(void *Buf,unsigned long Len) = 0;
   virtual bool Write(const void *Buf,unsigned long Len) = 0;
   virtual bool Seek(unsigned long Bytes) = 0;
   virtual unsigned long Tell() = 0;
   
   bool ReadNum(unsigned long &Number);
   bool WriteNum(unsigned long Number);
   bool ReadInt(unsigned long &Number,unsigned char Count);
   bool WriteInt(unsigned long Number,unsigned char Count);
   bool ReadInt(signed long &Number,unsigned char Count);
   bool WriteInt(signed long Number,unsigned char Count);
   bool ReadString(string &Foo);
   bool WriteString(string const &Foo);
   
   IO();
   virtual ~IO() {};
};

#endif

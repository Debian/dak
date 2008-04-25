// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: filelist.cc,v 1.14 1999/12/26 06:59:00 jgg Exp $
/* ######################################################################
   
   File List Structures

   This module has a large group of services all relating to the binary
   file list. Each individual record type has an read and write function
   that can be used to store it into a unpacked structure.
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync/filelist.h"
#endif

#include <dsync/filelist.h>
#include <dsync/error.h>
#include <system.h>

#include <time.h>
#include <stdio.h>
#include <iostream>
using namespace std;
									/*}}}*/

// FList::Step - Step to the next record				/*{{{*/
// ---------------------------------------------------------------------
/* This is an encompassing function to read a single record of any type
   from the IO */
bool dsFList::Step(IO &IO)
{
   if (!(_error->PendingError() == false && IO.ReadInt(Tag,1) == true))
      return false;

   Entity = 0;
   File = 0;
   
   switch (Tag)
   {
      case dsFList::tHeader:
      Head.Tag = Tag;
      Head.Read(IO);
      IO.Header = Head;
      break;
	 
      case dsFList::tDirMarker:
      case dsFList::tDirStart:
      case dsFList::tDirectory:
      Dir.Tag = Tag;
      Entity = &Dir;
      return Dir.Read(IO);
	     
      case dsFList::tNormalFile:
      NFile.Tag = Tag;
      Entity = &NFile;
      File = &NFile;
      return NFile.Read(IO);
	 
      case dsFList::tSymlink:
      SLink.Tag = Tag;
      Entity = &SLink;
      return SLink.Read(IO);
	 
      case dsFList::tDeviceSpecial:
      DevSpecial.Tag = Tag;
      Entity = &DevSpecial;
      return DevSpecial.Read(IO);
      
      case dsFList::tFilter:
      Filt.Tag = Tag;
      return Filt.Read(IO);
      
      case dsFList::tUidMap:
      UMap.Tag = Tag;
      return UMap.Read(IO);
      
      case dsFList::tGidMap:
      UMap.Tag = Tag;
      return UMap.Read(IO);
      
      case dsFList::tHardLink:
      HLink.Tag = Tag;
      Entity = &HLink;
      File = &HLink;
      return HLink.Read(IO);
      
      case dsFList::tTrailer:
      Trail.Tag = Tag;
      return Trail.Read(IO);

      case dsFList::tRSyncChecksum:
      RChk.Tag = Tag;
      return RChk.Read(IO);
      
      case dsFList::tAggregateFile:
      AgFile.Tag = Tag;
      return AgFile.Read(IO);
	 
      case tRSyncEnd:
      case tDirEnd:
      return true;
      
      default:
      return _error->Error("Corrupted file list");
   }
   return true;
}
									/*}}}*/
// FList::Print - Print out the record					/*{{{*/
// ---------------------------------------------------------------------
/* This simply displays the record */
bool dsFList::Print(ostream &out)
{
   char S[1024];
   switch (Tag)
   {
      case tHeader:
      {
	 snprintf(S,sizeof(S),"H Sig=%lx Maj=%lu Min=%lu Epoch=%lu Count=%lu\n",
		  Head.Signature,Head.MajorVersion,Head.MinorVersion,
		  Head.Epoch,Head.FlagCount);
	 out << S;
	 break;
      }
	 
      case tDirMarker:
      case tDirStart:
      case tDirectory:
      {
	 if (Tag == tDirMarker)
	    snprintf(S,sizeof(S),"DM Mod=%lu",
		     Dir.ModTime+Head.Epoch);
	 if (Tag == tDirStart)
	    snprintf(S,sizeof(S),"DS Mod=%lu",
		     Dir.ModTime+Head.Epoch);
	 if (Tag == tDirectory)
	    snprintf(S,sizeof(S),"D Mod=%lu",
		     Dir.ModTime+Head.Epoch);
	 out << S;
	 if ((Head.Flags[Tag] & Directory::FlPerm) != 0)
	 {
	    snprintf(S,sizeof(S)," Perm=%lo",Dir.Permissions);
	    out << S;
	 }
	 
	 if ((Head.Flags[Tag] & Directory::FlOwner) != 0)
	 {
	    snprintf(S,sizeof(S)," U=%lu G=%lu",Dir.User,Dir.Group);
	    out << S;
	 }
	 
	 snprintf(S,sizeof(S)," N='%s'\n",Dir.Name.c_str());
	 out << S;
	 break;
      }
      
      case tDirEnd:
      out << "DE" << endl;
      break;

      case tHardLink:
      case tNormalFile:
      {
	 snprintf(S,sizeof(S),"F Mod=%lu",File->ModTime+Head.Epoch);
	 out << S;
	 if ((Head.Flags[Tag] & NormalFile::FlPerm) != 0)
	 {
	    snprintf(S,sizeof(S)," Perm=%lo",File->Permissions);
	    out << S;
	 }
	 if ((Head.Flags[Tag] & NormalFile::FlOwner) != 0)
	 {
	    snprintf(S,sizeof(S)," U=%lu G=%lu",File->User,File->Group);
	    out << S;
	 }	 
	 if ((Head.Flags[Tag] & NormalFile::FlMD5) != 0)
	 {
	    char S[16*2+1];
	    for (unsigned int I = 0; I != 16; I++)
	       sprintf(S+2*I,"%02x",File->MD5[I]);
	    S[16*2] = 0;
	    out << " MD5=" << S;
	 }
	 
	 if (Tag == tHardLink)
	    out << " Ser=" << HLink.Serial;
	 snprintf(S,sizeof(S)," Sz=%lu N='%s'\n",File->Size,File->Name.c_str());
	 out << S;
	 	    
	 break;
      }

      case tDeviceSpecial:
      {
	 snprintf(S,sizeof(S),"S Mod=%lu",DevSpecial.ModTime+Head.Epoch);
	 out << S;
	 if ((Head.Flags[Tag] & DeviceSpecial::FlPerm) != 0)
	 {
	    snprintf(S,sizeof(S)," Perm=%lo",DevSpecial.Permissions);
	    out << S;
	 }
	 if ((Head.Flags[Tag] & DeviceSpecial::FlOwner) != 0)
	 {
	    snprintf(S,sizeof(S)," U=%lu G=%lu",DevSpecial.User,DevSpecial.Group);
	    out << S;
	 }	 
	 snprintf(S,sizeof(S)," N='%s'\n",DevSpecial.Name.c_str());
	 out << S;
	 break;
      }
      
      case tSymlink:
      {
	 snprintf(S,sizeof(S),"L Mod=%lu",SLink.ModTime+Head.Epoch);
	 out << S;
	 if ((Head.Flags[Tag] & Symlink::FlOwner) != 0)
	 {
	    snprintf(S,sizeof(S)," U=%lu G=%lu",SLink.User,SLink.Group);
	    out << S;
	 }
	 
	 snprintf(S,sizeof(S)," N='%s' T='%s'\n",SLink.Name.c_str(),SLink.To.c_str());
	 out << S;
	 break;
      }
	 
      case dsFList::tTrailer:
      {
	 snprintf(S,sizeof(S),"T Sig=%lx\n",Trail.Signature);
	 out << S;
	 break;
      }

      case dsFList::tRSyncChecksum:
      {
	 snprintf(S,sizeof(S),"RC BlockSize=%lu FileSize=%lu\n",RChk.BlockSize,RChk.FileSize);
	 out << S;
	 break;
      }
      
      case dsFList::tAggregateFile:
      {
	 snprintf(S,sizeof(S),"RAG File='%s'\n",AgFile.File.c_str());
	 break;
      }

      case tRSyncEnd:
      out << "RSE" << endl;
      break;
      
      default:
      return _error->Error("Unknown tag %u",Tag);
   }
   return true;
}
									/*}}}*/

// IO::IO - Constructor									/*{{{*/
// ---------------------------------------------------------------------
/* */
dsFList::IO::IO()
{
   NoStrings = false;
}
									/*}}}*/
// IO::ReadNum - Read a variable byte number coded with WriteNum	/*{{{*/
// ---------------------------------------------------------------------
/* Read a variable byte encoded number, see WriteNum */
bool dsFList::IO::ReadNum(unsigned long &Number)
{
   unsigned int I = 0;
   Number = 0;
   while (1)
   {
      unsigned char Byte = 0;
      if (Read(&Byte,1) == false)
	 return false;
      Number |= (Byte & 0x7F) << 7*I;
      if ((Byte & (1<<7)) == 0)
	 return true;
      I++;
   }   
}
									/*}}}*/
// IO::WriteNum - Write a variable byte number				/*{{{*/
// ---------------------------------------------------------------------
/* This encodes the given number into a variable number of bytes and writes
   it to the stream. This is done by encoding it in 7 bit chunks and using
   the 8th bit as a continuation flag */
bool dsFList::IO::WriteNum(unsigned long Number)
{
   unsigned char Bytes[10];
   unsigned int I = 0;
   while (1)
   {
      Bytes[I] = Number & 0x7F;
      Number >>= 7;
      if (Number != 0)
	 Bytes[I] |= (1<<7);
      else
	 break;
      I++;
   }
   return Write(Bytes,I+1);
}
									/*}}}*/
// IO::ReadInt - Read an unsigned int written by WriteInt		/*{{{*/
// ---------------------------------------------------------------------
/* Read an unsigned integer of a given number of bytes, see WriteInt */
bool dsFList::IO::ReadInt(unsigned long &Number,unsigned char Count)
{
   unsigned char Bytes[8];
   if (Read(&Bytes,Count) == false)
      return false;
   
   Number = 0;
   for (unsigned int I = 0; I != Count; I++)
      Number |= (Bytes[I] << I*8);
   return true;
}
									/*}}}*/
// IO::WriteInt - Write an unsigned int with a number of bytes		/*{{{*/
// ---------------------------------------------------------------------
/* This writes the number of bytes in least-significant-byte first order */
bool dsFList::IO::WriteInt(unsigned long Number,unsigned char Count)
{
   unsigned char Bytes[8];
   for (unsigned int I = 0; I != Count; I++)
      Bytes[I] = (Number >> I*8);
   return Write(Bytes,Count);
}
									/*}}}*/
// IO::ReadInt - Read an signed int written by WriteInt			/*{{{*/
// ---------------------------------------------------------------------
/* Read a signed integer of a given number of bytes, see WriteInt */
bool dsFList::IO::ReadInt(signed long &Number,unsigned char Count)
{
   unsigned char Bytes[8];
   if (Read(&Bytes,Count) == false)
      return false;
   
   Number = 0;
   for (unsigned int I = 0; I != Count; I++)
      Number |= (Bytes[I] << I*8);
   return true;
}
									/*}}}*/
// IO::WriteInt - Write an signed int with a number of bytes		/*{{{*/
// ---------------------------------------------------------------------
/* This writes the number of bytes in least-significant-byte first order */
bool dsFList::IO::WriteInt(signed long Number,unsigned char Count)
{
   unsigned char Bytes[8];
   for (unsigned int I = 0; I != Count; I++)
      Bytes[I] = (Number >> I*8);
   return Write(Bytes,Count);
}
									/*}}}*/
// IO::ReadString - Read a string written by WriteString		/*{{{*/
// ---------------------------------------------------------------------
/* If NoStrings is set then the string is not allocated into memory, this
   saves time when scanning a file */
bool dsFList::IO::ReadString(string &Foo)
{
   char S[1024];
   unsigned long Len;
   if (ReadNum(Len) == false)
      return false;
   if (Len >= sizeof(S))
      return _error->Error("String buffer too small");   
   if (Read(S,Len) == false)
      return false;
   S[Len] = 0;
   
   if (NoStrings == false)
      Foo = S;
   else
      Foo = string();
   
   return true;
}
									/*}}}*/
// IO::WriteString - Write a string to the stream			/*{{{*/
// ---------------------------------------------------------------------
/* Write a string, we encode a Number contianing the length and then the 
   string itself */
bool dsFList::IO::WriteString(string const &Foo)
{
   return WriteNum(Foo.length()) && Write(Foo.c_str(),strlen(Foo.c_str()));
}
									/*}}}*/

// Header::Header - Constructor						/*{{{*/
// ---------------------------------------------------------------------
/* The constructor sets the current signature and version information */
dsFList::Header::Header() : Signature(0x97E78AB), MajorVersion(0), 
                            MinorVersion(1)
{
   Tag = dsFList::tHeader;
   FlagCount = _count(Flags);
   memset(Flags,0,sizeof(Flags));
      
   Epoch = (unsigned long)time(0);
}
									/*}}}*/
// Header::Read - Read the coded header					/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Header::Read(IO &IO)
{
   // Read the contents
   if ((IO.ReadInt(Signature,4) && 
	IO.ReadInt(MajorVersion,2) && IO.ReadInt(MinorVersion,2) && 
	IO.ReadNum(Epoch) && IO.ReadInt(FlagCount,1)) == false)
      return false;

   unsigned long RealFlagCount = FlagCount;
   if (FlagCount > _count(Flags))
      FlagCount = _count(Flags);
   
   // Read the flag array
   for (unsigned int I = 0; I != RealFlagCount; I++)
   {
      unsigned long Jnk;
      if (I >= FlagCount)
      {
	 if (IO.ReadInt(Jnk,4) == false)
	    return false;
      }
      else
      {
	 if (IO.ReadInt(Flags[I],4) == false)
	    return false;
      }
   }
   
   return true;
}
									/*}}}*/
// Header::Write - Write the coded header				/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Header::Write(IO &IO)
{
   FlagCount = _count(Flags);
   
   // Write the contents
   if ((IO.WriteInt(Tag,1) && IO.WriteInt(Signature,4) && 
	IO.WriteInt(MajorVersion,2) && IO.WriteInt(MinorVersion,2) && 
	IO.WriteNum(Epoch) && IO.WriteInt(FlagCount,1)) == false)
      return false;
   
   // Write the flag array
   for (unsigned int I = 0; I != FlagCount; I++)
      if (IO.WriteInt(Flags[I],4) == false)
	 return false;
   return true;
}
									/*}}}*/
// Directory::Read - Read a coded directory record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Directory::Read(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.ReadInt(ModTime,4)) == false)
      return false;
   if ((F & FlPerm) == FlPerm && IO.ReadInt(Permissions,2) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.ReadNum(User) && 
				    IO.ReadNum(Group)) == false)
      return false;   
   if (IO.ReadString(Name) == false)
      return false;
   return true;
}
									/*}}}*/
// Directory::Write - Write a compacted directory record		/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Directory::Write(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.WriteInt(Tag,1) && IO.WriteInt(ModTime,4)) == false)
      return false;
   if ((F & FlPerm) == FlPerm && IO.WriteInt(Permissions,2) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.WriteNum(User) && 
				    IO.WriteNum(Group)) == false)
      return false;   
   if (IO.WriteString(Name) == false)
      return false;
   return true;
}
									/*}}}*/
// NormalFile::Read - Read the compacted file record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::NormalFile::Read(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.ReadInt(ModTime,4)) == false)
      return false;
   if ((F & FlPerm) == FlPerm && IO.ReadInt(Permissions,2) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.ReadNum(User) && 
				    IO.ReadNum(Group)) == false)
      return false;   
   if ((IO.ReadString(Name) && IO.ReadNum(Size)) == false)
      return false;
   if ((F & FlMD5) == FlMD5 && IO.Read(&MD5,16) == false)
      return false;
   
   return true;
}
									/*}}}*/
// NormalFile::write - Write the compacted file record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::NormalFile::Write(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.WriteInt(Tag,1) && IO.WriteInt(ModTime,4)) == false)
      return false;
   if ((F & FlPerm) == FlPerm && IO.WriteInt(Permissions,2) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.WriteNum(User) && 
				    IO.WriteNum(Group)) == false)
      return false;   
   if ((IO.WriteString(Name) && IO.WriteNum(Size)) == false)
      return false;
   if ((F & FlMD5) == FlMD5 && IO.Write(&MD5,16) == false)
      return false;
   
   return true;
}
									/*}}}*/
// Symlink::Read - Read a compacted symlink record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Symlink::Read(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.ReadInt(ModTime,4)) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.ReadNum(User) &&
				    IO.ReadNum(Group)) == false)
      return false;   
   if ((IO.ReadString(Name) && IO.ReadInt(Compress,1) &&
	IO.ReadString(To)) == false)
      return false;

   // Decompress the string
   if (Compress != 0)
   {
      if ((Compress & (1<<7)) == (1<<7))
	 To += Name;
      if ((Compress & 0x7F) != 0)
	 To = string(IO.LastSymlink,0,Compress & 0x7F) + To;
   }
   
   IO.LastSymlink = To;
   return true;
}
									/*}}}*/
// Symlink::Write - Write a compacted symlink record			/*{{{*/
// ---------------------------------------------------------------------
/* This performs the symlink compression described in the file list
   document. */
bool dsFList::Symlink::Write(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.WriteInt(Tag,1) && IO.WriteInt(ModTime,4)) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.WriteNum(User) &&
				    IO.WriteNum(Group)) == false)
      return false;
   
   if (IO.WriteString(Name) == false)
      return false;
   
   // Attempt to remove the trailing text
   bool Trail = false;
   if (To.length() >= Name.length())
   {
      unsigned int I = To.length() - Name.length();
      for (unsigned int J = 0; I < To.length(); I++, J++)
	 if (To[I] != Name[J])
	    break;
      if (I == To.length())
	 Trail = true;
   }
   
   // Compress the symlink target
   Compress = 0;
   unsigned int Len = To.length();
   if (Trail == true)
      Len -= Name.length();
   for (; Compress < Len && Compress < IO.LastSymlink.length() &&
	Compress < 0x7F; Compress++)
      if (To[Compress] != IO.LastSymlink[Compress])
	  break;

   // Set the trail flag
   if (Trail == true)
      Compress |= (1<<7);
   
   // Write the compresion byte
   if (IO.WriteInt(Compress,1) == false)
      return false;
   
   // Write the data string
   if (Trail == true)
   {
      if (IO.WriteString(string(To,Compress & 0x7F,To.length() - Name.length() - (Compress & 0x7F))) == false)
	 return false;
   }
   else
   {
      if (IO.WriteString(string(To,Compress,To.length() - Compress)) == false)
	 return false;
   }
   
   IO.LastSymlink = To;
   
   return true;
}
									/*}}}*/
// DeviceSpecial::Read - Read a compacted device special record		/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::DeviceSpecial::Read(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.ReadInt(ModTime,4)) == false)
      return false;
   if (IO.ReadInt(Permissions,2) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.ReadNum(User) &&
				    IO.ReadNum(Group)) == false)
      return false;
   if ((IO.ReadNum(Dev) && IO.ReadString(Name)) == false)
      return false;
   return true;
}
									/*}}}*/
// DeviceSpecial::Write - Write a compacted device special record	/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::DeviceSpecial::Write(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.WriteInt(Tag,1) && IO.WriteInt(ModTime,4)) == false)
      return false;
   if (IO.WriteInt(Permissions,2) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.WriteNum(User) &&
				    IO.WriteNum(Group)) == false)
      return false;
   if ((IO.WriteNum(Dev) && IO.WriteString(Name)) == false)
      return false;
   return true;
}
									/*}}}*/
// Filter::Read - Read a compacted filter record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Filter::Read(IO &IO)
{
   if ((IO.ReadInt(Type,1) && 
	IO.ReadString(Pattern)) == false)
      return false;
   return true;
}
									/*}}}*/
// Filter::Write - Write a compacted filter record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Filter::Write(IO &IO)
{
   if ((IO.WriteInt(Tag,1) && IO.WriteInt(Type,1) &&
	IO.WriteString(Pattern)) == false)
      return false;
   return true;
}
									/*}}}*/
// UidGidMap::Read - Read a compacted Uid/Gid map record		/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::UidGidMap::Read(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   if ((IO.ReadNum(FileID)) == false)
      return false;
   
   if ((F & FlRealID) == FlRealID && IO.ReadNum(RealID) == false)
      return false;
   if (IO.ReadString(Name) == false)
      return false;
   return true;
}
									/*}}}*/
// UidGidMap::Write - Write a compacted Uid/Gid map record		/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::UidGidMap::Write(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   if ((IO.WriteInt(Tag,1) && IO.WriteNum(FileID)) == false)
      return false;
   
   if ((F & FlRealID) == FlRealID && IO.WriteNum(RealID) == false)
      return false;
   if (IO.WriteString(Name) == false)
      return false;
   return true;
}
									/*}}}*/
// HardLink::Read - Read the compacted link record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::HardLink::Read(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.ReadInt(ModTime,4) && IO.ReadNum(Serial)) == false)
      return false;
   if ((F & FlPerm) == FlPerm && IO.ReadInt(Permissions,2) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.ReadNum(User) && 
				    IO.ReadNum(Group)) == false)
      return false;   
   if ((IO.ReadString(Name) && IO.ReadNum(Size)) == false)
      return false;
   if ((F & FlMD5) == FlMD5 && IO.Read(&MD5,16) == false)
      return false;
   
   return true;
}
									/*}}}*/
// HardLink::Write - Write the compacted file record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::HardLink::Write(IO &IO)
{
   unsigned long F = IO.Header.Flags[Tag];
   
   if ((IO.WriteInt(Tag,1) && IO.WriteInt(ModTime,4) && 
	IO.ReadNum(Serial)) == false)
      return false;
   if ((F & FlPerm) == FlPerm && IO.WriteInt(Permissions,2) == false)
      return false;
   if ((F & FlOwner) == FlOwner && (IO.WriteNum(User) && 
				    IO.WriteNum(Group)) == false)
      return false;   
   if ((IO.WriteString(Name) && IO.WriteNum(Size)) == false)
      return false;
   if ((F & FlMD5) == FlMD5 && IO.Write(&MD5,16) == false)
      return false;
   
   return true;
}
									/*}}}*/
// Trailer::Trailer - Constructor					/*{{{*/
// ---------------------------------------------------------------------
/* */
dsFList::Trailer::Trailer() : Tag(dsFList::tTrailer), Signature(0xBA87E79)
{
}
									/*}}}*/
// Trailer::Read - Read a compacted tail record				/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Trailer::Read(IO &IO)
{
   if (IO.ReadInt(Signature,4) == false)
      return false;
   return true;
}
									/*}}}*/
// Trailer::Write - Write a compacted tail record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::Trailer::Write(IO &IO)
{
   if ((IO.WriteInt(Tag,1) &&
	IO.WriteInt(Signature,4)) == false)
      return false;
   return true;
}
									/*}}}*/
// RSyncChecksum::RSyncChecksum - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsFList::RSyncChecksum::RSyncChecksum() : Tag(dsFList::tRSyncChecksum),
                                          Sums(0)
{
}
									/*}}}*/
// RSyncChecksum::~RSyncChecksum - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
dsFList::RSyncChecksum::~RSyncChecksum() 
{
   delete [] Sums;
}
									/*}}}*/
// RSyncChecksum::Read - Read a compacted device special record		/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::RSyncChecksum::Read(IO &IO)
{
   if ((IO.ReadNum(BlockSize) && IO.ReadNum(FileSize)) == false)
      return false;
   
   // Read in the checksum table
   delete [] Sums;
   Sums = new unsigned char[(FileSize + BlockSize-1)/BlockSize*20];
   if (IO.Read(Sums,(FileSize + BlockSize-1)/BlockSize*20) == false)
      return false;
   
   return true;
}
									/*}}}*/
// RSyncChecksum::Write - Write a compacted device special record	/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::RSyncChecksum::Write(IO &IO)
{
   if ((IO.WriteInt(Tag,1) && IO.WriteNum(BlockSize) &&
	IO.WriteNum(FileSize)) == false)
      return false;
   
   if (IO.Write(Sums,(FileSize + BlockSize-1)/BlockSize*20) == false)
      return false;
   return true;
}
									/*}}}*/
// AggregateFile::Read - Read a aggregate file record			/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::AggregateFile::Read(IO &IO)
{
   return IO.ReadString(File);
}
									/*}}}*/
// AggregateFile::Write - Write a compacted filter record		/*{{{*/
// ---------------------------------------------------------------------
/* */
bool dsFList::AggregateFile::Write(IO &IO)
{
   if ((IO.WriteInt(Tag,1) && IO.WriteString(File)) == false)
      return false;
   return true;
}
									/*}}}*/

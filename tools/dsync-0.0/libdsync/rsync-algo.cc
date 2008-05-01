// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: rsync-algo.cc,v 1.3 1999/12/26 06:59:01 jgg Exp $
/* ######################################################################
   
   RSync Algorithrim
   
   The RSync algorithim is attributed to Andrew Tridgell and is a means
   for matching blocks between two streams.  The algorithrim implemented 
   here differs slightly in its structure and is carefully optimized to be 
   able to operate on very large files effectively.

   We rely on the RSync rolling weak checksum routine and the MD4 strong 
   checksum routine. This implementation requires a uniform block size 
   for each run.
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync/rsync-algo.h"
#endif

#include <dsync/rsync-algo.h>
#include <dsync/error.h>
#include <dsync/slidingwindow.h>
#include <dsync/md5.h>
#include <dsync/md4.h>

#include <stdio.h>
#include <inttypes.h>
#include <netinet/in.h>
									/*}}}*/

// RollingChecksum - Compute the checksum perscribed by rsync		/*{{{*/
// ---------------------------------------------------------------------
/* */
static inline unsigned long RollingChecksum(unsigned char *Start,
					    unsigned char *End)
{
   unsigned long A = 0;
   unsigned long B = 0;

   /* A = sum(X[i],j,k)  B = sum((k-j+1)*X[i],j,k);
      Which reduces to the recurrence, B = sum(A[I],j,k); */
   for (; Start != End; Start++)
   {
      A += *Start;
      B += A;
   }

   return (A & 0xFFFF) | (B << 16);
}
									/*}}}*/
// GenerateRSync - Compute the rsync blocks for a file			/*{{{*/
// ---------------------------------------------------------------------
/* This function generates the RSync checksums for each uniform block in 
   the file. */
bool GenerateRSync(FileFd &Fd,dsFList::RSyncChecksum &Ck,
		   unsigned char OutMD5[16],
		   unsigned long BlockSize)
{
   SlidingWindow Wind(Fd);
   MD5Summation MD5;
   
   Ck.Tag = dsFList::tRSyncChecksum;
   Ck.BlockSize = BlockSize;
   Ck.FileSize = Fd.Size();
   
   // Allocate sum storage space
   delete [] Ck.Sums;
   Ck.Sums = new unsigned char[(Ck.FileSize + BlockSize-1)/BlockSize*20];

   // Slide over the file
   unsigned char *Start = 0;
   unsigned char *End = 0;
   unsigned char *Sum = Ck.Sums;
   unsigned char *SumEnd = Sum + (Ck.FileSize + BlockSize-1)/BlockSize*20;
   while (Sum < SumEnd)
   {
      // Tail little bit of the file
      if ((unsigned)(End - Start) < BlockSize)
      {
	 unsigned char *OldEnd = End;
	 if (Wind.Extend(Start,End) == false)
	    return false;
	 
	 // The file is very small, pretend this is the last block
	 if ((unsigned)(End - Start) < BlockSize && End != Start)
	 {
	    OldEnd = End;
	    End = Start;
	 }
	 
	 // All Done
	 if (Start == End)
	 {
	    /* The last block is rather artifical but can be of use in some
	       cases. Just remember not to insert it into the hash
	       search table!! */
	    *(uint32_t *)Sum = htonl(0xDEADBEEF);
	    InitMD4(Sum+4);
	    ComputeMD4Final(Sum+4,Start,OldEnd,OldEnd-Start);
	    MD5.Add(Start,OldEnd);
	    Sum += 20;
	    break;
	 }
      }

      // Compute the checksums
      MD5.Add(Start,Start+BlockSize);
      *(uint32_t *)Sum = htonl(RollingChecksum(Start,Start+BlockSize));
      InitMD4(Sum+4);
      ComputeMD4Final(Sum+4,Start,Start+BlockSize,BlockSize);
      Sum += 20;
      
      Start += BlockSize;
   }
   
   if (Sum != SumEnd)
      return _error->Error("Size Mismatch generating checksums");
   
   MD5.Result().Value(OutMD5);
   
   return true;
}
									/*}}}*/

// RSyncMatch::RSyncMatch - Constructor					/*{{{*/
// ---------------------------------------------------------------------
/* This generates the btree and hash table for looking up checksums */
RSyncMatch::RSyncMatch(dsFList::RSyncChecksum const &Ck) : Fast(1 << 16), 
                                    Ck(Ck)
{
   Indexes = 0;
   unsigned int Blocks = (Ck.FileSize + Ck.BlockSize-1)/Ck.BlockSize;
   
   // Drop the last partial block from the hashing
   if (Blocks < 3)
      return;
   Blocks--;
   
   // Setup the index table
   Indexes = new uint32_t *[Blocks];
   IndexesEnd = Indexes + Blocks;
   
   // Ready the checksum pointers
   unsigned char *Sum = Ck.Sums;
   unsigned char *SumEnd = Sum + Blocks*20;
   for (uint32_t **I = Indexes; Sum < SumEnd; Sum += 20)
   {
      *I++ = (uint32_t *)Sum;
   }
   
   // Sort them
   qsort(Indexes,Blocks,sizeof(*Indexes),Sort);
   
   // Generate the hash table
   unsigned int Cur = 0;
   Hashes[Cur] = Indexes;
   for (uint32_t **I = Indexes; I != IndexesEnd; I++)
   {
      printf("%x\n",**I);
      Fast.Set((**I) >> 16);
      while (((**I) >> 24) > Cur)
	 Hashes[Cur++] = I;
   }  
   while (Cur <= 256)
      Hashes[Cur++] = IndexesEnd;

   for (unsigned int Cur = 1; Cur != 255; Cur++)
   {
      printf("%u %p %x\n",Hashes[Cur] - Hashes[Cur-1],Hashes[Cur],**Hashes[Cur] >> 24);
   }
}
									/*}}}*/
// RSyncMatch::~RSyncMatch - Destructor					/*{{{*/
// ---------------------------------------------------------------------
/* */
RSyncMatch::~RSyncMatch()
{
   delete [] Indexes;
}
									/*}}}*/
// RSyncMatch::Sort - QSort function					/*{{{*/
// ---------------------------------------------------------------------
/* */
int RSyncMatch::Sort(const void *L,const void *R)
{
   if (**(uint32_t **)L == **(uint32_t **)R)
      return 0;
   if (**(uint32_t **)L > **(uint32_t **)R)
      return 1;
   return -1;
}
									/*}}}*/
bool RSyncMatch::Scan(FileFd &Fd)
{
   for (unsigned int Cur = 1; Cur != 256; Cur++)
   {
      printf("%u %p\n",Hashes[Cur] - Hashes[Cur-1],Hashes[Cur]);
   }
   
   return true;
}

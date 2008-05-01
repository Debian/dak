// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: rsync-algo.h,v 1.3 1999/12/26 06:59:01 jgg Exp $
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
#ifndef DSYNC_RSYNC_ALGO_H
#define DSYNC_RSYNC_ALGO_H

#ifdef __GNUG__
#pragma interface "dsync/rsync-algo.h"
#endif 

#include <dsync/fileutl.h>
#include <dsync/filelist.h>
#include <dsync/bitmap.h>

#include <inttypes.h>

class RSyncMatch
{
   uint32_t **Indexes;
   uint32_t **IndexesEnd;
   uint32_t **Hashes[257];
   BitmapVector Fast;
   dsFList::RSyncChecksum const &Ck;

   static int Sort(const void *L,const void *R);
   
   protected:
   
   virtual bool Hit(unsigned long Block,off_t SrcOff,
		    const unsigned char *Data) {return true;};
   
   public:

   bool Scan(FileFd &Fd);
      
   RSyncMatch(dsFList::RSyncChecksum const &Ck);
   virtual ~RSyncMatch();
};

bool GenerateRSync(FileFd &Fd,dsFList::RSyncChecksum &Ck,
		   unsigned char MD5[16],
		   unsigned long BlockSize = 8*1024);

#endif

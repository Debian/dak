// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: slidingwindow.h,v 1.2 1999/11/15 07:59:49 jgg Exp $
/* ######################################################################
   
   Sliding Window - Implements a sliding buffer over a file. 
   
   The buffer can be of arbitary size and where possible mmap is used
   to optimize IO.
   
   To use, init the class and then call Extend with a 0 input pointer
   to receive the first block and then call extend with Start <= End 
   to get the next block. If Start != End then Start will be returned
   with a new value, but pointing at the same byte, that is the new
   region will contain the subregion Start -> End(o) but with a new
   length End-Start, End != End(o).
   
   After the file has been exhausted Start == End will be returned, but
   the old region Start -> End(o) will remain valid.
   
   ##################################################################### */
									/*}}}*/
#ifndef SLIDING_WINDOW_H
#define SLIDING_WINDOW_H

#ifdef __GNUG__
#pragma interface "dsync/slidingwindow.h"
#endif 

#include <sys/types.h>
#include <dsync/fileutl.h>

class SlidingWindow
{
   unsigned char *Buffer;
   unsigned long Size;
   unsigned long MinSize;
   FileFd &Fd;
   unsigned long PageSize;
   off_t Offset;
   off_t Left;
   
   inline unsigned long Align(off_t V) const {return ((V % PageSize) == 0)?V:V + PageSize - (V % PageSize);};
   inline unsigned long Align(unsigned long V) const {return ((V % PageSize) == 0)?V:V + PageSize - (V % PageSize);};
   inline unsigned long AlignDn(off_t V) const {return ((V % PageSize) == 0)?V:V - (V % PageSize);};
   inline unsigned long AlignDn(unsigned long V) const {return ((V % PageSize) == 0)?V:V - (V % PageSize);};
   
   public:

   // Make the distance Start - End longer if possible
   bool Extend(unsigned char *&Start,unsigned char *&End);
   
   SlidingWindow(FileFd &Fd,unsigned long MinSize = 0);
   ~SlidingWindow();
};

#endif

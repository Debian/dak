// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: slidingwindow.cc,v 1.1 1999/11/05 05:47:06 jgg Exp $
/* ######################################################################

   Sliding Window - Implements a sliding buffer over a file. 

   It would be possible to implement an alternate version if 
   _POSIX_MAPPED_FILES is not defined.. 
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync/slidingwindow.h"
#endif

#include <dsync/slidingwindow.h>
#include <dsync/error.h>

#include <sys/mman.h>
#include <unistd.h>
									/*}}}*/

// SlidingWindow::SlidingWindow - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
SlidingWindow::SlidingWindow(FileFd &Fd,unsigned long MnSize) : Buffer(0),
                              MinSize(MnSize), Fd(Fd)
{       
   Offset = 0;
   Left = 0;
   PageSize = sysconf(_SC_PAGESIZE);
      
   if (MinSize < 1024*1024)
      MinSize = 1024*1024;
   MinSize = Align(MinSize);   
}
									/*}}}*/
// SlidingWindow::~SlidingWindow - Destructor				/*{{{*/
// ---------------------------------------------------------------------
/* Just unmap the mapping */
SlidingWindow::~SlidingWindow()
{
   if (Buffer != 0)
   {
      if (munmap((char *)Buffer,Size) != 0)
	 _error->Warning("Unable to munmap");
   }   
}
									/*}}}*/
// SlidingWindow::Extend - Make Start - End longer									/*{{{*/
// ---------------------------------------------------------------------
/* Start == End when the file is exhausted, false is an IO error. */
bool SlidingWindow::Extend(unsigned char *&Start,unsigned char *&End)
{
   unsigned long Remainder = 0;
   
   // Restart
   if (Start == 0 || Buffer == 0)
   {
      Offset = 0;
      Left = Fd.Size();
   }
   else
   {
      if (AlignDn((unsigned long)(Start - Buffer)) == 0)
	 return _error->Error("SlidingWindow::Extend called with too small a 'Start'");

      // Scanning is finished.
      if (Left < (off_t)Size)
      {
	 End = Start;
	 return true;
      }
      
      Offset += AlignDn((unsigned long)(Start - Buffer));
      Left -= AlignDn((unsigned long)(Start - Buffer));
      Remainder = (Start - Buffer) % PageSize;      
   }

   // Release the old region
   if (Buffer != 0)
   {
      if (munmap((char *)Buffer,Size) != 0)
	 return _error->Errno("munmap","Unable to munmap");
      Buffer = 0;
   }

   // Maximize the amount that can be mapped
   if (Left < (off_t)MinSize)
      Size = Align(Left);
   else
      Size = MinSize;
   
   // Map it
   Buffer = (unsigned char *)mmap(0,Size,PROT_READ,MAP_PRIVATE,Fd.Fd(),Offset);
   if (Buffer == (unsigned char *)-1)
      return _error->Errno("mmap","Couldn't make mmap %lu->%lu bytes",(unsigned long)Offset,
			   Size);
   
   // Reposition
   if (Left < (off_t)Size)
      End = Buffer + Left;
   else
      End = Buffer + Size;
   Start = Buffer + Remainder;
   return true;
}
									/*}}}*/

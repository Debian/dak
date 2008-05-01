// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: bitmap.h,v 1.1 1999/11/05 05:47:06 jgg Exp $
/* ######################################################################

   Bitmap - A trivial class to implement an 1 bit per element boolean
            vector
   
   This is deliberately extremely light weight so that it is fast for 
   the client.
   
   ##################################################################### */
									/*}}}*/
#ifndef DSYNC_BITMAP
#define DSYNC_BITMAP

#ifdef __GNUG__
#pragma interface "dsync/bitmap.h"
#endif 

class BitmapVector
{
   unsigned long *Vect;
   unsigned long Size;
   
   #define BITMAPVECTOR_SIZE sizeof(unsigned long)*8
   
   // Compute the necessary size of the vector in bytes.
   inline unsigned Bytes() {return (Size + BITMAPVECTOR_SIZE - 1)/BITMAPVECTOR_SIZE;};
   
   public:
   
   inline void Set(unsigned long Elm) 
      {Vect[Elm/BITMAPVECTOR_SIZE] |= 1 << (Elm%BITMAPVECTOR_SIZE);};
   inline bool Get(unsigned long Elm) 
      {return (Vect[Elm/BITMAPVECTOR_SIZE] & (1 << (Elm%BITMAPVECTOR_SIZE))) != 0;};
   inline void Set(unsigned long Elm,bool To)
   {
      if (To)
	 Vect[Elm/BITMAPVECTOR_SIZE] |= 1 << (Elm%BITMAPVECTOR_SIZE);
      else
	 Vect[Elm/BITMAPVECTOR_SIZE] &= ~(1 << (Elm%BITMAPVECTOR_SIZE));
   };
   
   BitmapVector(unsigned long Size);
   ~BitmapVector();
};

#endif

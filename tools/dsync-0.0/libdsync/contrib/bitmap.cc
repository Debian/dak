// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: bitmap.cc,v 1.1 1999/11/05 05:47:06 jgg Exp $
/* ######################################################################
   
   Bitmap - A trivial class to implement an 1 bit per element boolean
            vector
   
   This is deliberately extremely light weight so that it is fast for 
   the client.
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#ifdef __GNUG__
#pragma implementation "dsync/bitmap.h"
#endif

#include <dsync/bitmap.h>

#include <string.h>
									/*}}}*/

// BitmapVector::BitmapVector - Constructor				/*{{{*/
// ---------------------------------------------------------------------
/* Allocate just enough bytes and 0 it */
BitmapVector::BitmapVector(unsigned long Size) : Size(Size)
{
   Vect = new unsigned long[Bytes()];
   memset(Vect,0,Bytes());
}
									/*}}}*/
// BitmapVector::~BitmapVector - Destructor				/*{{{*/
// ---------------------------------------------------------------------
/* */
BitmapVector::~BitmapVector()
{
   delete [] Vect;
}
									/*}}}*/

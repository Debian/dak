// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: md4.h,v 1.2 1999/11/17 04:07:17 jgg Exp $
/* ######################################################################
   
   MD4 - MD4 Message Digest Algorithm.
   
   This is a simple function to compute the MD4 of 
   
   ##################################################################### */
									/*}}}*/
#ifndef DSYNC_MD4_H
#define DSYNC_MD4_H

void InitMD4(unsigned char MD4[16]);
void ComputeMD4(unsigned char MD4[16],unsigned char const *Start,
		unsigned const char *End);
void ComputeMD4Final(unsigned char MD4[16],unsigned char const *Start,
		     unsigned char const *End,unsigned long TotalLen);

#endif

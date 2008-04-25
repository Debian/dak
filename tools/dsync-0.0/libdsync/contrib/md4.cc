// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: md4.cc,v 1.4 1999/11/17 05:59:29 jgg Exp $
/* ######################################################################
   
   MD4Sum - MD4 Message Digest Algorithm.

   This code implements the MD4 message-digest algorithm. See RFC 1186.

   Ripped shamelessly from RSync which ripped it shamelessly from Samba.
   Code is covered under the GPL >=2 and has been changed to have a C++
   interface and use the local configuration stuff.

   Copyright (C) Andrew Tridgell 1997-1998.
   
   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 2 of the License, or
   (at your option) any later version.
   
   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
   
   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
   
   ##################################################################### */
									/*}}}*/
// Include Files							/*{{{*/
#include <dsync/md4.h>

#include <string.h>
#include <inttypes.h>
#include <config.h>
									/*}}}*/

// byteSwap - Swap bytes in a buffer					/*{{{*/
// ---------------------------------------------------------------------
/* Swap n 32 bit longs in given buffer */
#ifdef WORDS_BIGENDIAN
static void byteSwap(uint32_t *buf, unsigned words)
{
   uint8_t *p = (uint8_t *)buf;
   
   do 
   {
      *buf++ = (uint32_t)((unsigned)p[3] << 8 | p[2]) << 16 |
	 ((unsigned)p[1] << 8 | p[0]);
      p += 4;
   } while (--words);
}
#else
#define byteSwap(buf,words)
#endif
									/*}}}*/
// InitMD4 - Init the MD4 buffer					/*{{{*/
// ---------------------------------------------------------------------
/* */
void InitMD4(unsigned char MD4[16])
{
   uint32_t X[4] = {0x67452301,0xefcdab89,0x98badcfe,0x10325476};
   byteSwap(X,4);
   memcpy(MD4,X,16);
}
									/*}}}*/
// ComputeMD4 - Compute the MD4 hash of a buffer			/*{{{*/
// ---------------------------------------------------------------------
/* The buffer *must* be an even multiple of 64 bytes long. The resulting
   hash is placed in the output buffer in */
#define F(X,Y,Z) (((X)&(Y)) | ((~(X))&(Z)))
#define G(X,Y,Z) (((X)&(Y)) | ((X)&(Z)) | ((Y)&(Z)))
#define H(X,Y,Z) ((X)^(Y)^(Z))
#define lshift(x,s) (((x)<<(s)) | ((x)>>(32-(s))))

#define ROUND1(a,b,c,d,k,s) a = lshift(a + F(b,c,d) + X[k], s)
#define ROUND2(a,b,c,d,k,s) a = lshift(a + G(b,c,d) + X[k] + 0x5A827999,s)
#define ROUND3(a,b,c,d,k,s) a = lshift(a + H(b,c,d) + X[k] + 0x6ED9EBA1,s)

void ComputeMD4(unsigned char MD4[16],unsigned char const *Start,
		unsigned const char *End)
{
   uint32_t X[16];
   uint32_t A,B,C,D;

   // Prepare the sum state
   memcpy(X,MD4,16);
   byteSwap(X,4);
   A = X[0];
   B = X[1];
   C = X[2];
   D = X[3];
   
   for (; End - Start >= 64; Start += 64)
   {      
      uint32_t AA, BB, CC, DD;
      
      memcpy(X,Start,sizeof(X));
      byteSwap(X,16);
	 
      AA = A; BB = B; CC = C; DD = D;
      
      ROUND1(A,B,C,D,  0,  3);  ROUND1(D,A,B,C,  1,  7);  
      ROUND1(C,D,A,B,  2, 11);  ROUND1(B,C,D,A,  3, 19);
      ROUND1(A,B,C,D,  4,  3);  ROUND1(D,A,B,C,  5,  7);  
      ROUND1(C,D,A,B,  6, 11);  ROUND1(B,C,D,A,  7, 19);
      ROUND1(A,B,C,D,  8,  3);  ROUND1(D,A,B,C,  9,  7);  
      ROUND1(C,D,A,B, 10, 11);  ROUND1(B,C,D,A, 11, 19);
      ROUND1(A,B,C,D, 12,  3);  ROUND1(D,A,B,C, 13,  7);  
      ROUND1(C,D,A,B, 14, 11);  ROUND1(B,C,D,A, 15, 19);	
      
      ROUND2(A,B,C,D,  0,  3);  ROUND2(D,A,B,C,  4,  5);  
      ROUND2(C,D,A,B,  8,  9);  ROUND2(B,C,D,A, 12, 13);
      ROUND2(A,B,C,D,  1,  3);  ROUND2(D,A,B,C,  5,  5);  
      ROUND2(C,D,A,B,  9,  9);  ROUND2(B,C,D,A, 13, 13);
      ROUND2(A,B,C,D,  2,  3);  ROUND2(D,A,B,C,  6,  5);  
      ROUND2(C,D,A,B, 10,  9);  ROUND2(B,C,D,A, 14, 13);
      ROUND2(A,B,C,D,  3,  3);  ROUND2(D,A,B,C,  7,  5);  
      ROUND2(C,D,A,B, 11,  9);  ROUND2(B,C,D,A, 15, 13);
      
      ROUND3(A,B,C,D,  0,  3);  ROUND3(D,A,B,C,  8,  9);  
      ROUND3(C,D,A,B,  4, 11);  ROUND3(B,C,D,A, 12, 15);
      ROUND3(A,B,C,D,  2,  3);  ROUND3(D,A,B,C, 10,  9);  
      ROUND3(C,D,A,B,  6, 11);  ROUND3(B,C,D,A, 14, 15);
      ROUND3(A,B,C,D,  1,  3);  ROUND3(D,A,B,C,  9,  9);  
      ROUND3(C,D,A,B,  5, 11);  ROUND3(B,C,D,A, 13, 15);
      ROUND3(A,B,C,D,  3,  3);  ROUND3(D,A,B,C, 11,  9);  
      ROUND3(C,D,A,B,  7, 11);  ROUND3(B,C,D,A, 15, 15);
      
      A += AA; 
      B += BB; 
      C += CC; 
      D += DD;
   }
   X[0] = A;
   X[1] = B;
   X[2] = C;
   X[3] = D;
   
   byteSwap(X,4);
   memcpy(MD4,X,16);
}
									/*}}}*/
// ComputeMD4Final - Finalize the MD4, length and pad			/*{{{*/
// ---------------------------------------------------------------------
/* This does the final round of MD4, Start->End will be padded to be
   congruent to 0 mod 64 and TotalLen appended. */
void ComputeMD4Final(unsigned char MD4[16],unsigned char const *Start,
		     unsigned char const *End,unsigned long TotalLen)
{
   if (End - Start >= 64)
   {
      ComputeMD4(MD4,Start,End - ((End - Start)%64));
      Start = End - ((End - Start)%64);
   }
   
   uint8_t Buf[128];
   uint32_t Len = TotalLen*8;
   
   // Create the partial end buffer, padded to be 448%512 bits long
   memset(Buf,0,128);
   if (Start != End) 
      memcpy(Buf,Start,End - Start);   
   Buf[End-Start] = 0x80;
   
   // Append the 32 bit length into the 64 bit field
   if (End-Start <= 55) 
   {      
      memcpy(Buf+56,&Len,sizeof(Len));
      byteSwap((uint32_t *)(Buf+56),1);
      ComputeMD4(MD4,Buf,Buf+64);
   }
   else 
   {
      memcpy(Buf+120,&Len,sizeof(Len));
      byteSwap((uint32_t *)(Buf+120),1);
      ComputeMD4(MD4,Buf,Buf+128);
   }   
}
									/*}}}*/

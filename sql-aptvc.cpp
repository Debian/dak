/* Wrapper round apt's version compare functions for PostgreSQL. */
/* Copyright (C) 2001, James Troup <james@nocrew.org> */

/* This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA 
 */

/* NB: do not try to use the VERSION-1 calling conventions for
   C-Language functions; it works on i386 but segfaults the postgres
   child backend on Sparc. */

#include <apt-pkg/debversion.h>

extern "C"
{

#include <postgres.h>

  int versioncmp(text *A, text *B);

  int
  versioncmp (text *A, text *B)
  {
    int result, txt_size;
    char *a, *b;

    txt_size = VARSIZE(A)-VARHDRSZ;
    a = (char *) palloc(txt_size+1);
    memcpy(a, VARDATA(A), txt_size);
    a[txt_size] = '\0';

    txt_size = VARSIZE(B)-VARHDRSZ;
    b = (char *) palloc(txt_size+1);
    memcpy(b, VARDATA(B), txt_size);
    b[txt_size] = '\0';

    result = debVS.CmpVersion (a, b);

    pfree (a);
    pfree (b);

    return (result);
  }

}

// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: genfilelist.h,v 1.5 1999/12/26 06:59:01 jgg Exp $
/* ######################################################################
   
   Generate File List 
   
   This class is responsible for generating the file list. It is fairly
   simple and direct. One hook is provided to allow a derived class to
   cache md5 generation.
   
   The file list format is documented in the filelist.sgml document.
   
   ##################################################################### */
									/*}}}*/
#ifndef DSYNC_GENFILELIST
#define DSYNC_GENFILELIST

#ifdef __GNUG__
#pragma interface "dsync/genfilelist.h"
#endif 

#include <dsync/filefilter.h>
#include <dsync/filelist.h>
#include <list>

class dsGenFileList
{
   protected:
   
   list<string> Queue;
   list<string> DelayQueue;
   dsFList::IO *IO;
   
   // Hooks
   virtual int Visit(const char *Directory,const char *File,
		     struct stat const &Stat) {return 0;};
      
   // Directory handlers
   bool DirDepthFirst(char *CurDir);
   bool DirTree();
 
   // Emitters
   bool EnterDir(const char *Dir,struct stat const &St);
   bool LeaveDir(const char *Dir);
   bool DirectoryMarker(const char *Dir,struct stat const &St);
   bool DoFile(const char *Dir,const char *File,struct stat const &St);

   bool EmitOwner(struct stat const &St,unsigned long &UID,
		  unsigned long &GID,unsigned int Tag,unsigned int Flag);
   virtual bool EmitMD5(const char *Dir,const char *File,
			struct stat const &St,unsigned char MD5[16],
			unsigned int Tag,unsigned int Flag);

   virtual bool NeedsRSync(const char *Dir,const char *File,
			   dsFList::NormalFile &F) {return false;};
   virtual bool EmitRSync(const char *Dir,const char *File,
			  struct stat const &St,dsFList::NormalFile &F,
			  dsFList::RSyncChecksum &Ck);
      
   public:
   
   // Configurable things
   enum {Depth,Breadth,Tree} Type;
   dsFileFilter Filter;
   dsFileFilter PreferFilter;
   
   bool Go(string Base,dsFList::IO &IO);

   dsGenFileList();
   virtual ~dsGenFileList();
};

#endif

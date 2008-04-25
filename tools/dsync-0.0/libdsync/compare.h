// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: compare.h,v 1.3 1999/01/17 22:00:51 jgg Exp $
/* ######################################################################
   
   Compare a file list with a local directory 
   
   The Compare class looks at the file list and then generates events
   to cause the local directory tree to become syncronized with the 
   remote tree.
   
   The Correct class takes the events and applies them to the local tree.
   It only applies information that is stored in the file list, another
   class will have to hook the events to actually fetch files for download.
   
   ##################################################################### */
									/*}}}*/
#ifndef DSYNC_COMPARE
#define DSYNC_COMPARE

#ifdef __GNUG__
#pragma interface "dsync/compare.h"
#endif 

#include <dsync/filelist.h>

class dsDirCompare
{
   unsigned int IndexSize;
   unsigned int IndexAlloc;
   unsigned int *Indexes;
   unsigned int NameAlloc;
   char *Names;

   protected:
 
   // Location of the tree
   string Base;
   
   // Scan helpers
   bool LoadDir();
   bool DoDelete(string Dir);
   bool Fetch(dsFList &List,string Dir,struct stat *St);
   bool DirExists(string Name);
   virtual bool CheckHash(dsFList &List,string Dir,unsigned char MD5[16]);
   virtual bool FixMeta(dsFList &List,string Dir,struct stat &St);
   virtual bool Visit(dsFList &List,string Dir) {return true;};

   // Derived classes can hook these to actuall make them do something
   virtual bool GetNew(dsFList &List,string Dir) {return true;};
   virtual bool Delete(string Dir,const char *Name,bool Now = false) {return true;};
   virtual bool GetChanged(dsFList &List,string Dir) {return true;};
   virtual bool SetTime(dsFList &List,string Dir) {return true;};
   virtual bool SetPerm(dsFList &List,string Dir) {return true;};
   virtual bool SetOwners(dsFList &List,string Dir) {return true;};
   
   public:

   bool Verify;
   enum {Md5Never, Md5Date, Md5Always} HashLevel;
   
   bool Process(string Base,dsFList::IO &IO);
   
   dsDirCompare();
   virtual ~dsDirCompare();
};

class dsDirCorrect : public dsDirCompare
{
   bool DirUnlink(const char *Path);
      
   protected:

   // Derived classes can hook these to actuall make them do something
   virtual bool GetNew(dsFList &List,string Dir);
   virtual bool Delete(string Dir,const char *Name,bool Now = false);
   virtual bool GetChanged(dsFList &List,string Dir);
   virtual bool SetTime(dsFList &List,string Dir);
   virtual bool SetPerm(dsFList &List,string Dir);
   virtual bool SetOwners(dsFList &List,string Dir);
   
   public:
   
};

#endif

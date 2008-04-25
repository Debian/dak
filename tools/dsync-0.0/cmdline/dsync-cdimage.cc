// -*- mode: cpp; mode: fold -*-
// Description								/*{{{*/
// $Id: dsync-cdimage.cc,v 1.2 1999/12/26 06:59:00 jgg Exp $
/* ######################################################################

   DSync CD Image - CD Image transfer program
   
   This implements the DSync CD transfer method. This method is optimized
   to reconstruct a CD from a mirror of the CD's contents and the original
   ISO image.
   
   ##################################################################### */
									/*}}}*/
// Include files							/*{{{*/
#include <dsync/cmndline.h>
#include <dsync/configuration.h>
#include <dsync/error.h>
#include <dsync/filelistdb.h>
#include <dsync/rsync-algo.h>
#include <config.h>

#include <iostream>
#include <fstream>
#include <signal.h>
using namespace std;
									/*}}}*/

// Externs								/*{{{*/
ostream c0out(cout.rdbuf());
ostream c1out(cout.rdbuf());
ostream c2out(cout.rdbuf());
ofstream devnull("/dev/null");
unsigned int ScreenWidth = 80;
									/*}}}*/

// DoGenerate - Generate the checksum list				/*{{{*/
// ---------------------------------------------------------------------
/* */
bool DoGenerate(CommandLine &CmdL)
{
   return true;
}
									/*}}}*/
// DoAggregate - Generate aggregated file records			/*{{{*/
// ---------------------------------------------------------------------
/* This takes a file list with already generated rsync checksums and builds
   aggregated file lists for each checksum record */
bool DoAggregate(CommandLine &CmdL)
{
   if (CmdL.FileList[1] == 0)
      return _error->Error("You must specify a file name");
   
   // Open the file
   dsMMapIO IO(CmdL.FileList[1]);
   if (_error->PendingError() == true)
      return false;
   
   dsFList List;
   if (List.Step(IO) == false || List.Tag != dsFList::tHeader)
      return _error->Error("Unable to read header");
   
   string Dir;
   string File;
   while (List.Step(IO) == true)
   {
      if (List.Tag == dsFList::tDirStart)
      {
	 Dir = List.Dir.Name;
	 continue;
      }
      
      if (List.Entity != 0)
      {
	 File = List.Entity->Name;
	 continue;
      }
      
      if (List.Tag == dsFList::tRSyncChecksum)
      {
	 RSyncMatch Match(List.RChk);
      }
      
      if (List.Tag == dsFList::tTrailer)
	 break;
   }
   
   return true;
}
									/*}}}*/

// ShowHelp - Show the help screen					/*{{{*/
// ---------------------------------------------------------------------
/* */
bool ShowHelp(CommandLine &CmdL)
{
   cout << PACKAGE << ' ' << VERSION << " for " << ARCHITECTURE <<
      " compiled on " << __DATE__ << "  " << __TIME__ << endl;
   
   cout << 
      "Usage: dsync-cdimage [options] command [file]\n"
      "\n"
      "dsync-cdimage is a tool for replicating CD images from a mirror of\n"
      "their contents.\n"
      "\n"
      "Commands:\n"
      "   generate - Build a file+checksum index\n"
      "   help - This help text\n"
      "   verify - Compare the index against files in the current directory\n"
      "\n"
      "Options:\n"
      "  -h  This help text.\n"
      "  -q  Loggable output - no progress indicator\n"
      "  -qq No output except for errors\n"
      "  -c=? Read this configuration file\n"
      "  -o=? Set an arbitary configuration option, ie -o dir::cache=/tmp\n"
      "See the dsync-cdimage(1) and dsync.conf(5) manual\n"
      "pages for more information." << endl;
   return 100;
}
									/*}}}*/

int main(int argc, const char *argv[])
{
   CommandLine::Args Args[] = {
      {'h',"help","help",0},
      {'q',"quiet","quiet",CommandLine::IntLevel},
      {'q',"silent","quiet",CommandLine::IntLevel},
      {'v',"verbose","verbose",CommandLine::IntLevel},
      {'c',"config-file",0,CommandLine::ConfigFile},
      {'o',"option",0,CommandLine::ArbItem},
      {0,0,0,0}};
   CommandLine::Dispatch Cmds[] = {{"generate",&DoGenerate},
                                   {"help",&ShowHelp},
                                   {"aggregate",&DoAggregate},
                                   {0,0}};
   CommandLine CmdL(Args,_config);
   if (CmdL.Parse(argc,argv) == false)
   {
      _error->DumpErrors();
      return 100;
   }
   
   // See if the help should be shown
   if (_config->FindB("help") == true ||
       CmdL.FileSize() == 0)
      return ShowHelp(CmdL);   

   // Setup the output streams
   c0out.rdbuf(cout.rdbuf());
   c1out.rdbuf(cout.rdbuf());
   c2out.rdbuf(cout.rdbuf());
   if (_config->FindI("quiet",0) > 0)
      c0out.rdbuf(devnull.rdbuf());
   if (_config->FindI("quiet",0) > 1)
      c1out.rdbuf(devnull.rdbuf());

   // Setup the signals
/*   signal(SIGWINCH,SigWinch);
   SigWinch(0);*/
   
   // Match the operation
   CmdL.DispatchArg(Cmds);
   
   // Print any errors or warnings found during parsing
   if (_error->empty() == false)
   {
      
      bool Errors = _error->PendingError();
      _error->DumpErrors();
      return Errors == true?100:0;
   }
         
   return 0; 
}

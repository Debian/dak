#include <dsync/cmndline.h>
#include <dsync/error.h>
#include <dsync/filefilter.h>

int main(int argc, const char *argv[])
{
   CommandLine::Args Args[] = {
      {'i',"include","filter:: + ",CommandLine::HasArg},
      {'e',"exclude","filter:: - ",CommandLine::HasArg},
      {'c',"config-file",0,CommandLine::ConfigFile},
      {'o',"option",0,CommandLine::ArbItem},
      {0,0,0,0}};
   CommandLine CmdL(Args,_config);
   if (CmdL.Parse(argc,argv) == false)
   {
      _error->DumpErrors();
      return 100;
   }
   
   _config->Dump();
   
   dsFileFilter Filt;
   if (Filt.LoadFilter(_config->Tree("filter")) == false)
   {
      _error->DumpErrors();
      return 100;
   }

   cout << "Test: " << Filt.Test(CmdL.FileList[0],CmdL.FileList[1]) << endl;
      
   return 0;
}

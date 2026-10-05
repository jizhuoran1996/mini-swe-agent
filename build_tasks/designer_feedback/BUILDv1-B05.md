PreviousrealNode22.16sourcebuild/installpassed after~30minutes, butofficialtestcommandexit2; controllerwasinterruptedwhilewritingfinalsummary, completecommands/logs retained. Exactupstreamlog:
Usage: test.py [options]

test.py: error: no such option: --jobs

Inspecttools/test.py acceptedselectors; filepaths discoveredas test/parallel/...mayneed parallel/test-name relativeTestROOTwithout.js, currentinvalidselector meansNOtestsran. Preservefrozenstream32tests exactset, no skip/deleteexpectedoutputs; useactualnewinstallednode via--shell=<install/bin/node> supportedflag(officialrunnerdefaultbuildnode notprebuilt). KeepfullsourcebuildNodeCLIprivateSDKconsumer.

EXACT official parser snippets:
  result.add_option('--logfile', dest='logfile',
      help='write test output to file. NOTE: this only applies the tap progress indicator')
  result.add_option("-p", "--progress",
      help="The style of progress indicator (%s)" % ", ".join(PROGRESS_INDICATORS.keys()),
      choices=list(PROGRESS_INDICATORS.keys()), default="mono")
  result.add_option("--report", help="Print a summary of the tests to be run",
      default=False, action="store_true")
  result.add_option("-s", "--suite", help="A test suite",
      default=[], action="append")
  result.add_option("--warn-unused", help="Report unused rules",
      default=False, action="store_true")
  result.add_option("-j", help="The number of parallel tasks to run, 0=use number of cores",
      default=0, type="int")
  result.add_option("-J", help="For legacy compatibility, has no effect",
      default=False, action="store_true")
  result.add_option("--time", help="Print timing information after running",
      default=False, action="store_true")
  result.add_option("--suppress-dialogs", help="Suppress Windows dialogs for crashing tests",
  result.add_option("--no-suppress-dialogs", help="Display Windows dialogs for crashing tests",
        dest="suppress_dialogs", action="store_false")
  result.add_option("--shell", help="Path to node executable", default=None)
  result.add_option("--store-unexpected-output",
      help="Store the temporary JS files from tests that fails",
      dest="store_unexpected_output", default=True, action="store_true")
  result.add_option("--no-store-unexpected-output",
      help="Deletes the temporary JS files from tests that fails",
      dest="store_unexpected_output", action="store_false")
Usevalidshort-j2; --jobs is notsupported.

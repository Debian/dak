#! /usr/bin/env python3
# (c) 2008 Thomas Viehmann
# Free software licensed under the GPL version 2 or later

import argparse
import bz2
import json
import os
import re
import datetime
import subprocess
import sys
import tempfile

from collections import defaultdict

ITEMS_TO_KEEP = 20
CACHE_FILE = '/srv/ftp-master.debian.org/misc/dinstall_time_cache'
GRAPH_DIR = '/srv/ftp.debian.org/web/stat'

graphs = {
    "dinstall": {
        "keystolist": [
            "pdiff", "packages", "dakcleanup", "changelogs", "mkfilesindices",
            "mpfm", "dep11", "release", "ddaccess", "mkchecksums",
        ],
        "showothers": True},
}

RE_LINE = re.compile(
    rb'\A... .. (\d{2}):(\d{2}):(\d{2}) .*: '
    rb'########## dinstall (BEGIN|END): ([a-z0-9]+) .*##########')


def parse_log(path: str):
    begin = {}
    times = {}

    opener = bz2.open if path.endswith(".bz2") else open
    with opener(path, "rb") as fh:
        for line in fh:
            m = RE_LINE.match(line)
            if not m:
                continue
            t = 3600 * int(m[1]) + 60 * int(m[2]) + int(m[3])
            event = m[4]
            task = m[5].decode()
            if event == b"BEGIN":
                begin[task] = t
            elif event == b"END":
                t0 = begin.get(task)
                if t0 is not None:
                    times[task] = (t - t0) / 60.0
                else:
                    print(f"W: {task} ended, but didn't start", file=sys.stderr)

    return times


parser = argparse.ArgumentParser(description='plot runtime for dinstall tasks')
parser.add_argument('--items-to-keep', type=int, default=ITEMS_TO_KEEP, metavar='N')
parser.add_argument('--cache-file', default=CACHE_FILE, metavar='PATH')
parser.add_argument('--graph-dir', default=GRAPH_DIR, metavar='PATH')
parser.add_argument('log', nargs='*')
options = parser.parse_args()

data = {}
try:
    with open(options.cache_file) as fh:
        data = json.load(fh)
except (FileNotFoundError, json.JSONDecodeError):
    pass

RE_PATH = re.compile(r'dinstall_(\d{4})\.(\d{2})\.(\d{2})-(\d{2}):(\d{2}):(\d{2})\.log(?:\.bz2)?')
for path in options.log:
    m = RE_PATH.search(path)
    if not m:
        raise Exception(f"Unexpected filename '{path}'")
    t = str(datetime.datetime(*(int(x) for x in m.groups())))
    data[t] = parse_log(path)

datakeys = sorted(data.keys())
datakeys = datakeys[-options.items_to_keep:]
data = dict((k, data[k]) for k in datakeys)

averages = defaultdict(float)
for times in data.values():
    for task, t in times.items():
        averages[task] += t
for task in averages.keys():
    averages[task] /= len(data)

for task, t in sorted(averages.items(), key=lambda xs: xs[1], reverse=True):
    print(f"{task}: {t:.2f}")

with open(f"{options.cache_file}.tmp", "x") as fh:
    json.dump(data, fh)
os.rename(f"{options.cache_file}.tmp", options.cache_file)


def dump_file(outfn, keystolist, showothers):
    showothers = (showothers and 1) or 0
    # careful, outfn is NOT ESCAPED
    f = tempfile.NamedTemporaryFile("w+t")
    print('\t'.join(keystolist + showothers * ['other']), file=f)
    for t, times in data.items():
        others = sum(dt for task, dt in times.items() if task not in keystolist)
        print(t + '\t' + '\t'.join([str(times.get(task, 0)) for task in keystolist] + showothers * [str(others)]), file=f)
    f.flush()

    script = """
  bitmap(file = "%(outfile)s", type="png16m",width=16.9,height=11.8)
  d = read.table("%(datafile)s",  sep = "\t")
  #d[["ts"]] <- as.POSIXct(d[["timestamp"]])
  k = setdiff(names(d),c("ts","timestamp"))
  #palette(rainbow(max(length(k),2)))
  palette(c("midnightblue", "gold", "turquoise", "plum4", "palegreen1", "OrangeRed", "green4", "blue",
        "magenta", "darkgoldenrod3", "tomato4", "violetred2","thistle4", "steelblue2", "springgreen4", "salmon","gray"))
  #plot(d[["runtime"]],d[["compress"]],type="l",col="blue")
  #lines(d[["runtime"]],d[["logremove"]],type="l",col="red")
  #legend(as.POSIXct("2008-12-05"),9500,"logremove",col="red",lty=1)
  #plot(d[["ts"]],d[["compress"]],type="l",col="blue")
  #lines(d[["ts"]],d[["logremove"]],type="l",col="red")
  barplot(t(d[,k]), col=palette(), xlab="date",ylab="time/minutes"
          )
  par(xpd = TRUE)
  legend(xinch(-1.2),par("usr")[4]+yinch(1),legend=k,
                  ncol=3,fill=1:15) #,xjust=1,yjust=1)
  text(xinch(10),par("usr")[4]+yinch(.5),"%(title)s", cex=2)

  dev.off()
  q()
  """ % {'datafile': f.name, 'outfile': outfn,
       'title': ((not showothers) * "partial ") + "dinstall times"}
    subprocess.run(["R", "--vanilla", "--slave"],
                   input=script, stdout=subprocess.DEVNULL, text=True, check=True)


for afn, params in graphs.items():
    dump_file(os.path.join(options.graph_dir, afn + '.png'), **params)

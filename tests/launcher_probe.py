"""Isolated frozen process fixture for launcher/installer integration checks."""
import argparse
import json
import os
from pathlib import Path
import time
from common.launcher import SingleInstance

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
parser.add_argument('--ignore-shutdown',action='store_true')
parser.add_argument('--suffix',default='installer-smoke')
args=parser.parse_args()
instance=SingleInstance(args.suffix)
Path(args.output).write_text(json.dumps({'pid':os.getpid(),'primary':instance.primary}))
if instance.primary:
    end=time.monotonic()+90
    while time.monotonic()<end:
        if not args.ignore_shutdown and instance.poll()=='shutdown': break
        time.sleep(.05)
instance.close()

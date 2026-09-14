"""Run the four-stage local analysis in isolated sequential worker processes."""
import argparse
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parent


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float,default=60);parser.add_argument('--whole-file',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    from separate_audio import verify_model
    verify_model()
    out=(args.output or ROOT/'results'/('deep-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])).resolve()
    command=[sys.executable,str(ROOT/'deep_analysis.py'),str(args.source.resolve()),'--start',str(args.start),
             '--duration',str(args.duration),'--pitch','--output',str(out)]
    if args.whole_file:command.append('--whole-file')
    subprocess.run(command,check=True)
    for script,extra in [('separate_audio.py',['--stem-pitch']),('melody_analysis.py',[]),('finish_deep_report.py',[]),('prepare_listening.py',[])]:
        subprocess.run([sys.executable,str(ROOT/script),str(out),*extra],check=True)
    print('All four analysis stages completed: '+str(out/'report.md'))

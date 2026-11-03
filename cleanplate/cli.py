"""JSON CLI, importable without Qt or the MCP SDK."""
import argparse
import json
from pathlib import Path
import sys
import threading
from . import automation as api
from .media import probe, Cancelled


def main():
    if len(sys.argv)>1 and sys.argv[1]=='mcp':
        sys.argv.pop(1)
        from .mcp_server import main as serve
        serve()
        return 0
    parser=argparse.ArgumentParser(description='Clean Plate Studio headless automation; stdout is JSON')
    parser.add_argument('--jobs-dir',default=str(Path.cwd()/'.cleanplate-jobs'))
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('schema')
    sub.add_parser('job-list')
    p=sub.add_parser('probe');p.add_argument('path')
    p=sub.add_parser('create');p.add_argument('project');p.add_argument('--source',required=True);p.add_argument('--reference',required=True)
    p.add_argument('--mode',choices=api.MODES,default='cutout');p.add_argument('--settings',type=json.loads,default={})
    p.add_argument('--no-fit',action='store_true');p.add_argument('--start',type=float,default=0);p.add_argument('--duration',type=float,default=3)
    p=sub.add_parser('inspect');p.add_argument('project')
    p=sub.add_parser('update');p.add_argument('project');p.add_argument('--settings',type=json.loads,default={})
    p.add_argument('--output',type=json.loads,default={});p.add_argument('--project-fields',type=json.loads,default={});p.add_argument('--save-as')
    p=sub.add_parser('align');p.add_argument('project');p.add_argument('--time',type=float,default=0);p.add_argument('--save-as')
    for name in ('preview','frame','render','job-start'):
        p=sub.add_parser(name);p.add_argument('project');p.add_argument('output')
        if name in ('preview','frame'):p.add_argument('--time',type=float,default=0)
        if name=='preview':p.add_argument('--view',choices=api.VIEWS,default='Recorte');p.add_argument('--limit',type=int,default=1280)
    for name in ('job-status','job-cancel','job-run'):
        p=sub.add_parser(name);p.add_argument('id')
    args=parser.parse_args()
    cancel=threading.Event()
    try:
        import signal
        if args.command in ('frame','render'):
            signal.signal(signal.SIGINT,lambda *_:cancel.set())
        cmd=args.command
        if cmd=='schema': result=api.schema()
        elif cmd=='probe': result=probe(args.path)
        elif cmd=='create': result=api.create_project(args.project,args.source,args.reference,args.settings,args.mode,not args.no_fit,args.start,args.duration)
        elif cmd=='inspect': result=api.load_project(args.project)
        elif cmd=='update': result=api.update_project(args.project,args.settings,args.output,args.project_fields,args.save_as)
        elif cmd=='align': result=api.align_project(args.project,args.time,args.save_as)
        elif cmd=='preview':result=api.preview_project(args.project,args.output,args.time,args.view,args.limit)
        elif cmd in ('frame','render'):result=api.render_project(args.project,args.output,getattr(args,'time',0),cmd=='frame',cancel,
            lambda value:print(json.dumps({'event':'progress','value':value}),file=sys.stderr,flush=True))
        else:
            jobs=api.Jobs(args.jobs_dir)
            if cmd=='job-list':result=jobs.list()
            elif cmd=='job-start':result=jobs.start(args.project,args.output)
            elif cmd=='job-status':result=jobs.status(args.id)
            elif cmd=='job-cancel':result=jobs.cancel(args.id)
            else:result=jobs.run(args.id)
        print(json.dumps({'ok':True,'result':result},ensure_ascii=True),flush=True)
    except (Exception,KeyboardInterrupt) as exc:
        print(json.dumps({'ok':False,'error':{'type':type(exc).__name__,'message':str(exc) or 'Cancelled'}},ensure_ascii=True),flush=True)
        return 130 if isinstance(exc,(Cancelled,KeyboardInterrupt)) else 1
    return 0


if __name__=='__main__':sys.exit(main())

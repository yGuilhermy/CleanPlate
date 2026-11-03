from typing import Any
"""Headless application API shared by CLI and MCP. No Qt imports."""
from dataclasses import fields, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

import numpy as np
from PIL import Image
from .engine import Settings, Background, matte, composite, flatten_rgba, blurred_background
from .media import probe, read_frame, build_background, export_video, Cancelled, CREATE_FLAGS
from .preview import calculate

MODES = ['cutout', 'solid', 'matte', 'blur']
VIEWS = ['Recorte', 'Comparar', 'Matte', 'Original', 'Diferença']
_CHILDREN = []


def process_alive(pid):
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return False if ctypes.get_last_error()==87 else None
        try:
            code=wintypes.DWORD()
            return code.value==259 if kernel.GetExitCodeProcess(handle,ctypes.byref(code)) else None
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return None


def write_json(path, data, create=False):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if create:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
    else:
        temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            # Windows readers/scanners can briefly hold a file without delete
            # sharing. Retry the atomic publication, never rewrite it in place.
            for attempt in range(10):
                try:
                    os.replace(temp, path)
                    break
                except PermissionError:
                    if attempt==9:raise
                    time.sleep(.01*min(attempt+1,5))
        finally:
            temp.unlink(missing_ok=True)
    return str(path)


def schema() -> dict[str, Any]:
    """Discover all engine settings, default values, output modes and preview views."""
    defaults = Settings().to_dict()
    properties = {}
    for field in fields(Settings):
        value = defaults[field.name]
        kind = 'boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'number' if isinstance(value,float) else 'string'
        properties[field.name] = {'type':kind,'default':value}
    return {'settings':{'type':'object','properties':properties,'additionalProperties':False},
            'output':{'mode':MODES,'color':'#RRGGBB','quality':[0,1,2],'quality_crf':[16,20,24],'audio':'boolean'},
            'views':VIEWS,'project_version':3}


def normalize(data, base):
    if data.get('version') not in (1,2,3):
        raise ValueError('Unsupported project version')
    result = dict(data)
    for name in ('source','reference'):
        result[name] = str((Path(base)/data[name]).resolve())
        if not Path(result[name]).is_file():
            raise ValueError('Missing media: '+result[name])
    result['settings'] = Settings(**data.get('settings',{})).validate().to_dict()
    if any(isinstance(data.get('settings',{}).get(f.name),bool) and f.type is not bool
           for f in fields(Settings)):
        raise ValueError('Numeric settings cannot be boolean')
    start, duration = result.get('reference_start',0), result.get('reference_duration',3)
    if isinstance(start,bool) or not isinstance(start,(int,float)) or not np.isfinite(start) or start < 0:
        raise ValueError('Invalid reference_start')
    if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not np.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid reference_duration')
    fit = result.get('fit_reference',False)
    if not isinstance(fit,bool):
        raise ValueError('fit_reference must be boolean')
    output = dict(result.get('output',{}))
    if set(output)-{'mode','color','quality','audio'}:
        raise ValueError('Unknown output field')
    mode = output.get('mode',0)
    if isinstance(mode,str):
        mode = MODES.index(mode)
    if isinstance(mode,bool) or not isinstance(mode,int) or mode not in range(4):
        raise ValueError('Invalid output mode')
    color = output.get('color','#00ff00')
    from PIL import ImageColor
    if len(ImageColor.getrgb(color)) != 3:
        raise ValueError('Output color must be RGB')
    quality = output.get('quality',0)
    audio = output.get('audio',True)
    if isinstance(quality,bool) or not isinstance(quality,int) or quality not in (0,1,2) or not isinstance(audio,bool):
        raise ValueError('Invalid output quality/audio')
    result.update(version=3,reference_start=start,reference_duration=duration,fit_reference=fit,
                  output={'mode':int(mode),'color':color,'quality':int(quality),'audio':audio})
    return result


def load_project(path: str) -> dict[str, Any]:
    """Inspect a project, validate parameters and resolve media paths relative to its folder."""
    path = Path(path).resolve()
    return normalize(json.loads(path.read_text(encoding='utf-8')),path.parent)


def create_project(path: str, source: str, reference: str, settings: dict | None=None, mode: str='cutout', fit_reference: bool=True,
                   reference_start: float=0, reference_duration: float=3) -> dict[str, Any]:
    """Create a new desktop-compatible project; modes: cutout, solid, matte, blur. Existing paths are refused."""
    defaults = Settings(refine_foreground=True,edge_refinement=3,hole_area=600,feather=0).to_dict()
    defaults.update(settings or {})
    data = normalize({'version':3,'source':str(Path(source).resolve()),'reference':str(Path(reference).resolve()),
                      'settings':defaults,'output':{'mode':mode},'fit_reference':fit_reference,
                      'reference_start':reference_start,'reference_duration':reference_duration},Path.cwd())
    if Path(path).resolve() in (Path(data['source']),Path(data['reference'])):
        raise ValueError('Project cannot replace media')
    return {'project':write_json(path,data,create=True),'data':data}


def update_project(path: str, settings: dict | None=None, output: dict | None=None, project: dict | None=None, destination: str | None=None) -> dict[str, Any]:
    """Patch settings/output/media fields; save in place or to a new destination. Call settings_schema for keys.

    output: mode name/index, color RGB, quality index 0/1/2, audio boolean.
    project: source, reference, fit_reference, reference_start, reference_duration.
    """
    data = load_project(path)
    data['settings'].update(settings or {})
    data['output'].update(output or {})
    for key,value in (project or {}).items():
        if key not in ('source','reference','reference_start','reference_duration','fit_reference'):
            raise ValueError('Unknown project field: '+key)
        data[key] = str(Path(value).resolve()) if key in ('source','reference') else value
    data = normalize(data,Path(path).resolve().parent)
    target = Path(destination or path).resolve()
    if target in (Path(data['source']),Path(data['reference'])):
        raise ValueError('Project cannot replace media')
    return {'project':write_json(target,data,create=destination is not None),'data':data}


def model_for(data, info, cancel=None):
    model = build_background(data['reference'],data['reference_start'],data['reference_duration'],cancel=cancel)
    shape = (info['height'],info['width'],3)
    if model.mean.shape != shape:
        if not data['fit_reference']:
            raise ValueError('Resolution mismatch: enable fit_reference')
        size = (info['width'],info['height'])
        def resize(array):
            return np.stack([np.asarray(Image.fromarray(array[...,i]).resize(size,Image.Resampling.BILINEAR)) for i in range(3)],axis=2)
        model = Background(resize(model.mean),resize(model.deviation),model.samples)
    return model


def check_time(seconds,info):
    if not np.isfinite(seconds) or seconds < 0 or (not info['image'] and seconds >= info['duration']):
        raise ValueError('Time outside media duration')


def align_project(path, seconds=0, destination=None):
    from .alignment import estimate_alignment
    data = load_project(path); info=probe(data['source']); check_time(seconds,info)
    data['fit_reference'] = True
    model = model_for(data,info)
    transform,count = estimate_alignment(model.mean,read_frame(data['source'],seconds,info))
    transform['extrapolate_reference'] = True
    result = update_project(path,settings=transform,project={'fit_reference':True},destination=destination)
    result.update(inliers=count,transform=transform)
    return result


class Destination:
    def __init__(self, path, data, project_path):
        self.path=Path(path).resolve(); self.data=data; self.project=Path(project_path).resolve()
    def __enter__(self):
        if self.path in (Path(self.data['source']),Path(self.data['reference']),self.project):
            raise ValueError('Output cannot replace project or media')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=self.path.with_name(self.path.name+'.cleanplate-lock')
        self.handle=self.lock.open('x')
        if self.path.exists():
            self.__exit__(None,None,None)
            raise FileExistsError('Output already exists: '+str(self.path))
        return self.path
    def __exit__(self,*args):
        self.handle.close(); self.lock.unlink(missing_ok=True)


def save_png(path, array, cancel=None):
    temp=path.with_name(path.stem+'.'+uuid.uuid4().hex+'.partial.png')
    try:
        Image.fromarray(array).save(temp)
        if cancel and cancel.is_set(): raise Cancelled()
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def preview_project(project, output, seconds=0, view='Recorte', limit=1280):
    if view not in VIEWS or not isinstance(limit,int) or not 64 <= limit <= 4096:
        raise ValueError('Invalid view/preview limit (64..4096)')
    data=load_project(project);info=probe(data['source']);check_time(seconds,info)
    with Destination(output,data,project) as path:
        if path.suffix.lower() != '.png': raise ValueError('Preview requires PNG')
        model=model_for(data,info);frame=read_frame(data['source'],seconds,info)
        mode=MODES[data['output']['mode']]
        backdrop=data['output']['color'] if mode=='solid' else 'Desfocado' if mode=='blur' else 'Transparência'
        if mode=='matte' and view=='Recorte':view='Matte'
        image,_=calculate(frame,model,Settings(**data['settings']),view,backdrop,limit=limit)
        save_png(path,image)
    return {'output':str(path),'width':image.shape[1],'height':image.shape[0],'seconds':seconds}


def render_project(project, output, seconds=0, frame_only=False, cancel=None, progress=None):
    data=load_project(project);info=probe(data['source']);settings=Settings(**data['settings'])
    mode=MODES[data['output']['mode']]
    with Destination(output,data,project) as path:
        model=model_for(data,info,cancel)
        if info['image'] or frame_only:
            check_time(seconds,info)
            if path.suffix.lower()!='.png':raise ValueError('Frame export requires PNG')
            frame=read_frame(data['source'],seconds,info);alpha,_=matte(frame,model,settings)
            rgba=composite(frame,alpha,settings)
            image=(np.uint8(np.rint(alpha*255)) if mode=='matte' else flatten_rgba(rgba,data['output']['color'])
                   if mode=='solid' else blurred_background(frame,rgba,model,settings) if mode=='blur' else rgba)
            save_png(path,image,cancel);count=1
        else:
            count=export_video(data['source'],path,model,settings,mode,cancel,progress,
                               background_color=data['output']['color'],quality=[16,20,24][data['output']['quality']],
                               audio=data['output']['audio'])
    return {'output':str(path),'frames':count,'mode':mode}


class Jobs:
    """Durable jobs: CLI and MCP share IDs, progress and file-based cancellation."""
    def __init__(self, root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
    def folder(self, identifier):
        if len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('Invalid job ID')
        folder=self.root/identifier
        if not folder.is_dir(): raise ValueError('Unknown job')
        return folder
    def status(self, identifier):
        folder=self.folder(identifier)
        status=json.loads((folder/'status.json').read_text(encoding='utf-8'))
        metadata=folder/'process.json'
        if status['state'] in ('queued','running') and metadata.exists():
            pid=json.loads(metadata.read_text())['pid']
            if process_alive(pid) is False:
                status=json.loads((folder/'status.json').read_text(encoding='utf-8'))
                if status['state'] in ('queued','running'):
                    status.update(state='failed',error='Worker exited unexpectedly (possibly stopped by the MCP host). Inspect process.log and any stale output lock before retrying.')
                    write_json(folder/'status.json',status)
        return status
    def cancel(self, identifier):
        status=self.status(identifier)
        if status['state'] in ('queued','running'):
            (self.folder(identifier)/'cancel').touch()
        return self.status(identifier)
    def list(self):
        results=[]
        for folder in self.root.iterdir():
            if folder.is_dir() and len(folder.name)==32:
                try:results.append(self.status(folder.name))
                except (OSError,ValueError):continue
        return {'jobs':results,'jobs_dir':str(self.root)}
    def start(self, project, output):
        data=load_project(project)
        with Destination(output,data,project): pass
        identifier=uuid.uuid4().hex;folder=self.root/identifier;folder.mkdir()
        snapshot=folder/'project.json';write_json(snapshot,data)
        write_json(folder/'request.json',{'output':str(Path(output).resolve())})
        write_json(folder/'status.json',{'id':identifier,'state':'queued','progress':0})
        prefix=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-m','cleanplate.cli']
        env=os.environ.copy()
        if not getattr(sys,'frozen',False):
            root=Path(__file__).resolve().parents[1]
            env['PYTHONPATH']=os.pathsep.join([str(root/'.deps'),str(root),env.get('PYTHONPATH','')])
        with (folder/'process.log').open('ab') as log:
            try:
                _CHILDREN[:]=[child for child in _CHILDREN if child.poll() is None]
                child=subprocess.Popen(prefix+['--jobs-dir',str(self.root),'job-run',identifier],
                                 stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=CREATE_FLAGS,env=env)
                _CHILDREN.append(child)
                write_json(folder/'process.json',{'pid':child.pid})
            except Exception as exc:
                write_json(folder/'status.json',{'id':identifier,'state':'failed','error':str(exc),'progress':0})
                raise
        return {'id':identifier,'state':'queued','jobs_dir':str(self.root)}
    def run(self, identifier):
        folder=self.folder(identifier);request=json.loads((folder/'request.json').read_text())
        class Cancel:
            def is_set(self): return (folder/'cancel').exists()
        started=time.time()
        def state(name,progress=0,**extra):
            write_json(folder/'status.json',dict(id=identifier,state=name,progress=progress,started=started,**extra))
        try:
            if Cancel().is_set():raise Cancelled()
            state('running',pid=os.getpid())
            result=render_project(folder/'project.json',request['output'],cancel=Cancel(),
                                  progress=lambda value:state('running',value,pid=os.getpid()))
            state('completed',1,result=result)
        except Cancelled:
            state('cancelled')
        except Exception as exc:
            state('failed',error=str(exc))
        return self.status(identifier)

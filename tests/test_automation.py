import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import numpy as np
from PIL import Image
from cleanplate import automation as api
from cleanplate.media import executable, run, probe

ROOT=Path(__file__).resolve().parents[1]


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        plate=np.full((64,80,3),[60,90,110],np.uint8)
        frame=plate.copy();frame[16:50,25:55]=[220,30,20]
        Image.fromarray(plate).save(self.root/'plate.png')
        Image.fromarray(frame).save(self.root/'source.png')
        self.project=self.root/'project.json'
        api.create_project(str(self.project),str(self.root/'source.png'),str(self.root/'plate.png'),
                           {'refine_foreground':False,'hole_area':0,'edge_refinement':0})
    def tearDown(self):self.temp.cleanup()

    def test_project_validation_and_no_overwrites(self):
        old=self.project.read_bytes()
        for patch in [{'threshold':-1},{'threshold':True},{'unknown':3}]:
            with self.assertRaises((ValueError,TypeError)):
                api.update_project(str(self.project),settings=patch)
            self.assertEqual(self.project.read_bytes(),old)
        with self.assertRaises(ValueError):api.update_project(str(self.project),output={'oops':1})
        with self.assertRaises(ValueError):api.update_project(str(self.project),output={'mode':1.0})
        with self.assertRaises(ValueError):api.render_project(str(self.project),str(self.project))
        with self.assertRaises(ValueError):api.render_project(str(self.project),str(self.root/'source.png'))
        api.update_project(str(self.project),settings={'background_blur':35},output={'mode':'blur'})
        self.assertEqual(api.load_project(str(self.project))['output']['mode'],3)
        copy=self.root/'copy.json'
        api.update_project(str(self.project),destination=str(copy))
        with self.assertRaises(FileExistsError):api.update_project(str(self.project),destination=str(copy))

    def test_status_atomic_publication_retries_transient_windows_lock(self):
        from unittest.mock import patch
        original=os.replace
        attempts=[]
        def replace_once(source,target):
            attempts.append(1)
            if len(attempts)==1:raise PermissionError('transient reader lock')
            return original(source,target)
        target=self.root/'status.json'
        api.write_json(target,{'state':'queued'})
        with patch('cleanplate.automation.os.replace',side_effect=replace_once):
            api.write_json(target,{'state':'running'})
        self.assertEqual(json.loads(target.read_text())['state'],'running')
        self.assertEqual(len(attempts),2)

    def test_dead_worker_becomes_failed_instead_of_permanently_queued(self):
        from unittest.mock import patch
        self.assertTrue(api.process_alive(os.getpid()))
        jobs=api.Jobs(self.root/'jobs');identifier='b'*32;folder=jobs.root/identifier;folder.mkdir()
        api.write_json(folder/'status.json',{'id':identifier,'state':'queued','progress':0})
        api.write_json(folder/'process.json',{'pid':42})
        with patch('cleanplate.automation.process_alive',return_value=False):
            state=jobs.status(identifier)
        self.assertEqual(state['state'],'failed')
        self.assertIn('Worker exited',state['error'])

    def test_previews_frames_all_modes_and_relative_media(self):
        data=api.load_project(str(self.project));data['source']='source.png';data['reference']='plate.png'
        self.project.write_text(json.dumps(data))
        for mode in api.MODES:
            api.update_project(str(self.project),output={'mode':mode})
            p=self.root/(mode+'-preview.png');f=self.root/(mode+'-frame.png')
            api.preview_project(str(self.project),str(p))
            api.render_project(str(self.project),str(f),frame_only=True)
            with Image.open(f) as image:
                self.assertEqual(image.size,(80,64))
                self.assertEqual(image.mode,'RGBA' if mode=='cutout' else 'L' if mode=='matte' else 'RGB')
            with self.assertRaises(FileExistsError):api.preview_project(str(self.project),str(p))
        with self.assertRaises(ValueError):api.preview_project(str(self.project),str(self.root/'bad.png'),seconds=-1)
        self.assertFalse((self.root/'bad.png.cleanplate-lock').exists())

    def test_cli_json_and_errors_from_other_working_directory(self):
        entry=str(ROOT/'tools/control_entry.py')
        command=[sys.executable,entry,'inspect',str(self.project)]
        result=subprocess.run(command,capture_output=True,cwd=self.root)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        result=subprocess.run([sys.executable,entry,'update',str(self.project),'--settings','{"threshold":-1}'],capture_output=True,cwd=self.root)
        self.assertEqual(result.returncode,1)
        self.assertFalse(json.loads(result.stdout)['ok'])

    def make_video(self):
        target=self.root/'source.mkv'
        run([executable('ffmpeg'),'-v','error','-loop','1','-i',str(self.root/'source.png'),
             '-f','lavfi','-i','sine=frequency=400:duration=0.4','-t','0.4','-r','10',
             '-c:v','ffv1','-c:a','pcm_s16le',str(target)])
        api.update_project(str(self.project),project={'source':str(target)})

    def test_durable_job_snapshot_and_video_audio(self):
        self.make_video();api.update_project(str(self.project),output={'mode':'blur'})
        jobs=api.Jobs(self.root/'jobs');out=self.root/'out.mp4'
        started=jobs.start(str(self.project),str(out))
        api.update_project(str(self.project),output={'mode':'matte'})
        end=time.monotonic()+40
        while time.monotonic()<end:
            state=jobs.status(started['id'])
            if state['state'] in ('completed','failed','cancelled'):break
            time.sleep(.15)
        self.assertEqual(state['state'],'completed',state)
        self.assertEqual(state['result']['mode'],'blur')
        streams=json.loads(run([executable('ffprobe'),'-v','error','-show_streams','-of','json',str(out)]))['streams']
        self.assertTrue(any(s['codec_type']=='audio' for s in streams))
        self.assertEqual(probe(out)['width'],80)
        with self.assertRaises(ValueError):jobs.start(str(self.project),str(self.project))
        with self.assertRaises(ValueError):jobs.status('../escape')

    def test_cancelled_job_publishes_no_output(self):
        jobs=api.Jobs(self.root/'jobs');identifier='a'*32;folder=jobs.root/identifier;folder.mkdir()
        api.write_json(folder/'project.json',api.load_project(str(self.project)))
        api.write_json(folder/'request.json',{'output':str(self.root/'cancelled.png')})
        api.write_json(folder/'status.json',{'id':identifier,'state':'queued','progress':0})
        jobs.cancel(identifier);state=jobs.run(identifier)
        self.assertEqual(state['state'],'cancelled')
        self.assertFalse((self.root/'cancelled.png').exists())

    def test_mcp_stdio_real_handshake_tools_and_error(self):
        from mcp import Client, StdioServerParameters
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'tools/control_entry.py'),'mcp','--jobs-dir',str(self.root/'mcp-jobs')])
            async with Client(params) as client:
                listed=await client.list_tools()
                names={tool.name for tool in listed.tools}
                self.assertTrue({'settings_schema','render_start','job_cancel','preview','project_align'}<=names)
                result=await client.call_tool('settings_schema',{})
                self.assertFalse(result.is_error)
                self.assertIn('background_blur',result.structured_content['settings']['properties'])
                result=await client.call_tool('project_update',{'path':str(self.project),'output':{'mode':'blur'}})
                self.assertFalse(result.is_error)
                result=await client.call_tool('preview',{'project':str(self.project),'output':str(self.root/'mcp-preview.png')})
                self.assertFalse(result.is_error)
                self.assertTrue((self.root/'mcp-preview.png').is_file())
                self.assertTrue(any(block.type=='image' for block in result.content))
                result=await client.call_tool('project_update',{'path':str(self.project),'settings':{'threshold':-1}})
                self.assertTrue(result.is_error)
        asyncio.run(exercise())


if __name__=='__main__':unittest.main()

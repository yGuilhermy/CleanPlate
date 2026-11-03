from typing import Any
"""Local stdio MCP adapter. Never starts the GUI or opens a listening port."""
import argparse
import asyncio
from functools import wraps
import inspect
import base64
import json
from pathlib import Path
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ImageContent, TextContent
from . import automation as api
from .media import probe


def create_server(jobs_dir):
    server=MCPServer('Clean Plate Studio',version='1.0.0',
        instructions='Control local clean-plate projects. Inspect schema; preview before rendering. '
        'Use render_start, job_status and job_cancel for video. Output paths must be new. '
        'Job state persists in the configured jobs directory. Keep the MCP connection open during rendering: '
        'some hosts terminate all child processes on disconnect.')
    jobs=api.Jobs(jobs_dir)
    def expose(name=None, structured_output=True):
        def register(function):
            @wraps(function)
            async def call(*args,**kwargs):
                try:
                    if inspect.iscoroutinefunction(function):return await function(*args,**kwargs)
                    return await asyncio.to_thread(function,*args,**kwargs)
                except (ValueError,TypeError,OSError,RuntimeError) as exc:
                    raise ToolError(str(exc)) from exc
            return server.tool(name=name,structured_output=structured_output)(call)
        return register
    expose(name='settings_schema')(api.schema)
    @expose()
    async def media_probe(path: str) -> dict[str, Any]:
        """Inspect image/video size, orientation, duration and frame rate."""
        return await asyncio.to_thread(probe,path)
    expose(name='project_create')(api.create_project)
    expose(name='project_inspect')(api.load_project)
    expose(name='project_update')(api.update_project)

    @expose()
    async def project_align(path: str, seconds: float=0, destination: str | None=None) -> dict[str, Any]:
        """Estimate reference alignment using the specified frame; update project or save a copy."""
        return await asyncio.to_thread(api.align_project,path,seconds,destination)

    @expose(structured_output=False)
    async def preview(project: str, output: str, seconds: float=0, view: str='Recorte', limit: int=1280) -> CallToolResult:
        """Write and display a PNG preview. Views: Recorte, Comparar, Matte, Original, Diferença."""
        result=await asyncio.to_thread(api.preview_project,project,output,seconds,view,limit)
        return CallToolResult(content=[TextContent(type='text',text=json.dumps(result)),
            ImageContent(type='image',data=base64.b64encode(Path(result['output']).read_bytes()).decode('ascii'),mime_type='image/png')],
            structured_content=result)

    @expose()
    async def frame_export(project: str, output: str, seconds: float=0) -> dict[str, Any]:
        """Export the current output mode as a full-resolution PNG."""
        return await asyncio.to_thread(api.render_project,project,output,seconds,True)

    @expose()
    def render_start(project: str, output: str) -> dict[str, Any]:
        """Start durable video/image rendering and return immediately with a job ID."""
        return jobs.start(project,output)

    @expose()
    def job_status(identifier: str) -> dict[str, Any]:
        """Read queued/running/completed/failed/cancelled status and progress, including output or error."""
        return jobs.status(identifier)

    @expose()
    def job_cancel(identifier: str) -> dict[str, Any]:
        """Request cancellation. Poll status until terminal state; completed outputs are kept."""
        return jobs.cancel(identifier)
    @expose()
    def job_list() -> dict[str, Any]:
        """List durable jobs in this server's jobs directory, including jobs from earlier sessions."""
        return jobs.list()
    return server


def main():
    parser=argparse.ArgumentParser(description='Clean Plate MCP stdio server')
    parser.add_argument('--jobs-dir',default=str(Path.cwd()/'.cleanplate-jobs'))
    args=parser.parse_args()
    create_server(args.jobs_dir).run(transport='stdio')


if __name__=='__main__':main()

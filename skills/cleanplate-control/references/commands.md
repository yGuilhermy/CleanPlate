# Terminal and MCP reference

The examples assume PowerShell in the app's source folder. Replace `python tools/control_entry.py` with the absolute path of `CleanPlateControl.exe` for the portable build. Neither entry point loads Qt. Use `--help` for each subcommand.

```powershell
python tools/control_entry.py schema
python tools/control_entry.py probe "./media/source.mp4"
python tools/control_entry.py create "./work/project.json" --source "./media/source.mp4" --reference "./media/empty.jpg" --mode blur
python tools/control_entry.py update "./work/project.json" --settings '{"background_blur":30,"threshold":12,"compensate_light":true}'
python tools/control_entry.py preview "./work/project.json" "./work/preview.png" --time 1.5 --limit 1280
python tools/control_entry.py frame "./work/project.json" "./work/frame.png" --time 1.5
python tools/control_entry.py render "./work/project.json" "./work/result.mp4"
```

CLI stdout contains one JSON envelope: `{"ok":true,"result":...}` or `{"ok":false,"error":{"type":"...","message":"..."}}`. Runtime errors return exit 1, cancellation 130; syntax/help use argparse's normal exit codes (2/0). Progress for synchronous render is JSON lines on stderr. Keep stdout separate from stderr when parsing it. Ctrl+C requests graceful cancellation of a synchronous render.

## Project controls

`create PROJECT --source FILE --reference FILE [--settings JSON] [--mode cutout|solid|matte|blur] [--no-fit] [--start SECONDS] [--duration SECONDS]`

New projects match desktop defaults: foreground refinement enabled, edge refinement 3 px, small-hole fill 600 px², feather 0. Source/reference files are not copied. `inspect PROJECT` validates and resolves a saved project, including older versions 1/2/3. `schema` describes low-level engine defaults; new project defaults intentionally differ as above.

`update PROJECT [--settings JSON] [--output JSON] [--project-fields JSON] [--save-as NEW_PROJECT]`

Settings are partial, retaining unspecified fields. Output fields: `mode` as a name or integer 0/1/2/3 (cutout/solid/matte/blur), `color` as RGB, `quality` 0/1/2 (CRF16/20/24), `audio` boolean. Project fields: `source`, `reference`, `fit_reference`, `reference_start`, `reference_duration`. Changing the sampling interval reanalyzes the reference on the next preview/render. Unknown settings/output fields are rejected. An in-place update changes only the project JSON, while `--save-as` refuses existing destinations.

`align PROJECT [--time SECONDS] [--save-as NEW_PROJECT]` estimates scale/rotation/offset from the source frame, enables resizing and reference-edge extrapolation. Extrapolation approximates unknown areas and can fail; inspect the preview.

`preview PROJECT OUTPUT.png [--time SECONDS] [--view VIEW] [--limit 64..4096]`

Views: `Recorte`, `Comparar`, `Matte`, `Original`, `Diferença`. Preview transparency uses a checkerboard for visibility. `frame PROJECT OUTPUT.png [--time SECONDS]` preserves actual alpha when the selected mode is cutout. `render PROJECT OUTPUT` uses PNG for image sources, MOV for cutout videos, MP4 for the other video modes. Video rendering covers the entire source; `--time` is only for preview/frame/alignment. There is no playback/audio monitor or timeline trimming in the headless engine.

## Durable jobs

```powershell
python tools/control_entry.py --jobs-dir "./work/jobs" job-start "./work/project.json" "./work/result.mp4"
python tools/control_entry.py --jobs-dir "./work/jobs" job-status JOB_ID
python tools/control_entry.py --jobs-dir "./work/jobs" job-cancel JOB_ID
python tools/control_entry.py --jobs-dir "./work/jobs" job-list
```

Jobs default to `.cleanplate-jobs` in the calling working directory. Always reuse the returned `jobs_dir` across terminal calls. Keep the MCP connection open during rendering: some hosts kill all child processes on disconnect. Terminal jobs outside a managed host may run independently. Completed status can be queried after disconnect. Each 32-character job ID has its own project snapshot, request, status, process log and cancellation marker. Later project edits do not alter an active job. States: queued/running/completed/failed/cancelled. Progress ranges 0..1. A cancellation request is asynchronous. Final video publication is atomic; cancelled renders remove partial media. A dead recorded worker PID is reported as failed. A crash/forced external kill can leave partial media or a stale `.cleanplate-lock`; inspect the owning job/process before removing a stale lock. There is no automatic job history retention cleanup or restart/resume after a machine reboot. `job-run` is internal, not a retry command.

## MCP

Start with `CleanPlateControl.exe mcp --jobs-dir ./work/jobs` or `python tools/control_entry.py mcp --jobs-dir ./work/jobs`. This serves MCP over stdio, not an HTTP endpoint. The MCP host must launch the command and use the protocol rather than sending ad-hoc JSON.

Tools and argument names:

| Tool | Arguments |
|---|---|
| settings_schema | none |
| media_probe | path |
| project_create | path, source, reference, settings?, mode?, fit_reference?, reference_start?, reference_duration? |
| project_inspect | path |
| project_update | path, settings?, output?, project?, destination? |
| project_align | path, seconds?, destination? |
| preview | project, output, seconds?, view?, limit? |
| frame_export | project, output, seconds? |
| render_start | project, output |
| job_status | identifier |
| job_cancel | identifier |
| job_list | none |

Tool results are structured data and ordinary MCP tool errors. `preview` also returns the generated image as a standard MCP image content block, so a capable host can display it without opening a local path. Full-resolution frame exports return a local path. Tools have local filesystem privileges of the process; this is for a trusted local MCP host, not a public service. No shell execution tool, remote upload or client configuration changes are exposed.

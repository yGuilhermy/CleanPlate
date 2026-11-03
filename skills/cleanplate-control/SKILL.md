---
name: cleanplate-control
description: Operate Clean Plate Studio through MCP or its JSON terminal interface to configure clean-plate video cutouts, inspect previews and render alpha, solid backgrounds, blur or mattes.
---

Control the local Clean Plate Studio engine without opening the GUI. The application needs a source video/image and an empty-scene reference. No upload or pretrained model is involved.

## Choose the available interface

If the Clean Plate MCP server is connected, use its tools. Otherwise run `CleanPlateControl.exe` from the application's `dist/CleanPlateControl` folder, or `python tools/control_entry.py` from a source checkout. The executable includes its runtime and FFmpeg. Do not register a server or install this skill unless the user requests it.

Read [references/commands.md](references/commands.md) for command syntax, MCP parameter names, output formats and asynchronous jobs. Call `settings_schema` / `schema` to discover every current engine control instead of guessing setting names.

## Work with a project

Inspect media, then create a project or inspect an existing one. Relative media paths in loaded projects resolve against the project folder; newly supplied paths resolve against the caller's working directory. Prefer absolute paths when controlling the app from another process.

Use `project_update` / `update` to set parameters, output mode and reference sampling interval. All recorte, alignment, light compensation, cleanup, effects and background-blur controls are available in the `settings` object. Projects use the same JSON format as the desktop interface. Save to a new project with `destination` / `--save-as` when the user needs to compare variants.

If framing differs, use alignment on a representative frame and check the resulting preview. Alignment can reject scenes without enough matching background detail. It does not track a moving camera. Enable light compensation when exposure differs. Do not report an inferred matte as ground-truth accuracy.

Generate PNG previews at several useful times, inspect the image files using the host's image viewer, and adjust as needed. `preview` includes the selected output background; `frame_export` / `frame` writes a full-resolution PNG, including real alpha in `cutout` mode. The `Original`, `Matte`, `Diferença` and `Comparar` views help diagnose the mask.

## Render and observe

Use new output paths: the automation refuses to replace existing files, projects or input media. Do not delete an existing result merely to bypass this protection.

For long video renders prefer `render_start` / `job-start`, then poll `job_status` / `job-status` with the returned ID and the same jobs directory. Poll no more frequently than every 2–5 seconds. The start response acknowledges a job; it does not prove a successful render. Confirm `completed` and the returned output before reporting success. On `failed`, inspect `error` and the job's `process.log` if needed. After cancellation wait for `cancelled` (a near-finished job may instead complete).

Keep the MCP connection open while a job runs: some hosts terminate all child processes on disconnect. Completed results and job history persist. Terminal jobs started outside such a managed host can run independently. Cancel explicitly when the user's request requires stopping them. Job files contain media paths and project snapshots; treat them as local user data. If a child process was externally killed, status detects a dead recorded PID and marks it failed, but a reboot/PID reuse may leave stale state; inspect its recorded PID/log before deciding whether to launch a replacement. Never terminate unrelated processes.

## Output choices

`cutout` produces MOV/ProRes 4444 alpha; `solid` produces MP4 with an RGB background; `blur` produces MP4 with adjustable `background_blur`; `matte` produces a grayscale MP4 without audio. For still/frame export every mode uses PNG. MP4 has no alpha. Hair, glass, motion blur and similar foreground/background colors remain difficult; inspect actual results before making quality claims.

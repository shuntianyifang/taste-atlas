param([Parameter(ValueFromRemainingArguments=$true)][string[]]$FFmpegArgs)
$ErrorActionPreference='Stop'
$taskFFmpeg=& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'
if($LASTEXITCODE -ne 0){throw 'Bundled FFmpeg unavailable.'}
& $taskFFmpeg @FFmpegArgs
exit $LASTEXITCODE

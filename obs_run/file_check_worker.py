"""
Child process of obs_run.file_check.IsolatedWorker: reads one JSON request per line from stdin and
answers with one JSON line. Runs without Django setup; a crash of a native reader (astropy,
OpenCV/FFmpeg) only ends this process.

Requests (by "action"):
  check            {"path", "kind"}                      -> list of issues
  video_thumbnail  {"path", "max_dim", "max_pixels"}     -> {"png": base64} or {"error": ...}
  video_size       {"path"}                              -> {"size": [width, height]} or {"error": ...}
"""
import base64
import json
import os
import sys


def handle(request):
    action = request.get('action', 'check')
    if action == 'check':
        from obs_run.file_check import check_path
        return check_path(request['path'], request['kind'])
    try:
        if action == 'video_thumbnail':
            from obs_run.video_thumbnails import render_video_frame_png
            png = render_video_frame_png(
                request['path'], max_dim=int(request.get('max_dim', 512)), max_pixels=request.get('max_pixels'),
            )
            return {'png': base64.b64encode(png).decode('ascii')}
        if action == 'video_size':
            from obs_run.video_thumbnails import read_video_frame_size
            return {'size': list(read_video_frame_size(request['path']))}
        return {'error': f'Unknown action {action!r}'}
    except Exception as exc:
        return {'error': str(exc)}


def main():
    # Answers go to a copy of the original stdout. File descriptor 1 itself is pointed to stderr, so
    # output of native libraries (e.g. FFmpeg writing to fd 1 directly) cannot corrupt the answers.
    answers = os.fdopen(os.dup(1), 'w', buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    for line in sys.stdin:
        if not line.strip():
            continue
        answers.write(json.dumps(handle(json.loads(line))) + '\n')
        answers.flush()


if __name__ == '__main__':
    main()

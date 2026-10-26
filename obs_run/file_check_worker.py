"""
Child process of obs_run.file_check.IsolatedChecker: reads one JSON request per line from stdin
({"path": ..., "kind": ...}) and answers with the JSON list of issues on one line. Runs without
Django setup; a crash of a native file reader only ends this process.
"""
import json
import os
import sys


def main():
    # Answers go to a copy of the original stdout. File descriptor 1 itself is pointed to stderr, so
    # output of native libraries (e.g. FFmpeg writing to fd 1 directly) cannot corrupt the answers.
    answers = os.fdopen(os.dup(1), 'w', buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    from obs_run.file_check import check_path

    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        issues = check_path(request['path'], request['kind'])
        answers.write(json.dumps(issues) + '\n')
        answers.flush()


if __name__ == '__main__':
    main()

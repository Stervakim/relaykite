"""Single-use PTY child: attach controlling TTY, drop UID, exec clean shell.

Runs in its own interpreter so the multithreaded parent never uses a Python
preexec_fn between fork and exec.
"""
import fcntl
import json
import os
import sys
import termios

def main():
    argv,env,uid=json.loads(sys.argv[1])
    fcntl.ioctl(0,termios.TIOCSCTTY,0)
    if uid is not None:
        os.setgroups([]);os.setgid(uid);os.setuid(uid)
    os.execve(argv[0],argv,env)

if __name__=='__main__':main()

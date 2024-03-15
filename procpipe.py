# procpipe.asy
#
# Copyright 2024 Bill Zissimopoulos
#
# MIT License
#
# Copyright (c) 2024 Bill Zissimopoulos
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import errno
import shlex
import subprocess
import threading

class P:
    def __init__(this, *args):
        this.args = args
        this.strm = [None, None]
        this.comb = False
        this.test = True
        this.pipe = []
    def __copy__(this):
        that = this.__class__.__new__(this.__class__)
        that.args = this.args
        that.strm = list(this.strm)
        that.comb = this.comb
        that.test = this.test
        that.pipe = list(this.pipe)
        return that
    def __add__(this, that):
        this = this.__copy__()
        if isinstance(that, tuple):
            this.args += that
            return this
        elif isinstance(that, str):
            this.args += tuple(shlex.split(that, posix=True))
            return this
        else:
            raise TypeError(type(that))
    def __invert__(this):
        this = this.__copy__()
        this.comb = not this.comb
        return this
    def __neg__(this):
        this = this.__copy__()
        this.test = not this.test
        return this
    def __or__(this, that):
        this = this.__copy__()
        if isinstance(that, this.__class__):
            this.pipe.append(that)
            this.pipe.extend(that.pipe)
            that = that.strm[1]
            if that is None:
                return this
        if isinstance(that, int) or hasattr(that, "fileno") or that in (None, bytes, str):
            if hasattr(that, "fileno"):
                this.strm[1] = that.fileno()
            elif that is None:
                this.strm[1] = subprocess.DEVNULL
            else:
                this.strm[1] = that
            return this
        else:
            raise TypeError(type(that))
    def __ror__(this, that):
        this = this.__copy__()
        if isinstance(that, (bytes, int, str)) or hasattr(that, "fileno") or that in (None,):
            if hasattr(that, "fileno"):
                this.strm[0] = that.fileno()
            elif that is None:
                this.strm[0] = subprocess.DEVNULL
            else:
                this.strm[0] = that
            return this
        else:
            raise TypeError(type(that))
    def __repr__(this):
        def strmrepr(strm):
            if strm == subprocess.DEVNULL:
                return "</dev/null>"
            elif strm == bytes:
                return "<bytes>"
            elif strm == str:
                return "<str>"
            else:
                return repr(strm)
        res = []
        if this.strm[0] is not None:
            res.append(strmrepr(this.strm[0]))
        for p in [this] + this.pipe:
            res.append(f"{'~' if p.comb else ''}{'-' if not p.test else ''}{' '.join(p.args)}")
        if this.strm[1] is not None:
            res.append(strmrepr(this.strm[1]))
        return " | ".join(res)
    def __call__(this, *,
        result="output", suppress_stderr=False, capture_stderr=False, suppress_test=False):
        def feedpipe(f, buf):
            for c in [lambda: f.write(buf) if buf else None, lambda: f.close()]:
                try:
                    c()
                except BrokenPipeError:
                    pass
                except OSError as exc:
                    if exc.errno == errno.EINVAL:
                        pass
                    else:
                        raise
        pipe = [this] + this.pipe
        proc = []
        for i, p in enumerate(pipe):
            if 0 == i:
                stdin = subprocess.PIPE if isinstance(this.strm[0], (bytes, str)) else this.strm[0]
            else:
                stdin = proc[-1].stdout
            if len(pipe) - 1 != i:
                stdout = subprocess.PIPE
            else:
                stdout = subprocess.PIPE if this.strm[1] in (bytes, str) else this.strm[1]
            if suppress_stderr:
                stderr = subprocess.DEVNULL
            elif capture_stderr:
                stderr = subprocess.STDOUT
            else:
                stderr = subprocess.STDOUT if p.comb else None
            proc.append(subprocess.Popen(p.args, stdin=stdin, stdout=stdout, stderr=stderr))
            if 0 == i:
                feed = None
                if isinstance(p.strm[0], bytes):
                    feed = p.strm[0]
                elif isinstance(p.strm[0], str):
                    feed = p.strm[0].encode(errors="strict")
                if feed is not None:
                    t = threading.Thread(target=feedpipe, args=(proc[-1].stdin, feed))
                    t.daemon = True
                    t.start()
                    proc[-1].stdin = None
            else:
                stdin.close()
        out, _ = proc[-1].communicate()
        for p in proc[:-1]:
            p.wait()
        if not suppress_test:
            for i, p in enumerate(pipe):
                if p.test and 0 != proc[i].returncode:
                    raise subprocess.CalledProcessError(proc[i].returncode, proc[i].args)
        ret = proc[-1].returncode
        out = out.decode(errors="replace") if this.strm[1] == str else out
        if "output" == result:
            return out
        elif "returncode" == result:
            return ret
        elif "tuple" == result:
            return (ret, out)

if "__main__" == __name__:
    import os, sys

    ls = P("ls")
    grep = P("grep")
    head = P("head")
    less = P("less")

    assert "ls" == repr(ls)
    assert "~ls" == repr(~ls)
    assert "ls" == repr(~~ls)
    assert "-ls" == repr(-ls)
    assert "ls" == repr(--ls)
    assert "~-ls" == repr(~-ls)
    assert "~-ls" == repr(-~ls)

    assert "ls -la" == repr(ls + "-la")
    assert "ls -la" == repr(ls + ("-la",))
    assert "ls -l -a" == repr(ls + "-l -a")
    assert "ls -l -a" == repr(ls + ("-l", "-a"))

    assert "ls | </dev/null>" == repr(ls | None)
    assert "</dev/null> | ls" == repr(None | ls)
    assert "</dev/null> | ls | </dev/null>" == repr(None | ls | None)

    assert "ls | 1" == repr(ls | 1)
    assert "1 | ls" == repr(1 | ls)
    assert "1 | ls | 1" == repr(1 | ls | 1)

    assert "ls | <str>" == repr(ls | str)
    assert "'hello' | ls" == repr("hello" | ls)
    assert "'hello' | ls | <str>" == repr("hello" | ls | str)

    assert "ls | <bytes>" == repr(ls | bytes)
    assert "b'hello' | ls" == repr(b"hello" | ls)
    assert "b'hello' | ls | <bytes>" == repr(b"hello" | ls | bytes)

    p = ls | grep
    assert "ls | grep | less" == repr(p | less)
    assert "less | ls | grep" == repr(less | p)
    assert "less | ls | grep | less" == repr(less | p | less)
    assert "ls | grep" == repr(p)

    p = ls | grep
    q = ls | head
    assert "ls | grep | ls | head" == repr(p | q)
    assert "ls | grep | ls | grep | ls | head" == repr(p | p | q)
    assert "ls | grep | ls | head | ls | head" == repr(p | q | q)
    assert "ls | grep | ls | head | ls | grep | ls | head" == repr(p | q | p | q)
    assert "ls | grep" == repr(p)
    assert "ls | head" == repr(q)

    p = 1 | ls
    q = head | 2
    assert "1 | ls | head | 2" == repr(p | q)
    assert "1 | ls | ls | head | 2" == repr(p | p | q)
    assert "1 | ls | head | head | 2" == repr(p | q | q)
    assert "1 | ls | head | ls | head | 2" == repr(p | q | p | q)
    assert "1 | ls" == repr(p)
    assert "head | 2" == repr(q)

    python = P(sys.executable, "-c")

    p = -python + ('import sys; sys.exit(0)',) | str
    assert 0 == p(result="returncode")
    p = -python + ('import sys; sys.exit(42)',) | str
    assert 42 == p(result="returncode")

    p = python + ('print("hello")',) | str
    assert "hello\n" == p()
    p = "world" | python + ('import sys; print(f"hello {sys.stdin.read()}")',) | str
    assert "hello world\n" == p()
    p = "world" | ~python + ('import sys; print(f"hello {sys.stdin.read()}"); sys.stdout.flush(); print("stderr", file=sys.stderr)',) | str
    assert "hello world\nstderr\n" == p()

    p = python + ('print("hello")',) | bytes
    assert b"hello\n" == p()
    p = b"world" | python + ('import sys; print(f"hello {sys.stdin.read()}")',) | bytes
    assert b"hello world\n" == p()
    p = b"world" | ~python + ('import sys; print(f"hello {sys.stdin.read()}"); sys.stdout.flush(); print("stderr", file=sys.stderr)',) | bytes
    assert b"hello world\nstderr\n" == p()

    p = python + ('import sys; sys.stdout.write(sys.stdin.read())',)
    assert "hello" == ("hello" | p | str)()
    assert "hello" == ("hello" | p | p | str)()
    assert "hello" == ("hello" | p | p | p | str)()
    assert "hello" == ("hello" | p | p | p | p | str)()

    if "posix" == os.name:
        # see https://stackoverflow.com/a/76402964
        n = 2_000_000
        p = P("seq", str(n)) | P("tee", "/dev/stderr") | P("head", "-n", str(n // 2)) | P("wc", "-l")
        assert b" 1000000\n" == (p | bytes)(suppress_stderr=True, suppress_test=True)

    print("PASS")

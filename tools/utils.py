
import os, sys

from System.Diagnostics import Process, ProcessStartInfo


def popen(executable, arguments):
    global process # XXX: keep it alive
    processStartInfo = ProcessStartInfo(executable, arguments)
    processStartInfo.UseShellExecute = False
    processStartInfo.CreateNoWindow = True
    processStartInfo.RedirectStandardOutput = True
    process = Process.Start(processStartInfo)
    return file(process.StandardOutput.BaseStream, "r")


def eval_dict_item(container, context=None):
    if not container:
        return {}
    str_, ctx = container[0], {}
    if context is not None:
        ctx = __import__(context, fromlist=['*']).__dict__
    return eval(str_, ctx)


def read(*args):
    f = open(os.path.join(*args))
    try:
        return f.read()
    finally:
        f.close()


def read_interesting_lines(*args):
    f = open(os.path.join(*args))
    try:
        return filter(None, [l.split('#')[0].strip() for l in f.readlines()])
    finally:
        f.close()


BADGE = (
    'This file was generated by running the following command:',
    '  %s %s' % (sys.executable, ' '.join(sys.argv))
)
ASM_BADGE = '; %s\n; %s\n\n' % BADGE
C_BADGE = '/*\n * %s\n * %s\n */\n\n' % BADGE
GEN_BADGE = '# %s\n# %s\n\n' % BADGE


def _get_badge(name):
    _, ext = os.path.splitext(name)
    return {
        '.asm': ASM_BADGE,
        '.generated': GEN_BADGE,
    }.get(ext, C_BADGE)


def write(dir_, name, text, badge=False):
    f = open(os.path.join(dir_, name), "w")
    try:
        if badge:
            f.write(_get_badge(name))
        f.write(text)
    finally:
        f.close()

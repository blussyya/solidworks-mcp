import sys
import os

print("python:", sys.version)
print("64-bit:", sys.maxsize > 2**32)

import win32com.client.gencache as g
p = g.GetGeneratePath()
print("gen_py path:", p)
print("exists:", os.path.isdir(p))
if os.path.isdir(p):
    print("contents:", os.listdir(p))

import win32com.client

try:
    app = win32com.client.Dispatch("SldWorks.Application")
    print("late-bound Dispatch: OK, revision =", app.RevisionNumber)
except Exception as e:
    print("late-bound Dispatch FAILED:", repr(e))

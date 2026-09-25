"""Creates a kill-on-close job, puts a sleeping child in it, prints the child pid, then waits."""
import subprocess
import sys
import time

from manga_viewer.winjob import KillOnCloseJob

job = KillOnCloseJob()
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
job.assign(child.pid)
print(child.pid, flush=True)
time.sleep(120)

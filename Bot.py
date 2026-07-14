import os
import time

os.system("pip install -r require/requirements.txt -q")
os.system("clear")
print("\033[1;32;40mWait Until The Entire Program Gets Finished.\033[1;31;40mOtherwise...")
time.sleep(2)
os.system("cd core && python3 lol.py")

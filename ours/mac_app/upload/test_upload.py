"""Test the Drive upload chain from this PC, before any app change.
Asks for the script URL and token (typed, not saved anywhere), then:
  1. GET  connection check
  2. POST a small dummy zip to session "TEST_upload" (twice: the second must say duplicate)
Then look for  <Drive folder>/TEST_upload/dummy.zip  on this PC, and delete that folder afterwards.
Usage: python ours/mac_app/upload/test_upload.py
"""
import base64
import getpass
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
import zipfile

url = input("Apps Script /exec URL: ").strip()
token = getpass.getpass("Token (hidden, paste then Enter): ").strip()
print(f"   token received: {len(token)} characters (should match the TOKEN value in Script Properties)")


def call(req):
    with urllib.request.urlopen(req, timeout=120) as r:      # follows Apps Script's 302 redirect
        return json.loads(r.read().decode())


print("1. check:", call(url + "?" + urllib.parse.urlencode({"token": token})))

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("hello.txt", f"upload test {time.ctime()}\n")
data = buf.getvalue()
body = json.dumps({"token": token, "session": "TEST_upload", "file": "dummy.zip",
                   "md5": hashlib.md5(data).hexdigest(), "data": base64.b64encode(data).decode()}).encode()
for i in (2, 3):
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    print(f"{i}. upload:", call(req))
print("Now check the synced Drive folder on this PC for TEST_upload/dummy.zip")

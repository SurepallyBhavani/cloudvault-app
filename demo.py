"""
End-to-end demo of CloudVault's auth + access-control flow, against a REAL
running instance of the app (local or deployed) -- no UI needed.

Run the app first (`python app.py`, or point BASE_URL at your EC2 deployment),
then run this: `python demo.py`

What it proves, step by step:
  1. Three users register.
  2. The owner logs in and uploads a file.
  3. A stranger (never granted access) tries to download it -- rejected (403).
  4. The owner shares the file with a friend.
  5. The friend downloads it -- now succeeds (200), gets a real presigned URL.
  6. The stranger tries again -- still rejected. Sharing only granted the
     friend access, not everyone.
"""

import io
import time
import requests

BASE_URL = "http://localhost:5000"


def register(username, password):
    r = requests.post(f"{BASE_URL}/register", json={"username": username, "password": password})
    print(f"[register] {username}: {r.status_code} {r.json()}")
    return r


def login(username, password):
    r = requests.post(f"{BASE_URL}/login", json={"username": username, "password": password})
    print(f"[login] {username}: {r.status_code}")
    return r.json().get("token")


def upload(token, filename, content=b"hello from the demo script"):
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": (filename, io.BytesIO(content))}
    r = requests.post(f"{BASE_URL}/upload", headers=headers, files=files)
    print(f"[upload] {filename}: {r.status_code} {r.json()}")
    return r


def download(token, filename, label):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/download/{filename}", headers=headers)
    print(f"[download as {label}] {filename}: {r.status_code} {r.json()}")
    return r


def share(token, filename, target_username):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{BASE_URL}/files/{filename}/share", headers=headers, json={"username": target_username}
    )
    print(f"[share] {filename} -> {target_username}: {r.status_code} {r.json()}")
    return r


def main():
    # A timestamp suffix means usernames are unique every run -- otherwise
    # UNIQUE constraint violations after the first run, since re-registering
    # the same username twice is correctly rejected.
    stamp = int(time.time())
    owner, friend, stranger = f"owner_{stamp}", f"friend_{stamp}", f"stranger_{stamp}"
    password = "demo-password-123"
    filename = f"demo_file_{stamp}.txt"

    print("=== 1. Registering three users ===")
    register(owner, password)
    register(friend, password)
    register(stranger, password)

    print("\n=== 2. Owner logs in and uploads a file ===")
    owner_token = login(owner, password)
    upload(owner_token, filename)

    print("\n=== 3. Stranger tries to download -- should be REJECTED (403) ===")
    stranger_token = login(stranger, password)
    download(stranger_token, filename, label="stranger")

    print("\n=== 4. Owner shares the file with their friend ===")
    share(owner_token, filename, friend)

    print("\n=== 5. Friend downloads -- should now SUCCEED (200) ===")
    friend_token = login(friend, password)
    download(friend_token, filename, label="friend")

    print("\n=== 6. Stranger tries AGAIN -- still rejected (sharing was scoped to the friend only) ===")
    download(stranger_token, filename, label="stranger (again)")


if __name__ == "__main__":
    main()

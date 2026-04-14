#!/usr/bin/env python3

import datetime
import json
import pathlib
import platform
import shutil
import subprocess
import sys
import os
import urllib.request
import urllib.error
import re
import yaml

# Load configuration
CONFIG_FILE = pathlib.Path(__file__).parent / "config.yaml"
DEFAULT_CONFIG = {
    "server": {"url": "http://localhost:8080"},
    "client": {
        "download_dir": "~/Downloads",
        "auto_confirm": False,
        "temp_dir": "./temp_syrup",
        "log_level": "info"
    },
    "package": {
        "format": "zip",
        "include_hidden": True
    },
    "auth": {
        "token_file": "~/.syrup_token",
        "auto_refresh": True
    },
    "limits": {
        "max_package_size_gb": 2
    }
}

def load_config():
    """Load configuration from config.yaml or use defaults."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
            # Merge with defaults to ensure all keys exist
            for key in DEFAULT_CONFIG:
                if key not in config:
                    config[key] = DEFAULT_CONFIG[key]
                elif isinstance(DEFAULT_CONFIG[key], dict):
                    for subkey in DEFAULT_CONFIG[key]:
                        if subkey not in config[key]:
                            config[key][subkey] = DEFAULT_CONFIG[key][subkey]
            return config
    return DEFAULT_CONFIG

CONFIG = load_config()
SERVER_URL = CONFIG["server"]["url"]
TOKEN_FILE = pathlib.Path(CONFIG["auth"]["token_file"]).expanduser()
MAX_PACKAGE_SIZE_BYTES = CONFIG.get("limits", {}).get("max_package_size_gb", 2) * 1024 * 1024 * 1024

ascii = """
███████╗██╗   ██╗██████╗ ██╗   ██╗██████╗
██╔════╝╚██╗ ██╔╝██╔══██╗██║   ██║██╔══██╗
███████╗ ╚████╔╝ ██████╔╝██║   ██║██████╔╝
╚════██║  ╚██╔╝  ██╔══██╗██║   ██║██╔═══╝
███████║   ██║   ██║  ██║╚██████╔╝██║
╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝
"""


def pkg():
    print(f"Welcome {pathlib.Path.home().name}, to syrup.")
    print("Please enter the folder(s) to package. (eg.. ~/.config/)")
    loadfolder = input("> ")
    path = pathlib.Path(loadfolder).expanduser()
    if not path.exists():
        print("That path does not exist.")
        raise FileNotFoundError
    name = input("Enter a name: ")
    dependencies = input("Please list all the dependencies, seperated by commas: ")
    dependencies = [d.strip() for d in dependencies.split(",") if d.strip()]
    desc = input("Enter a description: ")
    try:
        relpath = "~/" + str(path.relative_to(pathlib.Path.home()))
    except ValueError:
        relpath = str(path)
    syrup = {
        "name": name,
        "creation": datetime.datetime.now().strftime(format="%d-%m-%Y - %H:%M"),
        "author": pathlib.Path.home().name,
        "folder": relpath,
        "depends": dependencies,
        "distro": platform.release(),
        "desc": desc,
    }
    with open(f"{path.expanduser()}/.recipe", "w") as f:
        json.dump(syrup, f)
    shutil.make_archive(name, "zip", path)
    tempzip = pathlib.Path(f"{name}.zip")
    output = pathlib.Path(f"{name}.syp")
    tempzip.rename(output)
    pathlib.Path(f"{path.expanduser()}/.recipe").unlink()
    print(f"Yaay! Done. You can find the file at {output.expanduser()}.")


def install(syrup):
    # Check if it's a server package (@username/rice format)
    if syrup.startswith('@'):
        install_from_server(syrup)
        return
    
    syrup = pathlib.Path(syrup).expanduser()
    if not syrup.exists():
        print("File not found.")
        return

    tempdir = pathlib.Path(CONFIG["client"]["temp_dir"])
    tempdir.mkdir(exist_ok=True)

    shutil.unpack_archive(str(syrup), extract_dir=tempdir, format="zip")

    recipefile = tempdir / ".recipe"
    with open(recipefile, "r") as f:
        metadata = json.load(f)

    deps = metadata.get("depends", [])
    if deps:
        print(f"Needed: {', '.join(deps)}")
        if shutil.which("pacman"):
            subprocess.run(["sudo", "pacman", "-S", "--needed"] + deps)
        elif shutil.which("dnf"):
            subprocess.run(["sudo", "dnf", "install"] + deps)
        else:
            print(
                "Hey.. so like.. your system's main package manager isn't supported.. Sorry.."
            )

    destination = pathlib.Path(metadata["folder"]).expanduser()
    if destination.exists():
        if not any(destination.iterdir()):
            pass
        else:
            yn = input(
                f"[WARNING] {destination.name} is NOT empty. Are you sure you would like to pour the Syrup? [Y/n]"
            ).lower()
            if yn == "y":
                pass
            elif yn == "n":
                print("Bai!")
                sys.exit(0)
            else:
                print("Huh?")
                sys.exit(1)
    destination.mkdir(parents=True, exist_ok=True)

    for item in tempdir.iterdir():
        if item.name == ".recipe":
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)

    shutil.rmtree(tempdir)
    print(f"Syrup poured into {destination}!")


def get_token():
    """Get the saved token from file."""
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, 'r') as f:
            return f.read().strip()
    return None


def save_token(token):
    """Save token to file."""
    with open(TOKEN_FILE, 'w') as f:
        f.write(token)


def delete_token():
    """Delete saved token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def login():
    """Login to the server."""
    print("Enter username:")
    username = input("> ")
    print("Enter password:")
    password = input("> ")
    
    data = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{SERVER_URL}/api/login",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            token = result.get("token")
            if token:
                save_token(token)
                print(f"Logged in as {username}. Token saved.")
            else:
                print("Login failed: No token received")
    except urllib.error.HTTPError as e:
        error = json.loads(e.read().decode())
        print(f"Login failed: {error.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"Connection error: {e}")


def register():
    """Register a new account on the server."""
    print("Choose a username:")
    username = input("> ")
    print("Choose a password:")
    password = input("> ")
    
    data = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{SERVER_URL}/api/register",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            token = result.get("token")
            if token:
                save_token(token)
                print(f"Registered as {username}. Token saved.")
            else:
                print("Registration failed: No token received")
    except urllib.error.HTTPError as e:
        error = json.loads(e.read().decode())
        print(f"Registration failed: {error.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"Connection error: {e}")


def logout():
    """Logout from the server."""
    token = get_token()
    if not token:
        print("No active session.")
        return
    
    req = urllib.request.Request(
        f"{SERVER_URL}/api/logout",
        method="POST",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            delete_token()
            print("Logged out successfully.")
    except urllib.error.HTTPError as e:
        delete_token()
        print("Logged out locally (server may have already invalidated token).")
    except Exception as e:
        delete_token()
        print(f"Logout error: {e}")


def send_package(filepath=None):
    """Send a .syp file to the server."""
    token = get_token()
    if not token:
        print("Not logged in. Please login first with 'syrup login'.")
        return
    
    # Get filepath from argument or prompt
    if not filepath:
        if len(sys.argv) > 2:
            filepath = sys.argv[2]
        else:
            print("Enter path to .syp file:")
            filepath = input("> ")
    
    filepath = pathlib.Path(filepath).expanduser()
    if not filepath.exists():
        print(f"File not found: {filepath}")
        return
    
    if not filepath.suffix == ".syp":
        print("Warning: File is not a .syp file")
    
    # Check file size (2GB limit)
    file_size = filepath.stat().st_size
    if file_size > MAX_PACKAGE_SIZE_BYTES:
        max_gb = CONFIG.get("limits", {}).get("max_package_size_gb", 2)
        print(f"Error: File size ({file_size / (1024**3):.2f} GB) exceeds maximum allowed size ({max_gb} GB)")
        return
    
    # Get package name
    package_name = filepath.stem
    
    # Read file content
    with open(filepath, 'rb') as f:
        file_content = f.read()
    
    # Send to server
    req = urllib.request.Request(
        f"{SERVER_URL}/api/upload",
        data=file_content,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "X-Package-Name": package_name
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            print(f"Package uploaded: {result.get('filename', package_name)}")
    except urllib.error.HTTPError as e:
        error = json.loads(e.read().decode())
        print(f"Upload failed: {error.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"Connection error: {e}")


def install_from_server(package_spec):
    """Install a package from the server using @username/rice format."""
    # Parse @username/rice format
    match = re.match(r'@([^/]+)/(.+)', package_spec)
    if not match:
        print("Invalid package specification. Use @username/rice format.")
        return
    
    username = match.group(1)
    package_name = match.group(2)
    
    print(f"Downloading {package_name} from @{username}...")
    
    # Download from server
    download_url = f"{SERVER_URL}/api/download/{username}/{package_name}"
    
    # Get download directory from config
    download_dir = pathlib.Path(CONFIG["client"]["download_dir"]).expanduser()
    download_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        req = urllib.request.Request(download_url)
        with urllib.request.urlopen(req) as response:
            # Save to download directory
            temp_file = download_dir / f"{package_name}.syp"
            with open(temp_file, 'wb') as f:
                f.write(response.read())
            
            print(f"Downloaded to {temp_file}, installing...")
            
            # Install the downloaded package
            install(str(temp_file))
            
            # Clean up
            temp_file.unlink()
            
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode()
        try:
            error = json.loads(error_msg)
            print(f"Download failed: {error.get('error', 'Unknown error')}")
        except:
            print(f"Download failed: HTTP {e.code}")
    except Exception as e:
        print(f"Connection error: {e}")


def main():
    try:
        if sys.argv[1] == "package":
            pkg()
        elif sys.argv[1] == "install":
            if sys.argv[2]:
                install(sys.argv[2])
        elif sys.argv[1] == "send":
            send_package()
        elif sys.argv[1] == "login":
            login()
        elif sys.argv[1] == "register":
            register()
        elif sys.argv[1] == "logout":
            logout()
        else:
            print(
                "Syrup\ninstall - Installs a .syp file.\npackage - Packages a folder into a .syp file.\nsend - Sends a .syp to the server (requires login)\nlogin - Login to server\nregister - Register new account\nlogout - Logout from server\nExamples:\nsyrup install rice.syp\nsyrup install @username/rice\nsyrup package\nsyrup send myrice.syp"
            )
    except IndexError:
        print(ascii)
        print("""
----------------[Commands]----------------
[install --- Installs a .syp file]
[package --- Package a folder into a .syp]
[send ------ Send a .syp to the server]
[login ----- Login to server]
[register -- Register new account]
[logout ---- Logout from server]
            """)
    except KeyboardInterrupt:
        print("\n")
        sys.exit()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import datetime
import json
import pathlib
import platform
import shutil
import subprocess
import sys

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
    syrup = pathlib.Path(syrup).expanduser()
    if not syrup.exists():
        print("File not found.")
        return

    tempdir = pathlib.Path("./temp_syrup")
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


def main():
    try:
        if sys.argv[1] == "package":
            pkg()
        elif sys.argv[1] == "install":
            if sys.argv[2]:
                install(sys.argv[2])
        else:
            print(
                "Syrup\ninstall - Installs a .syp file.\npackage - Packages a folder into a .syp file.\nExamples:\nsyrup install rice.syp\nsyrup package"
            )
    except IndexError:
        print(ascii)
        print("""
----------------[Commands]----------------
[install --- Installs a .syp file]
[package --- Package a folder into a .syp]
            """)
    except KeyboardInterrupt:
        print("\n")
        sys.exit()


if __name__ == "__main__":
    main()

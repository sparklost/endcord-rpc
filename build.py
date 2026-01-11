import argparse
import importlib.metadata
import importlib.util
import os
import shutil
import subprocess
import sys
import tomllib


def get_app_name():
    """Get app name from pyproject.toml"""
    if os.path.exists("pyproject.toml"):
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        if "project" in data and "version" in data["project"]:
            return str(data["project"]["name"])
        print("App name not specified in pyproject.toml")
        sys.exit()
    print("pyproject.toml file not found")
    sys.exit()


def get_version_number():
    """Get version number from pyproject.toml"""
    if os.path.exists("pyproject.toml"):
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        if "project" in data and "version" in data["project"]:
            return str(data["project"]["version"])
        print("Version not specified in pyproject.toml")
        sys.exit()
    print("pyproject.toml file not found")
    sys.exit()


def supports_color():
    """Return True if the running terminal supports ANSI colors."""
    if sys.platform == "win32":
        return (os.getenv("ANSICON") is not None or
            os.getenv("WT_SESSION") is not None or
            os.getenv("TERM_PROGRAM") == "vscode" or
            os.getenv("TERM") in ("xterm", "xterm-color", "xterm-256color")
        )
    if not sys.stdout.isatty():
        return False
    return os.getenv("TERM", "") != "dumb"


PKGNAME = get_app_name()
PKGVER = get_version_number()
USE_COLOR = supports_color()


def fprint(text, color_code="\033[1;35m", prepend=f"[{PKGNAME.capitalize()} Build Script]: "):
    """Print colored text prepended with text, default is light purple"""
    if USE_COLOR:
        print(f"{color_code}{prepend}{text}\033[0m")
    else:
        print(f"{prepend}{text}")


def check_dev():
    """Check if its dev environment and set it up"""
    if importlib.util.find_spec("PyInstaller") is None or importlib.util.find_spec("nuitka") is None:
        subprocess.run(["uv", "sync", "--group", "build"], check=True)


def build_third_party_licenses(exclude=[]):
    """Collect and build all lincenses found in venv into THIRD_PARTY_LICENSES.txt file"""
    fprint("Building list of third party licenses")
    subprocess.run(["uv", "pip", "install", "pip-licenses"], check=True)
    command = [
        "uv", "run", "pip-licenses",
        "--ignore-packages " + " ".joind(exclude),
        "--format=plain-vertical",
        "--no-license-path",
        "--output-file=THIRD_PARTY_LICENSES.txt",
    ]
    subprocess.run(command, check=True)
    subprocess.run(["uv", "pip", "uninstall", "pip-licenses", "prettytable", "wcwidth"], check=True)


def build_with_pyinstaller(onedir):
    """Build with pyinstaller"""
    pkgname = PKGNAME
    mode = "--onedir" if onedir else "--onefile"
    hidden_imports = ["--hidden-import=uuid"]
    exclude_imports = [
        "--exclude-module=cython",
        "--exclude-module=zstandard",
    ]
    package_data = []

    # platform-specific
    if sys.platform == "linux":
        options = []
    elif sys.platform == "win32":
        options = ["--console"]
        hidden_imports += ["--hidden-import=win32timezone"]
    elif sys.platform == "darwin":
        options = []

    # prepare command and run it
    cmd = [
        "uv", "run", "python", "-m", "PyInstaller",
        mode,
        *hidden_imports,
        *exclude_imports,
        *package_data,
        *options,
        "--noconfirm",
        "--clean",
        f"--name={pkgname}",
        "main.py",
    ]
    cmd = [arg for arg in cmd if arg != ""]
    fprint("Starting pyinstaller")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(e.returncode)

    # cleanup
    fprint("Cleaning up")
    try:
        os.remove(f"{pkgname}.spec")
        shutil.rmtree("build")
    except FileNotFoundError:
        pass
    fprint(f"Finished building {pkgname}")


def build_with_nuitka(onedir, clang, mingw):
    """Build with nuitka"""
    pkgname = PKGNAME
    mode = "--standalone" if onedir else "--onefile"
    compiler = ""
    if clang:
        compiler = "--clang"
    elif mingw:
        compiler = "--mingw64"
    python_flags = ["--python-flag=-OO"]
    hidden_imports = ["--include-module=uuid"]
    # excluding zstandard because its nuitka dependency bu also urllib3 optional dependency, and uses lots of space
    exclude_imports = [
        "--nofollow-import-to=cython",
        "--nofollow-import-to=zstandard",
        "--nofollow-import-to=google._upb",
    ]
    package_data = []

    # options
    if clang:
        os.environ["CFLAGS"] = "-Wno-macro-redefined"

    # platform-specific
    if sys.platform == "linux":
        options = []
    elif sys.platform == "win32":
        options = ["--assume-yes-for-downloads"]
        hidden_imports += [
            "--include-package=winrt.windows.foundation",
            "--include-package=winrt.windows.ui.notifications",
            "--include-package=winrt.windows.data.xml.dom",
            "--include-package=win32timezone",
        ]
        package_data += ["--include-package-data=winrt"]
    elif sys.platform == "darwin":
        options = [
            f"--macos-app-name={PKGNAME}",
            f"--macos-app-version={get_version_number()}",
            "--macos-app-protected-resource=NSMicrophoneUsageDescription:Microphone access for recording voice message.",
        ]

    # prepare command and run it
    cmd = [
        "uv", "run", "python", "-m", "nuitka",
        mode,
        compiler,
        *python_flags,
        *hidden_imports,
        *exclude_imports,
        *package_data,
        *options,
        "--remove-output",
        "--output-dir=dist",
        f"--output-filename={pkgname}",
        "main.py",
    ]
    cmd = [arg for arg in cmd if arg != ""]
    fprint("Starting nuitka")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(e.returncode)

    # cleanup
    fprint("Cleaning up")
    try:
        os.remove(f"{pkgname}.spec")
        shutil.rmtree("build")
    except FileNotFoundError:
        pass
    fprint(f"Finished building {pkgname}")


def parser():
    """Setup argument parser for CLI"""
    parser = argparse.ArgumentParser(
        prog="build.py",
        description=f"build script for {PKGNAME}",
    )
    parser._positionals.title = "arguments"
    parser.add_argument(
        "--nuitka",
        action="store_true",
        help="build with nuitka, takes a long time, but more optimized executable",
    )
    parser.add_argument(
        "--clang",
        action="store_true",
        help="use clang when building with nuitka",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="build into directory instead single executable",
    )
    parser.add_argument(
        "--mingw",
        action="store_true",
        help="use mingw instead msvc on windows, has no effect on Linux and macOS, or with --clang flag",
    )
    parser.add_argument(
        "--build-licenses",
        action="store_true",
        help="build file containing licenses from all used third party libraries",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parser()

    check_dev()

    if sys.platform not in ("linux", "win32", "darwin"):
        sys.exit(f"This platform is not supported: {sys.platform}")

    if args.build_licenses:
        exclude = ["ordered-set", "zstandard", "altgraph", "packaging", "pyinstaller-hooks-contrib", "packaging", "setuptools"]
        build_third_party_licenses(exclude)

    if args.nuitka:
        build_with_nuitka(args.onedir, args.clang, args.mingw)
    else:
        build_with_pyinstaller(args.onedir)

    sys.exit()

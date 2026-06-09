import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tomllib

PYTHON_MAX_MINOR = 14
PYTHON_FREETHREADED = 14
PYTHON_LAST_SAFE = 13

CUSTOM_CFLAGS = [
    "-DNDEBUG",
    "-g0",
    "-O3",
    "-march=x86-64",
    "-mtune=generic",
    "-fno-semantic-interposition",
    "-fno-strict-overflow",
    "-fvisibility=hidden",
    # "-flto=thin",
]
CUSTOM_CXXFLAGS = CUSTOM_CFLAGS
CUSTOM_LDFLAGS = [
    "-Wl,-s",
    "-Wl,-O1",
    "-Wl,--sort-common",
    "-Wl,--as-needed",
    "-Wl,-z,pack-relative-relocs",
    "-Wl,--exclude-libs,ALL",
    # "-flto=thin",
]
CFLAGS_OLD = os.environ.get("CFLAGS", "")
CXXFLAGS_OLD = os.environ.get("CFLAGS", "")
LDFLAGS_OLD = os.environ.get("CFLAGS", "")

def get_app_name():
    """Get app name from pyproject.toml"""
    if os.path.exists("pyproject.toml"):
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        if "project" in data and "version" in data["project"]:
            return str(data["project"]["name"])
        print("App name not specified in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    print("pyproject.toml file not found", file=sys.stderr)
    sys.exit(1)


def get_version_number():
    """Get version number from pyproject.toml"""
    if os.path.exists("pyproject.toml"):
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        if "project" in data and "version" in data["project"]:
            return str(data["project"]["version"])
        print("Version not specified in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    print("pyproject.toml file not found", file=sys.stderr)
    sys.exit(1)


def is_gil_enabled():
    """Safely check if GIL is enabled"""
    try:
        return sys._is_gil_enabled()
    except AttributeError:
        return True


def get_python_version():
    """Get python major and minor versions"""
    if shutil.which("uv"):
        try:
            version_result = subprocess.run(["uv", "run", "--no-sync", "python", "-VV"], capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"uv error: {e}", file=sys.stderr)
            return sys.version_info.major, sys.version_info.minor, is_gil_enabled()
        all_parts = version_result.stdout.strip().split(" ")
        version_parts = all_parts[1].split(".")
        if len(version_parts) < 2:
            return sys.version_info.major, sys.version_info.minor, is_gil_enabled()
        return int(version_parts[0]), int(version_parts[1]), "free-threading" in all_parts[2]
    return sys.version_info.major, sys.version_info.minor, is_gil_enabled()


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


def check_python():
    """Check python version and print warning, and return True if runing inside pure python (no uv)"""
    if sys.version_info.major != 3:
        print(f"Python {sys.version_info.major} is not supported. Only Python 3 is supported.", file=sys.stderr)
        sys.exit(1)

    if os.environ.get("UV", ""):
        if sys.version_info.minor < 12 or sys.version_info.minor > PYTHON_MAX_MINOR:
            fprint(f'WARNING: Python {sys.version_info.major}.{sys.version_info.minor} is not supported but build may succeed. Run "python build.py" to let uv download and setup recommended temporary python interpreter.', color_code="\033[1;31m")
        else:
            try:
                version = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=True)
                fprint(f"Using {version.stdout.strip()}")
            except Exception:
                pass
            fprint(f"Using Python {sys.version}")
        if not is_gil_enabled():
            if sys.version_info.minor == PYTHON_FREETHREADED:
                fprint("WARNING: While endcord works with freethreaded python, final binary is much larger. Nutka doesnt yet support freethreaded python, so build is likely to fail.", color_code="\033[1;31m")
            else:
                fprint(f'WARNING: Endcord is known to only build with freethreaded python version 3.{PYTHON_FREETHREADED}. Buil is likely to fail on other versions. Run "python build.py" to let uv download and setup recommended temporary python interpreter, optionally with flag "--freethreaded".', color_code="\033[1;31m")
        return False

    try:
        version = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"uv error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("uv command not found, please ensure uv is installed and in PATH", file=sys.stderr)
        sys.exit(1)
    return True


def ensure_python(freethreaded, safe=False):
    """Check current python and download correct python if needed"""
    if safe:
        selected_version = PYTHON_LAST_SAFE
    else:
        selected_version = PYTHON_MAX_MINOR

    _, minor, have_freethreaded = get_python_version()
    if minor == selected_version and freethreaded == have_freethreaded:
        return None, have_freethreaded

    if freethreaded:
        version = f"3.{PYTHON_FREETHREADED}+freethreaded"
    else:
        version = f"3.{selected_version}"
        # ensure there is no same-name freethreaded python
        subprocess.run(["uv", "python", "uninstall", f"3.{minor}+freethreaded"], check=False)

    freethreaded_string = "freethreaded " if freethreaded else ""
    fprint(f"Setting up {freethreaded_string}python {version} for this project")
    subprocess.run(["uv", "python", "install", version], check=True)

    return version, have_freethreaded or freethreaded


def check_dev():
    """Check if its dev environment and set it up"""
    if importlib.util.find_spec("PyInstaller") is None or importlib.util.find_spec("nuitka") is None:
        subprocess.run(["uv", "sync", "--group", "build"], check=True)


def force_ujson():
    """Remove orjson and force installing ujson instead. WARNING: this modifies pyproject.toml"""
    try:
        subprocess.run(["uv", "remove", "orjson"], check=True, stderr=subprocess.DEVNULL)
        fprint("Switching orjson -> ujson   !! pyproject.toml is modified !!", color_code="\033[1;31m")
        subprocess.run(["uv", "add", "ujson"], check=True)
    except subprocess.CalledProcessError:
        pass


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


def setup_compiler(clang, clear=False, overwrite=False, cflags=[], ldflags=[], cxxflags=[]):
    """Set compiler and its flags in environment variables"""
    if clang:
        os.environ["CC"] = "clang"
        os.environ["CXX"] = "clang++"
        os.environ["LD"] = "lld"
    if clear:
        os.environ["CFLAGS"] = CFLAGS_OLD
        os.environ["CXXFLAGS"] = CXXFLAGS_OLD
        os.environ["LDFLAGS"] = LDFLAGS_OLD
        return [], [], []
    cflags = ([] if overwrite else CFLAGS_OLD.split(" ")) + CUSTOM_CFLAGS + cflags
    cxxflags = ([] if overwrite else CXXFLAGS_OLD.split(" ")) + CUSTOM_CXXFLAGS + cxxflags
    ldflags = ([] if overwrite else LDFLAGS_OLD.split(" ")) + CUSTOM_LDFLAGS + ldflags
    if shutil.which("lld") and clang:
        ldflags.append("-fuse-ld=lld")
    os.environ["CFLAGS"] = " ".join(cflags)
    os.environ["CXXFLAGS"] = " ".join(cxxflags)
    os.environ["LDFLAGS"] = " ".join(ldflags)
    return cflags, cxxflags, ldflags


def build_with_pyinstaller(onedir, print_cmd=False):
    """Build with pyinstaller"""
    pkgname = PKGNAME
    mode = "--onedir" if onedir else "--onefile"
    hidden_imports = ["--hidden-import=uuid"]
    exclude_imports = [
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
    if print_cmd:
        print(" ".join(cmd))
        sys.exit(0)
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


def build_with_nuitka(onedir, clang, mingw, print_cmd=False):
    """Build with nuitka"""
    clang = clang or os.environ.get("CC") == "clang"
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
        "--nofollow-import-to=zstandard",
        "--nofollow-import-to=google._upb",
    ]
    package_data = []

    setup_compiler(clang)

    # options
    if clang:
        os.environ["CFLAGS"] = "-Wno-macro-redefined"

    # platform-specific
    if sys.platform == "linux":
        options = []
    elif sys.platform == "win32":
        options = ["--assume-yes-for-downloads"]
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
    if print_cmd:
        print(" ".join(cmd))
        sys.exit(0)
    fprint("Starting nuitka")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(e.returncode)

    # cleanup
    fprint("Cleaning up")
    try:
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
        "--noclang",
        action="store_true",
        help="script prefers clang if its installed, set this to not use it, or change CC and LD env vars",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="build into directory instead single executable",
    )
    parser.add_argument(
        "--mingw",
        action="store_true",
        help="use mingw instead msvc on windows, has no effect on Linux and macOS",
    )
    parser.add_argument(
        "--freethreaded",
        action="store_true",
        help="build with freethreaded python, will noticeably improve terminal media player performance at the cost of much larger binary",
    )
    parser.add_argument(
        "--safe",
        action="store_true",
        help=f"Use python 3.{PYTHON_LAST_SAFE} which is known to build endcord without any issues",
    )
    parser.add_argument(
        "--nobuild",
        action="store_true",
        help="only configure environment, but dont build endcord",
    )
    parser.add_argument(
        "--print-cmd",
        action="store_true",
        help="print build command for nuitka or pyinstaller and exit",
    )
    parser.add_argument(
        "--build-licenses",
        action="store_true",
        help="build file containing licenses from all used third party libraries",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parser()
    clang = not (args.noclang or args.mingw)

    if args.print_cmd:
        if args.nuitka:
            build_with_nuitka(args.onedir, args.clang, args.mingw, print_cmd=True)
        else:
            build_with_pyinstaller(args.onedir, print_cmd=True)
        sys.exit(0)

    if check_python():
        version, freethreaded = ensure_python(args.freethreaded, args.safe)
        if version:
            if freethreaded:
                force_ujson()
            os.execvp("uv", ["uv", "run", "-p", version, *sys.argv])
        else:
            os.execvp("uv", ["uv", "run", *sys.argv])
        sys.exit(0)

    if args.freethreaded:
        force_ujson()

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

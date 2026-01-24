# Endcord-RPC
Small RPC server made from parts of [endcord](https://github.com/sparklost/endcord). Provides Rich Presence and game detection only.


## Features
- Rich Presence
- Game detection
- Extremely small RAM, CPU and storage usage
- Automatic reconnect
- Configurable game detection blacklist


## Installing
### Linux
- Pre-built binaries (built with nuitka using clang) are available in releases.  
    Binaries are built on Ubuntu-like distro.
- From AUR: `yay -S endcord-rpc`
- [Build](#building) endcord-rpc, then copy built executable to system:  
    `sudo cp dist/endcord-rpc /usr/local/bin/`

### Windows
- Pre-built binaries (built with nuitka using clang) are available in releases.  
- [Build](#building) endcord-rpc, standalone executable can be found in `./dist/`  


## Building
To see all build script options, run: `uv run build.py -h`.  
To build into directory, not as a single executable, add `--onedir` flag. Will speed up startup.  
To build with Nuitka, add `--nuitka` flag. Optimized, smaller executable, long compile time. See [Nuitka](#nuitka) for more info.  
If you want to build without `orjson` (uses rust), run `uv remove orjson` for the first time, before running anything else. This will make it fallback to standard json (more CPU usage by game detection). Optionally it can use `ujson`, run `uv add ujson` to install it.  

### Linux
1. Clone this repository: `git clone https://github.com/sparklost/endcord-rpc.git`
2. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
3. `cd endcord-rpc`
4. run build script: `uv run build.py`  

### Windows
1. Install [Python](https://www.python.org/) 3.13 or later
2. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
3. Clone this repository, unzip it
4. Open terminal, cd to unzipped folder
5. run build script: `uv run build.py`

### Nuitka
To enable building with Nuitka, add `--nuitka` flag (takes a long time).  
Nuitka built binaries are much more optimized and can play videos at higher framerate.  
Optionally, add `--clang` flag to tell nuitka to compile using llvm, which might run even faster.  
Nuitka requirements:
- on Linux: GCC or clang and `patchelf` package
- on Windows: [Visual Studio 2022](https://www.visualstudio.com/en-us/downloads/download-visual-studio-vs.aspx) or mingw (will be downloaded by nuitka)


## Configuration
Settings, logs and data location:
- On Linux: `~/.config/endcord-rpc/` or `$XDG_DATA_HOME/endcord-rpc/`  
- On Windows: `%USERPROFILE%/AppData/Local/endcord-rpc/`  

### Config options (config.json)
- `"token": ""`  
    Put your token inside `""`. See [Token](#Token) for more info on obtaining your Discord token.  
- `"game_detection": True`  
    Enable game detection service.
- `"games_blacklist": []`  
    A list of apps to not be sent as discord presence. List must be of format: `["APP_ID_1", "APP_ID_2"]`.  
    `APP_ID_N` can be obtained in lig or in console when this app gets detected by endcord-rpc.
- `game_detection_download_delay = 7`  
    How often detectable games list will be checked for updates. Value is in days. Set to 0 to check on each run.
- `"proxy": None`  
    Proxy URL to use, it must be this format: `protocol://host:port`, example: `socks5://localhost:1080`.  
    Supported proxy protocols: `http`, `socks5`.  
    Be warned! Using proxy (especially TOR) might make you more suspicious to discord.  
    Voice and video calls will only work with socks5 proxy and it must support UDP ASSOCIATE.  
- `"custom_host": null`  
    Custom host to connect to, like `old.server.spacebar.chat`. Set to `null` to use default host (`discord.com`)
`"client_properties": "default"`  
    Client properties are used by discord in spam detection system. They contain various system information like operating system and browser user agent. There are 2 options available: `"default"` and `"anonymous"`.  
    - `"default"` - Approximately what official desktop client sends. Includes: OS version, architecture, Linux window manager, locale.  
    - `"anonymous"` - Approximately what official web client sends. But there is higher risk to trigger spam heuristics.  
`"custom_user_agent": None`  
    Custom [user agent string](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/User-Agent) for `client_properties`.  
    Default user agent is Firefox for `"anonymous"` and discord desktop client for `default` client properties.  
    User agent should not be changed unless the [default ones](https://github.com/sparklost/endcord/blob/main/endcord/client_properties.py) are very outdated.  
    Setting wrong user agent can make you more suspicious to discord spam filter! Make sure user agent string matches your OS.  

To set "debug" log level, run `export LOG_LEVEL=DEBUG ` before starting endcord-rpc.


### Token
Token is used to access Discord through your account without logging-in.  
It is required to use endcord-rpc.  
Obtaining your Discord token:
1. Open Discord in browser.
2. Open developer tools (`F12` or `Ctrl+Shift+I` on Chrome and Firefox).
3. Go to the `Network` tab then refresh the page.
4. In the 'Filter URLs' text box, search `discord.com/api`.
5. Click on any filtered entry. On the right side, switch to `Header` tab, look for `Authorization`.
6. Copy value of `Authorization: ...` found under `Request Headers` (right click -> Copy Value)
7. This is your discord token. **Do not share it!**

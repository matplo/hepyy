import pathlib
import sys

import click

from .config import get_build_dir, get_packages_dir, get_registry_path


# ---------------------------------------------------------------------------
# Shell-completion helpers (used by install / uninstall / info / env)
# ---------------------------------------------------------------------------

def _complete_available(ctx, param, incomplete):
    """Complete with available recipe names (built-in + remote sources)."""
    try:
        from click.shell_completion import CompletionItem
        from .recipe import list_builtin_recipes
        from .recipe_sources import list_all_remote_recipes
        names = {n for n, _ in list_builtin_recipes()}
        try:
            names.update(n for n, _, _ in list_all_remote_recipes())
        except Exception:
            pass
        return [CompletionItem(n) for n in sorted(names) if n.startswith(incomplete)]
    except Exception:
        return []


def _complete_installed(ctx, param, incomplete):
    """Complete with installed package names (from registry)."""
    try:
        from click.shell_completion import CompletionItem
        from .registry import get_registry
        return [CompletionItem(n) for n in sorted(get_registry().all_packages())
                if n.startswith(incomplete)]
    except Exception:
        return []


@click.group()
@click.version_option(message="%(prog)s %(version)s")
def cli():
    """hepyy — HEP C++ package manager with cppyy bindings."""
    ctx = click.get_current_context()
    if ctx.invoked_subcommand not in (None, "init") and not get_registry_path().exists():
        click.echo("[heyy] first run — initializing ...", err=True)
        _do_init_with_stdout_redirected_to_stderr()


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("packages", nargs=-1, required=True, shell_complete=_complete_available)
@click.option("--version", "-v", default=None, help="Package version (single-package installs only).")
@click.option("--recipe", "recipe_path", default=None, help="Path to a YAML recipe file (single-package installs only).")
@click.option("--force", is_flag=True, help="Re-extract source and rebuild (keeps cached tarball).")
@click.option("--redownload", is_flag=True, help="Delete cached tarball and re-download before rebuilding.")
@click.option("--clean", is_flag=True, help="Clean build artifacts and rebuild, keeping the extracted source tree.")
@click.option("--verbose", is_flag=True, help="Show build output in terminal.")
@click.option("--njobs", "-j", default=None, type=int, help="Override parallel make jobs (overrides recipe default of 4).")
@click.option("--set", "-s", "set_vars", multiple=True, metavar="KEY=VALUE",
              help="Override a Jinja2 template variable in the build script (e.g. --set WITH_GPU=1).")
def install(packages, version, recipe_path, force, redownload, clean, verbose, njobs, set_vars):
    """Download, build, and register one or more HEP C++ packages (in order)."""
    from .builder import build_package
    extra_vars = dict(kv.split("=", 1) for kv in set_vars if "=" in kv)
    for i, package in enumerate(packages):
        # --version and --recipe only apply when a single package is given
        _version = version if len(packages) == 1 else None
        _recipe_path = recipe_path if len(packages) == 1 else None
        if len(packages) > 1:
            click.echo(f"\n[{i+1}/{len(packages)}] Installing {package} ...")
        build_package(package, version=_version, recipe_path=_recipe_path, force=force, redownload=redownload, clean=clean, verbose=verbose, njobs=njobs, extra_vars=extra_vars)


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("package")
@click.option("--prefix", required=True, help="Path to the installed package prefix.")
@click.option("--recipe", "recipe_path", default=None, help="Path to a YAML recipe file.")
@click.option("--version", "-v", default=None, help="Version string (overrides recipe default).")
def register(package, prefix, recipe_path, version):
    """Register a pre-built package (no compilation)."""
    from .builder import register_package
    register_package(package, prefix, recipe_path=recipe_path, version=version)


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("package", shell_complete=_complete_installed)
@click.option("--keep-files", is_flag=True, default=False,
              help="Remove from registry only; leave the installed files on disk.")
def uninstall(package, keep_files):
    """Remove an installed package from the registry (and optionally its files)."""
    import shutil
    from .registry import get_registry
    from .shell import get_modulefiles_dir

    reg = get_registry()
    record = reg.get(package)
    if record is None:
        click.echo(f"Error: '{package}' is not in the registry.", err=True)
        sys.exit(1)

    version = record.get("version", "unknown")
    prefix = pathlib.Path(record["prefix"]) if record.get("prefix") else None

    # Remove TCL modulefile if present
    mod_file = get_modulefiles_dir() / package / version
    if mod_file.exists():
        mod_file.unlink()
        click.echo(f"Removed modulefile: {mod_file}")
        # Clean up empty parent dir
        try:
            mod_file.parent.rmdir()
        except OSError:
            pass

    # Remove installed files
    if not keep_files and prefix and prefix.exists():
        click.echo(f"Removing {prefix} ...")
        shutil.rmtree(prefix)
        click.echo(f"Removed prefix: {prefix}")
    elif keep_files:
        click.echo(f"Keeping files at {prefix} (--keep-files)")

    # Deregister
    reg.remove(package)
    click.echo(f"Uninstalled {package}/{version}.")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@cli.command(name="list")
def list_cmd():
    """Show all installed packages."""
    from .registry import get_registry
    reg = get_registry()
    pkgs = reg.all_packages()
    if not pkgs:
        click.echo("No packages installed. Run 'hepyy install <pkg>'.")
        return
    click.echo(f"{'Package':<20} {'Version':<12} Prefix")
    click.echo("-" * 70)
    for name, rec in pkgs.items():
        click.echo(f"{name:<20} {rec.get('version','?'):<12} {rec.get('prefix','?')}")


# ---------------------------------------------------------------------------
# avail
# ---------------------------------------------------------------------------

@cli.command()
def avail():
    """Show all available recipes (built-in + remote sources)."""
    from .recipe import list_builtin_recipes
    from .recipe_sources import list_all_remote_recipes

    click.echo("Built-in recipes:")
    for name, ver in list_builtin_recipes():
        click.echo(f"  {name}/{ver}")

    remote = list_all_remote_recipes()
    if remote:
        click.echo("\nRemote recipes:")
        for name, ver, src in remote:
            click.echo(f"  {name}/{ver}  [{src}]")


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("package", shell_complete=_complete_installed)
def info(package):
    """Show details for an installed package."""
    from .registry import get_registry
    rec = get_registry().get(package)
    if rec is None:
        click.echo(f"Package '{package}' is not installed.", err=True)
        sys.exit(1)
    for key, val in rec.items():
        if isinstance(val, list):
            click.echo(f"{key}:")
            for item in val:
                click.echo(f"  - {item}")
        else:
            click.echo(f"{key}: {val}")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def _do_init_with_stdout_redirected_to_stderr():
    """Run _do_init() with real fd 1 pointed at fd 2, then restore it.

    _do_init() (via recipe_sources.add_source's `git clone`/print and
    cppyy_fix's install_name_tool/print) writes some of its status text
    through bare print()/inherited-stdout subprocesses rather than
    click.echo(err=True), so a plain sys.stdout swap wouldn't catch it.
    Redirecting the actual OS file descriptor catches all of it — needed
    only for the *auto*-init path, since several heyy commands (shell-init,
    completion, modules) are meant to have their stdout captured with
    eval "$(...)", and this must never land inside that capture. The
    explicit 'heyy init' command calls _do_init() directly, unredirected,
    so its output stays on stdout as normal for an interactively-run command.
    """
    import os
    import sys
    sys.stdout.flush()
    saved_fd = os.dup(1)
    try:
        os.dup2(2, 1)
        _do_init()
    finally:
        sys.stdout.flush()
        os.dup2(saved_fd, 1)
        os.close(saved_fd)


def _do_init():
    """Create packages directory, registry skeleton, and check cppyy.

    Shared by the 'init' command and the auto-init path in cli() (which
    runs this once, quietly, on the first subcommand of a fresh env).

    All output goes to stderr: several heyy commands (shell-init, completion,
    modules) are designed to have their stdout captured by `eval "$(...)"`,
    and if auto-init fires underneath one of those, status text on stdout
    would corrupt the shell script being eval'd.
    """
    def echo(msg=""):
        click.echo(msg, err=True)

    pkg_dir = get_packages_dir()
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "logs").mkdir(exist_ok=True)
    (pkg_dir / "src").mkdir(exist_ok=True)
    reg_path = get_registry_path()
    if not reg_path.exists():
        import json
        reg_path.write_text(json.dumps({"schema_version": 1, "packages": {}}, indent=2))
        echo(f"Created registry: {reg_path}")
    else:
        echo(f"Registry already exists: {reg_path}")
    echo(f"Packages directory: {pkg_dir}")

    # Auto-register the canonical hepyy-recipes repo if not already present
    _RECIPES_REPO = "https://github.com/matplo/hepyy-recipes"
    from .recipe_sources import list_sources, add_source
    existing_urls = {s["url"] for s in list_sources()}
    if _RECIPES_REPO not in existing_urls:
        echo(f"\nFetching recipes from {_RECIPES_REPO} ...")
        try:
            add_source(_RECIPES_REPO)
        except Exception as exc:
            echo(f"  Warning: could not fetch recipes ({exc}). Run 'hepyy recipe update' later.")
    else:
        echo("Recipe source: already registered")

    # Check cppyy backend and auto-fix — only when libCling is inside this venv.
    # Importing cppyy_backend on shared HPC environments (where libCling lives
    # outside the venv) triggers PCH rebuilds that can loop indefinitely on
    # network filesystems. Skip the check entirely in that case.
    from .cppyy_fix import is_in_venv, libcling_in_venv, _find_libcling
    if is_in_venv():
        lib = _find_libcling()
        if lib is None:
            echo("cppyy backend: not found (cppyy not installed?)")
        elif libcling_in_venv(lib):
            from .cppyy_fix import fix_cppyy, check_cppyy, get_broken_deps
            if check_cppyy():
                echo("cppyy backend: OK")
            else:
                broken = get_broken_deps(lib)
                echo(f"\ncppyy backend: {len(broken)} broken library path(s) in {lib}:")
                for p in broken:
                    echo(f"  {p}")
                echo("Auto-fixing (library is inside this venv) ...")
                fixed = fix_cppyy(verbose=True)
                if fixed:
                    echo(f"cppyy patched successfully ({len(fixed)} path(s) fixed).")
                else:
                    echo(
                        "Could not auto-fix (install_name_tool / patchelf missing?).\n"
                        "Run 'hepyy fix-cppyy' to retry manually."
                    )
        else:
            echo("cppyy backend: skipping check (libCling is outside this venv — run 'hepyy fix-cppyy' if needed)")
    else:
        echo("cppyy backend: skipping check (not in a virtual environment)")

    # Clean up stale .pth from the pre-rename package (heppyyier → hepyy).
    # If the old package was uninstalled before installing hepyy, Python raises
    # ModuleNotFoundError on every startup until the stale file is removed.
    import sysconfig as _sc
    _site = pathlib.Path(_sc.get_paths()["purelib"])
    _stale = _site / "heppyyier_autoload.pth"
    if _stale.exists():
        _stale.unlink()
        echo(f"Removed stale heppyyier_autoload.pth from {_site}")

    # Regular (non-editable) installs already ship hepyy_autoload.pth at the
    # wheel root (see pyproject.toml force-include) — only editable/dev
    # installs (pip install -e .) need 'generate-modules' to write it.
    if not (_site / "hepyy_autoload.pth").exists():
        echo("\nRun 'heyy generate-modules' to enable 'module load' auto-loading.")


@cli.command()
def init():
    """Create packages directory, registry skeleton, and check cppyy."""
    _do_init()


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@cli.command("config")
def config_cmd():
    """Show active configuration (packages directory, registry, etc.)."""
    import os
    from .config import get_packages_dir, get_registry_path, get_log_dir

    pkg_dir = get_packages_dir()
    click.echo(f"packages_dir : {pkg_dir}")
    click.echo(f"registry     : {get_registry_path()}")
    click.echo(f"log_dir      : {get_log_dir()}")
    click.echo(f"src_dir      : {pkg_dir / 'src'}")
    # Show which config source was used
    if "HEPYY_PACKAGES_DIR" in os.environ:
        click.echo("(source: HEPYY_PACKAGES_DIR env var)")
    elif "HEPYY_BUILD_DIR" in os.environ:
        click.echo("(source: HEPYY_BUILD_DIR env var  [legacy])")
    elif (pathlib.Path.cwd() / ".hepyy.toml").exists():
        click.echo("(source: .hepyy.toml)")
    else:
        import sys
        from .config import _is_conda_env
        if sys.prefix != sys.base_prefix:
            click.echo(f"(source: active venv  {sys.prefix})")
        elif _is_conda_env():
            click.echo(f"(source: active conda env  {sys.prefix})")
        else:
            click.echo("(source: default  ./packages/)")


# ---------------------------------------------------------------------------
# fix-cppyy
# ---------------------------------------------------------------------------

@cli.command("fix-cppyy")
@click.option("--check", is_flag=True, help="Only check, do not patch.")
def fix_cppyy_cmd(check):
    """Detect and fix broken rpath entries in the cppyy backend (macOS)."""
    from .cppyy_fix import fix_cppyy, check_cppyy, _find_libcling, get_broken_deps
    lib = _find_libcling()
    if lib is None:
        click.echo("cppyy backend not found (is cppyy installed?).", err=True)
        sys.exit(1)
    click.echo(f"Backend: {lib}")
    broken = get_broken_deps(lib)
    if not broken:
        click.echo("All library paths are healthy — nothing to fix.")
        return
    click.echo(f"Found {len(broken)} broken path(s):")
    for p in broken:
        click.echo(f"  {p}")
    if check:
        return
    fixed = fix_cppyy(verbose=True)
    if fixed:
        click.echo(f"\ncppyy patched successfully ({len(fixed)} path(s) fixed).")
    else:
        click.echo("\nCould not fix all paths. Install missing libraries manually.", err=True)


# ---------------------------------------------------------------------------
# env
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("package", required=False, shell_complete=_complete_installed)
def env(package):
    """Print shell environment variables for a package (or all loaded)."""
    from .registry import get_registry
    reg = get_registry()
    targets = [package] if package else list(reg.all_packages().keys())
    for name in targets:
        rec = reg.get(name)
        if rec is None:
            continue
        prefix = rec["prefix"]
        NAME = name.upper().replace("-", "_")
        click.echo(f"export {NAME}_DIR={prefix!r}")
        click.echo(f"export PATH={prefix!r}/bin:$PATH")


# ---------------------------------------------------------------------------
# demos
# ---------------------------------------------------------------------------

_DEMOS_BASE = "https://raw.githubusercontent.com/matplo/hepyy/main/demos"
_DEMO_FILES = [
    "demo_fastjet.py",
    "demo_fjcontrib.py",
    "demo_pythia_fastjet.py",
    "demo_pythia_fastjet_root.py",
    "demo_pythia_fastjet_root_cppyy.py",
    "demo_fjcontrib.ipynb",
    "demo_pythia_fastjet.ipynb",
    "demo_pythia_fastjet_root.ipynb",
    "demo_softdrop_splitting.ipynb",
]

@cli.command()
@click.option("--dest", default="./hepyy_demos", show_default=True, help="Directory to download demos into.")
@click.option("--overwrite", is_flag=True, help="Overwrite existing files.")
def demos(dest, overwrite):
    """Download demo scripts from GitHub to the current directory."""
    import requests
    dest_path = pathlib.Path(dest).resolve()
    dest_path.mkdir(parents=True, exist_ok=True)
    for fname in _DEMO_FILES:
        out = dest_path / fname
        if out.exists() and not overwrite:
            click.echo(f"  skip  {fname}  (already exists, use --overwrite)")
            continue
        url = f"{_DEMOS_BASE}/{fname}"
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            out.write_bytes(r.content)
            click.echo(f"  ok    {fname}")
        else:
            click.echo(f"  fail  {fname}  (HTTP {r.status_code})", err=True)
    click.echo(f"\nDemos written to: {dest_path}")
    click.echo("Run: python demo_fastjet.py")


# ---------------------------------------------------------------------------
# shell-init
# ---------------------------------------------------------------------------

@cli.command("shell-init")
@click.option(
    "--shell", "shell_type",
    type=click.Choice(["bash", "zsh", "fish"]),
    default=None,
    help="Shell type (default: auto-detected from $SHELL).",
)
def shell_init(shell_type):
    """Print shell integration for eval — one-time setup, then it self-wires.

    \b
    Bash/zsh — add to ~/.bashrc / ~/.zshrc:
        eval "$(heyy shell-init)"

    \b
    Fish — add to ~/.config/fish/config.fish:
        heyy shell-init --shell fish | source

    Defines the 'module load/unload/list/avail' shim (bash/zsh) and a hook
    that re-wires completion + 'module use <modulefiles>' every time you
    activate or deactivate a venv/conda env — no per-env files, and it's a
    no-op wherever heyy isn't installed (including after 'pip uninstall').
    """
    import os
    from .shell import shell_init_script

    if shell_type is None:
        sh = os.environ.get("SHELL", "")
        shell_type = "fish" if "fish" in sh else ("zsh" if "zsh" in sh else "bash")

    click.echo(shell_init_script(shell_type), nl=False)


# ---------------------------------------------------------------------------
# completion
# ---------------------------------------------------------------------------

_COMPLETION_ALIASES = ["heyy", "her", "hepyy"]


def _bash_completion_script() -> str:
    """Generate a dynamic bash 3.2-compatible completion script.

    Package-name completions are evaluated at completion time by calling
    'heyy list' (installed) and 'heyy avail' (available) so they are
    always current without needing to re-source the script.
    """
    top_cmds = sorted(
        name for name in cli.commands.keys() if not name.startswith("_")
    )
    subcommand_map = {
        name: sorted(cmd.commands.keys())
        for name, cmd in cli.commands.items()
        if not name.startswith("_") and hasattr(cmd, "commands")
    }
    top_cmds_str = " ".join(top_cmds)

    lines = [
        "# hepyy bash completion — bash 3.2+ compatible, dynamic package names",
        "# Add to ~/.bashrc or ~/.zshrc:  eval \"$(heyy completion)\"",
        "",
        "_hepyy_avail_pkgs() {",
        "    heyy avail 2>/dev/null | awk '/^[[:space:]]+[a-zA-Z]/{split($1,a,\"/\"); print a[1]}' | sort -u",
        "}",
        "",
        "_hepyy_installed_pkgs() {",
        "    heyy list 2>/dev/null | awk 'NR>2 && /^[a-zA-Z]/{print $1}'",
        "}",
        "",
        "_hepyy_completion() {",
        "    local cur cmd",
        "    COMPREPLY=()",
        '    cur="${COMP_WORDS[COMP_CWORD]}"',
        '    cmd="${COMP_WORDS[1]}"',
        "",
        '    case "$cmd" in',
        "        install)",
        '            COMPREPLY=( $(compgen -W "$(_hepyy_avail_pkgs)" -- "$cur") )',
        "            return 0 ;;",
        "        uninstall|info|env)",
        '            COMPREPLY=( $(compgen -W "$(_hepyy_installed_pkgs)" -- "$cur") )',
        "            return 0 ;;",
    ]
    for group, subcmds in subcommand_map.items():
        lines.append(f"        {group})")
        lines.append(f'            COMPREPLY=( $(compgen -W "{" ".join(subcmds)}" -- "$cur") )')
        lines.append( "            return 0 ;;")
    lines += [
        "    esac",
        "",
        f'    COMPREPLY=( $(compgen -W "{top_cmds_str}" -- "$cur") )',
        "    return 0",
        "}",
        "",
    ]
    for alias in _COMPLETION_ALIASES:
        lines.append(f"complete -F _hepyy_completion {alias}")
    return "\n".join(lines) + "\n"


@cli.command("completion")
@click.option(
    "--shell", "shell_type",
    type=click.Choice(["bash", "zsh", "fish"]),
    default=None,
    help="Shell type (default: auto-detected from $SHELL).",
)
def completion(shell_type):
    """Print shell completion setup — pipe through eval to activate.

    \b
    Bash — add to ~/.bashrc:
        eval "$(heyy completion)"

    \b
    Zsh — add to ~/.zshrc:
        eval "$(heyy completion)"

    \b
    Fish — add to ~/.config/fish/config.fish:
        heyy completion --shell fish | source

    \b
    Completes: top-level commands, subcommands, installed package names
    (for uninstall / info / env), and available recipe names (for install).
    """
    import os

    if shell_type is None:
        sh = os.environ.get("SHELL", "")
        if "zsh" in sh:
            shell_type = "zsh"
        elif "fish" in sh:
            shell_type = "fish"
        else:
            shell_type = "bash"

    if shell_type == "fish":
        for alias in _COMPLETION_ALIASES:
            var = f"_{alias.upper()}_COMPLETE"
            click.echo(f"env {var}=fish_source {alias} | source")
    elif shell_type == "zsh":
        for alias in _COMPLETION_ALIASES:
            var = f"_{alias.upper()}_COMPLETE"
            click.echo(f'eval "$({var}=zsh_source {alias})"')
    else:
        # bash — hand-rolled for bash 3.2+ (macOS system bash) compatibility
        click.echo(_bash_completion_script())


@cli.command("modules")
def modules():
    """Print 'module use <path>' for the hepyy modulefiles directory.

    Usage: eval "$(heyy modules)"
    Then:  module load jewel/2.4.0
    """
    from .shell import get_modulefiles_dir
    click.echo(f"module use {get_modulefiles_dir()}")


@cli.command("modules-path")
def modules_path():
    """Print the hepyy modulefiles directory path (no 'module use' prefix)."""
    from .shell import get_modulefiles_dir
    click.echo(get_modulefiles_dir())


@cli.command("generate-modules")
def generate_modules():
    """Regenerate TCL modulefiles for all installed packages."""
    import pathlib
    from .shell import write_tcl_modulefile, get_modulefiles_dir, write_sitecustomize
    from .registry import get_registry
    reg = get_registry()
    count = 0
    for name, record in reg.all_packages().items():
        python_paths = record.get("python_paths")
        if python_paths is None:
            # Fallback for registry records written before python_paths was stored
            try:
                from .recipe import find_recipe
                r = find_recipe(name, version=record.get("version"))
                python_paths = r.python_paths
            except Exception:
                python_paths = []
        depends_on = record.get("depends_on") or []
        mod_file = write_tcl_modulefile(name, record["version"], pathlib.Path(record["prefix"]), python_paths=python_paths, depends_on=depends_on)
        click.echo(f"  wrote {mod_file}")
        count += 1
    if count == 0:
        click.echo("No installed packages found.")
    else:
        click.echo(f"\nModulefiles at: {get_modulefiles_dir()}")
        click.echo(f'Add to your shell:  eval "$(heyy modules)"')
    sc = write_sitecustomize()
    click.echo(f"sitecustomize.py refreshed: {sc}")


# ---------------------------------------------------------------------------
# upgrade / upgrade-from-gh
# ---------------------------------------------------------------------------

_HEPYY_GITHUB = "git+https://github.com/matplo/hepyy.git"


def _run_upgrade(source: str, label: str) -> None:
    """Shared logic for upgrade and upgrade-from-gh."""
    import shutil
    import subprocess

    pip = pathlib.Path(sys.executable).parent / "pip"
    uv = shutil.which("uv")

    if uv:
        cmd = [uv, "pip", "install", "--reinstall-package", "hepyy", source]
    else:
        cmd = [str(pip), "install", "--force-reinstall", "--no-deps", source]

    click.echo(f"Upgrading hepyy from {label} ...")
    click.echo(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        click.echo("Done. Restart your shell or re-enter the henv subshell to use the new version.")
    else:
        click.echo("Upgrade failed — check the output above.", err=True)
        sys.exit(result.returncode)


@cli.command()
def upgrade():
    """Upgrade hepyy to the latest release from PyPI."""
    _run_upgrade("hepyy", "PyPI")


@cli.command("upgrade-from-gh")
def upgrade_from_gh():
    """Upgrade hepyy from the latest commit on GitHub (bleeding edge)."""
    _run_upgrade(_HEPYY_GITHUB, "GitHub")


# ---------------------------------------------------------------------------
# _shell-env-path  (internal, called by the shell `module` function)
# ---------------------------------------------------------------------------

@cli.command("_shell-env-path", hidden=True)
@click.argument("name")
@click.argument("version", required=False, default=None)
def shell_env_path(name, version):
    """Internal: print prefix path for a package (used by shell module function)."""
    from .shell import env_path
    from .exceptions import PackageNotInstalledError
    try:
        p = env_path(name, version or None)
        click.echo(str(p))
    except PackageNotInstalledError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# _shell-list  (internal)
# ---------------------------------------------------------------------------

@cli.command("_shell-list", hidden=True)
def shell_list():
    """Internal: list shell-loaded packages from env vars."""
    from .shell import list_loaded
    loaded = list_loaded()
    if not loaded:
        click.echo("No packages currently loaded.")
    else:
        for name, version in loaded:
            click.echo(f"{name}/{version}")


# ---------------------------------------------------------------------------
# recipe subgroup
# ---------------------------------------------------------------------------

@cli.group()
def recipe():
    """Manage remote recipe sources."""


@recipe.command("add")
@click.argument("url")
def recipe_add(url):
    """Add a GitHub repo/directory as a recipe source."""
    from .recipe_sources import add_source
    add_source(url)


@recipe.command("remove")
@click.argument("url")
def recipe_remove(url):
    """Remove a recipe source."""
    from .recipe_sources import remove_source
    remove_source(url)


@recipe.command("list-sources")
def recipe_list_sources():
    """List all registered remote recipe sources."""
    from .recipe_sources import list_sources
    sources = list_sources()
    if not sources:
        click.echo("No remote sources registered. Use 'hepyy recipe add <url>'.")
        return
    for src in sources:
        subtree = f"  subtree: {src['subtree']}" if src.get("subtree") else ""
        click.echo(f"  {src['url']}{subtree}")
        click.echo(f"    added: {src['added_at']}")
        click.echo(f"    local: {src['local_path']}")


@recipe.command("update")
def recipe_update():
    """Update all remote recipe sources (git pull)."""
    from .recipe_sources import update_sources
    update_sources()


# ---------------------------------------------------------------------------
# kernel subgroup
# ---------------------------------------------------------------------------

@cli.group()
def kernel():
    """Manage Jupyter kernel registrations.

    \b
    Typical workflow:
      heyy kernel install            # create the kernel for this environment
      heyy kernel update             # refresh after 'heyy install <pkg>'
      heyy kernel list               # show registered hepyy kernels
      heyy kernel uninstall <name>   # remove a kernel (name from 'kernel list')

    Each henv/venv gets its own kernel named hepyy-<venv-name>, so
    multiple environments are automatically kept separate. Run 'kernel list'
    to see all registered kernels and their associated package directories.
    """


@kernel.command("install")
@click.option("--name", default=None, help="Kernel name slug used internally by Jupyter (default: hepyy-<venv-name>).")
@click.option("--display-name", "display_name", default=None,
              help="Human-readable name shown in JupyterHub/Lab (default: 'HEP (<pkg list>)').")
@click.option("--sys-prefix", "sys_prefix", is_flag=True, default=False,
              help="Install into sys.prefix so all users of this environment see the kernel; default installs for the current user only.")
def kernel_install(name, display_name, sys_prefix):
    """Create or refresh the hepyy Jupyter kernel spec.

    Embeds PATH, library paths, and PYTHONPATH for every installed package
    so notebooks work without any manual environment setup.

    Re-run this command after 'heyy install <pkg>' to pick up new packages.

    \b
    Examples:
      heyy kernel install
      heyy kernel install --name hep-dev --display-name "HEP dev env"
      heyy kernel install --sys-prefix   # shared JupyterHub install
    """
    from .kernel import install_kernel
    try:
        dest = install_kernel(name=name, display_name=display_name, user=not sys_prefix)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Read back kernel.json to report what was embedded
    import json
    spec = json.loads((dest / "kernel.json").read_text())
    click.echo(f"Kernel installed: {dest}")
    click.echo(f"  display name : {spec['display_name']}")
    click.echo(f"  python       : {spec['argv'][0]}")
    env = spec.get("env", {})
    if "HEPYY_PACKAGES_DIR" in env:
        click.echo(f"  packages dir : {env['HEPYY_PACKAGES_DIR']}")
    if "PATH" in env:
        click.echo(f"  PATH         : {env['PATH'][:80]}{'...' if len(env['PATH']) > 80 else ''}")
    click.echo(f"\nSelect '{spec['display_name']}' in JupyterHub/Lab to use it.")


@kernel.command("list")
def kernel_list():
    """List hepyy-managed Jupyter kernels.

    Shows only kernels created by 'heyy kernel install'. Columns: kernel
    name (pass to 'heyy kernel uninstall'), display name shown in
    JupyterHub/Lab, and the hepyy packages directory embedded in the spec.
    """
    from .kernel import list_kernels
    try:
        kernels = list_kernels()
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if not kernels:
        click.echo("No hepyy kernels installed. Run 'heyy kernel install' to create one.")
        return

    click.echo(f"{'Name':<30} {'Display name':<40} Packages dir")
    click.echo("-" * 100)
    for k in kernels:
        click.echo(f"{k['name']:<30} {k['display_name']:<40} {k['packages_dir']}")


@kernel.command("update")
@click.argument("name", required=False, default=None)
@click.option("--sys-prefix", "sys_prefix", is_flag=True, default=False,
              help="Re-install into sys.prefix (default: user install).")
def kernel_update(name, sys_prefix):
    """Refresh an existing hepyy kernel spec to pick up new packages.

    NAME is the kernel slug from 'heyy kernel list'. When omitted, the kernel
    for the current environment (hepyy-<venv-name>) is updated.

    Only the env block is meaningfully updated (PATH, PYTHONPATH, library
    paths). The kernel will be rewritten with the current Python interpreter,
    so run this from inside the same henv that originally created the kernel.

    \b
    Examples:
      heyy kernel update                        # refresh current venv's kernel
      heyy kernel update hepyy-henv-dev     # refresh a named kernel
    """
    from .kernel import update_kernel
    try:
        dest = update_kernel(name=name, user=not sys_prefix)
    except KeyError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except PermissionError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    import json
    spec = json.loads((dest / "kernel.json").read_text())
    click.echo(f"Kernel updated: {dest}")
    click.echo(f"  display name : {spec['display_name']}")
    click.echo(f"  python       : {spec['argv'][0]}")
    env = spec.get("env", {})
    if "HEPYY_PACKAGES_DIR" in env:
        click.echo(f"  packages dir : {env['HEPYY_PACKAGES_DIR']}")
    click.echo(f"\nSelect '{spec['display_name']}' in JupyterHub/Lab to use it.")


@kernel.command("uninstall")
@click.argument("name")
def kernel_uninstall(name):
    """Remove a hepyy-managed Jupyter kernel spec.

    NAME is the kernel slug shown in the first column of 'heyy kernel list'.
    Only kernels installed by hepyy can be removed this way; others are
    left untouched.

    \b
    Example:
      heyy kernel list                        # find the kernel name
      heyy kernel uninstall hepyy-myenv   # remove it
    """
    from .kernel import remove_kernel
    try:
        removed = remove_kernel(name)
    except KeyError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except PermissionError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Removed kernel '{name}': {removed}")


# ---------------------------------------------------------------------------
# Entry point — clean error messages, no tracebacks for known exceptions
# ---------------------------------------------------------------------------

def main():
    from .exceptions import RecipeNotFoundError, BuildError, PackageNotInstalledError
    try:
        rv = cli(standalone_mode=False)
        sys.exit(rv or 0)
    except (RecipeNotFoundError, BuildError, PackageNotInstalledError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except click.exceptions.Abort:
        sys.exit(1)
    except click.exceptions.Exit as exc:
        sys.exit(exc.exit_code)
    except click.exceptions.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)

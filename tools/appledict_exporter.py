#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Generic Apple Dictionary exporter using PyGlossary and Apple Dictionary Development Kit."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from zipfile import ZIP_DEFLATED, ZipFile

from pyglossary import Glossary
from tools.goldendict_exporter import DictEntry, DictInfo, DictVariables
from tools.printer import printer as pr


def find_ddk_path() -> Optional[Path]:
    """Find the path to the Apple Dictionary Development Kit directory.
    Checks environment variable DICT_BUILD_TOOL_DIR, user Developer folder,
    and standard system locations.
    """
    candidates = []

    # 1. Environment variable
    env_dir = os.environ.get("DICT_BUILD_TOOL_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    # 2. User Developer Extras (standard user installation)
    candidates.append(Path.home() / "Developer/Extras/Dictionary Development Kit")

    # 3. Utilities / System locations
    candidates.append(Path("/Applications/Utilities/Dictionary Development Kit"))
    candidates.append(Path("/Library/Developer/Extras/Dictionary Development Kit"))
    candidates.append(Path("/Applications/Dictionary Development Kit"))

    # 4. Workspace-local or repo-relative path
    candidates.append(Path(__file__).resolve().parent.parent / "Dictionary Development Kit")

    for p in candidates:
        if p and p.is_dir() and (p / "bin" / "build_dict.sh").is_file():
            return p

    return None


def clean_xhtml_for_appledict(html: str) -> str:
    """Extract clean body/fragment from HTML for Apple Dictionary XML."""
    if not html:
        return ""

    # Remove <!DOCTYPE>
    html = re.sub(r"<!DOCTYPE[^>]*>", "", html, flags=re.IGNORECASE)

    # Extract body content if <body> tag exists
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.IGNORECASE | re.DOTALL)
    if body_match:
        html = body_match.group(1)
    else:
        # Strip stray head or html tags
        html = re.sub(r"<head[^>]*>.*?</head>", "", html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r"</?html[^>]*>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"</?body[^>]*>", "", html, flags=re.IGNORECASE)

    # Remove any stray <h3> prefix if added by other exporters
    html = re.sub(r"^<h3>.*?</h3>", "", html.strip())

    # Replace &nbsp; with &#160; for strict XML compatibility
    html = html.replace("&nbsp;", "&#160;")

    clean_content = html.strip()
    if not clean_content.startswith("<div class=\"grammar_dict_entry\"") and not clean_content.startswith("<div class='grammar_dict_entry'"):
        clean_content = f'<div class="grammar_dict_entry">{clean_content}</div>'

    return clean_content


def get_apple_css_path(dict_var: DictVariables) -> Path:
    """Determine the CSS file to use for Apple Dictionary."""
    # Look for dedicated grammar_apple.css in project root
    project_root = Path(__file__).resolve().parent.parent
    apple_css = project_root / "grammar_apple.css"
    if apple_css.is_file():
        return apple_css

    # Fallback to grammar.css or first CSS in dict_var
    if dict_var.css_paths and dict_var.css_paths[0].is_file():
        return dict_var.css_paths[0]

    grammar_css = project_root / "grammar.css"
    if grammar_css.is_file():
        return grammar_css

    return apple_css


def write_custom_makefile(output_dir: Path, dict_name: str, ddk_dir: Optional[Path]) -> None:
    """Generate a clean, robust Makefile for building and installing with DDK."""
    ddk_path_str = str(ddk_dir) if ddk_dir else "/Applications/Utilities/Dictionary Development Kit"

    makefile_content = f"""# Makefile for Apple Dictionary: {dict_name}
DICT_NAME = {dict_name}
DICT_SRC_PATH = {dict_name}.xml
CSS_PATH = {dict_name}.css
PLIST_PATH = {dict_name}.plist
DICT_BUILD_OPTS =

DICT_BUILD_TOOL_DIR ?= {ddk_path_str}
DICT_BUILD_TOOL_BIN = $(DICT_BUILD_TOOL_DIR)/bin

DICT_DEV_KIT_OBJ_DIR = ./objects
export DICT_DEV_KIT_OBJ_DIR

DESTINATION_FOLDER = $(HOME)/Library/Dictionaries
RM = /bin/rm

all:
\t"$(DICT_BUILD_TOOL_BIN)/build_dict.sh" $(DICT_BUILD_OPTS) "$(DICT_NAME)" "$(DICT_SRC_PATH)" "$(CSS_PATH)" "$(PLIST_PATH)"
\t@echo "Done."

install:
\t@echo "Installing into $(DESTINATION_FOLDER)..."
\tmkdir -p "$(DESTINATION_FOLDER)"
\tditto --noextattr --norsrc "$(DICT_DEV_KIT_OBJ_DIR)/$(DICT_NAME).dictionary" "$(DESTINATION_FOLDER)/$(DICT_NAME).dictionary"
\ttouch "$(DESTINATION_FOLDER)"
\t@echo "Done. Restart Dictionary.app to see the dictionary."

clean:
\t$(RM) -rf "$(DICT_DEV_KIT_OBJ_DIR)"
"""
    makefile_path = output_dir / "Makefile"
    with open(makefile_path, "w", encoding="utf-8") as f:
        f.write(makefile_content)


def build_with_ddk(output_dir: Path, dict_name: str, ddk_dir: Path) -> Optional[Path]:
    """Invoke build_dict.sh from the Dictionary Development Kit."""
    build_script = ddk_dir / "bin" / "build_dict.sh"
    xml_file = f"{dict_name}.xml"
    css_file = f"{dict_name}.css"
    plist_file = f"{dict_name}.plist"

    cmd = [
        str(build_script),
        dict_name,
        xml_file,
        css_file,
        plist_file,
    ]

    pr.white("building dictionary bundle with DDK")
    try:
        env = os.environ.copy()
        env["DICT_BUILD_TOOL_DIR"] = str(ddk_dir)
        env["DICT_DEV_KIT_OBJ_DIR"] = "./objects"

        res = subprocess.run(
            cmd,
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            env=env,
        )
        if res.returncode != 0:
            pr.no("build failed")
            if res.stderr:
                pr.red(res.stderr.strip())
            if res.stdout:
                pr.red(res.stdout.strip())
            return None

        bundle_path = output_dir / "objects" / f"{dict_name}.dictionary"
        if bundle_path.is_dir():
            pr.yes("ok")
            return bundle_path
        else:
            pr.no("bundle not found")
            return None
    except Exception as e:
        pr.no("error")
        pr.red(str(e))
        return None


def install_bundle(bundle_path: Path, dest_dir: Optional[Path] = None) -> bool:
    """Install .dictionary bundle into ~/Library/Dictionaries/"""
    pr.white("installing to ~/Library/Dictionaries")
    try:
        if dest_dir is None:
            dest_dir = Path.home() / "Library/Dictionaries"
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / bundle_path.name

        if target.exists():
            shutil.rmtree(target)

        # ditto preserves resource forks and attributes
        subprocess.run(["ditto", "--noextattr", "--norsrc", str(bundle_path), str(target)], check=True)
        subprocess.run(["touch", str(dest_dir)], check=True)
        # Flush macOS dictionary helper cache
        subprocess.run(["killall", "DictionaryServiceHelper"], check=False, capture_output=True)
        pr.yes("ok")
        return True
    except Exception as e:
        pr.no("error")
        pr.red(str(e))
        return False


def zip_directory(source_dir: Path, zip_file: Path) -> None:
    """Compress a directory into a zip file."""
    with ZipFile(zip_file, "w", ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, source_dir)
                # Store with top-level folder name inside zip
                arcname = os.path.join(source_dir.name, relative_path)
                zipf.write(file_path, arcname)


def export_to_appledict(
    dict_info: DictInfo,
    dict_var: DictVariables,
    dict_data: list[DictEntry],
    install: bool = False,
    ddk_path: Optional[Path] = None,
) -> None:
    """Export dictionary to Apple Dictionary format using PyGlossary and DDK.
    Usage:
        export_to_appledict(dict_info, dict_var, dict_data, install=False)
    """
    pr.green_title("exporting to apple dictionary")

    dict_name = getattr(dict_var, "dict_name", "pali-grammar")
    apple_dir = getattr(dict_var, "apple_dir", dict_var.gd_path.parent / f"{dict_name}-apple")
    apple_zip_path = getattr(dict_var, "apple_zip_path", dict_var.gd_path.parent / f"{dict_name}-apple.dictionary.zip")

    # Clean existing apple_dir
    if apple_dir.exists():
        shutil.rmtree(apple_dir)
    apple_dir.mkdir(parents=True, exist_ok=True)

    # 1. Initialize PyGlossary
    pr.white("creating glossary")
    Glossary.init()
    bundle_id = f"org.digitalpalidictionary.{dict_name.replace('_', '-')}"
    glos = Glossary(
        info={
            "name": dict_info.bookname,
            "bookname": dict_info.bookname,
            "author": dict_info.author,
            "description": dict_info.description,
            "website": dict_info.website,
            "sourceLang": dict_info.source_lang,
            "targetLang": dict_info.target_lang,
            "date": dict_info.date,
            "CFBundleIdentifier": bundle_id,
            "copyright": "Digital Pali Dictionary",
        }
    )
    pr.yes("ok")

    # 2. Add entries (cleaning XHTML for Apple Dictionary XML)
    pr.white("compiling data")
    for d in dict_data:
        cleaned_html = clean_xhtml_for_appledict(d.definition_html)
        words = [d.word] + [syn for syn in d.synonyms if syn != d.word]
        glos.addEntry(
            glos.newEntry(
                word=words,
                defi=cleaned_html,
                defiFormat="h",
            )
        )
    pr.yes("ok")

    # 3. Determine custom CSS
    css_path = get_apple_css_path(dict_var)

    # 4. Write Apple Dictionary XML sources
    pr.white("writing appledict xml sources")
    glos.write(
        filename=str(apple_dir),
        formatName="AppleDict",
        css=str(css_path),
        clean_html=True,
    )
    pr.yes("ok")

    # Copy icon if available into OtherResources
    if dict_var.icon_source_path and dict_var.icon_source_path.exists():
        other_res = apple_dir / "OtherResources"
        other_res.mkdir(exist_ok=True)
        shutil.copy(dict_var.icon_source_path, other_res / dict_var.icon_source_path.name)

    # 5. Locate DDK
    if ddk_path is None:
        ddk_path = find_ddk_path()

    # Write clean Makefile
    write_custom_makefile(apple_dir, apple_dir.name, ddk_path)

    # 6. Build .dictionary bundle if DDK is available
    bundle_built = False
    if ddk_path:
        bundle_path = build_with_ddk(apple_dir, apple_dir.name, ddk_path)
        if bundle_path and bundle_path.is_dir():
            bundle_built = True
            # Copy bundle to share directory
            target_bundle = apple_dir.parent / f"{dict_name}.dictionary"
            if target_bundle.exists():
                shutil.rmtree(target_bundle)
            shutil.copytree(bundle_path, target_bundle)

            if dict_var.zip_up:
                pr.white("zipping dictionary bundle")
                if apple_zip_path.exists():
                    apple_zip_path.unlink()
                zip_directory(target_bundle, apple_zip_path)
                pr.yes("ok")

            if install:
                install_bundle(target_bundle)

            if dict_var.delete_original:
                pr.white("cleaning up build files")
                shutil.rmtree(apple_dir)
                pr.yes("ok")
    else:
        pr.white("DDK not found; source package generated in " + str(apple_dir))
        pr.yes("ok")
        if dict_var.zip_up:
            pr.white("zipping apple source package")
            sources_zip = apple_dir.parent / f"{dict_name}-apple-sources.zip"
            if sources_zip.exists():
                sources_zip.unlink()
            zip_directory(apple_dir, sources_zip)
            pr.yes("ok")

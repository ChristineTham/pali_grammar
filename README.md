# pali_grammar

Dictionary of Pali grammatical inflections with grammatical symbols, usage, meaning and construction, based on Digital Pali Dictionary.

Pre-compiled dictionary archives for **Apple Dictionary**, **GoldenDict**, and **MDict** can be downloaded directly from the [Releases page](https://github.com/ChristineTham/pali_grammar/releases).

### Building from Source

```shell
git clone https://github.com/ChristineTham/pali_grammar.git
```

2. Install [uv](https://docs.astral.sh/uv/) for your operating system

3. Install all the dependencies with uv

```shell
uv sync
```

4. Download latest version of dpd.db.tar.bz2 from [dpd-db releases page](https://github.com/digitalpalidictionary/dpd-db/releases)

```shell
tar xvf dpd.db.tar.bz2
```

That should create an SQLite database `dpd.db` in the project folder which can be accessed with [DB Browser](https://sqlitebrowser.org/), [DBeaver](https://dbeaver.io/), through [SQLAlchemy](https://www.sqlalchemy.org/) or your preferred method.

5. Now, generate Pali grammar dictionary

```shell
uv run main.py
```

This compiles dictionaries in three formats:
- **GoldenDict**: `share/pali-grammar` and `share/pali-grammar-goldendict.zip`
- **MDict**: `share/pali-grammar-mdict.mdx`, `.mdd`, and `share/pali-grammar-mdict.zip`
- **Apple Dictionary**: `share/pali-grammar.dictionary` and `share/pali-grammar-apple.dictionary.zip` (plus XML sources in `share/pali-grammar-apple/`)

#### Apple Dictionary (macOS native Dictionary app)

The Apple Dictionary exporter uses **PyGlossary** to generate compliant XML sources, styles, property lists, and Makefiles, and automatically compiles them using the **Apple Dictionary Development Kit (DDK)** if installed.

1. **Prerequisites for compiling Apple Dictionary:**
   - Download *Additional Tools for Xcode* from the [Apple Developer Downloads](https://developer.apple.com/download/all/) portal.
   - Copy `Dictionary Development Kit` into `~/Developer/Extras/Dictionary Development Kit` (or `/Applications/Utilities/Dictionary Development Kit`).
   - If DDK is not found, the build will still generate the complete AppleDict source files and Makefile in `share/pali-grammar-apple/` ready to compile with `make`.

2. **Installing into macOS Dictionary app:**
   - Run with `--install` flag:
     ```shell
     uv run main.py --apple-only --install
     ```
   - Or manually copy `share/pali-grammar.dictionary` (or unzip `share/pali-grammar-apple.dictionary.zip`) into:
     ```text
     ~/Library/Dictionaries/
     ```
   - Open **Dictionary.app**, go to **Settings** (`⌘ ,`), and ensure **Pali Grammar** is checked in the dictionary list.
   - Use system-wide word lookup in any macOS app with <kbd>Control</kbd> + <kbd>Command</kbd> + <kbd>D</kbd>.

#### Command-line Options

```shell
uv run main.py [options]
```

- `--apple-only`: Build only the Apple Dictionary
- `--goldendict-only`: Build only GoldenDict
- `--mdict-only`: Build only MDict
- `--no-apple`: Skip Apple Dictionary build
- `--install`: Automatically install the compiled `.dictionary` bundle into `~/Library/Dictionaries/`
- `--limit N`: Limit processing to `N` entries (convenient for quick tests)

6. Generate custom Cspell dictionary

```shell
uv run cspell.py
```

Enjoy!


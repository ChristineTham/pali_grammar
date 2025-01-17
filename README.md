# pali_grammar

Pali grammar dictionary based on Digital Pali Dictionary

1. To generate, first clone DPD

```shell
git clone --depth=1 https://github.com/digitalpalidictionary/dpd-db.git
```

2. Navigate into the directory

```shell
cd dpd-db
```

3. Clone this repo

```shell
git clone https://github.com/ChristineTham/pali_grammar.git
```

4. Download the submodules from Github

```shell
git submodule init && git submodule update
```

5. Generate conda environment

```shell
conda env create -f pali_grammar/environment.yml
conda activate pdpd
```

6. Install [nodejs](https://nodejs.org/en/download) for your operating system

7. Install [go](https://go.dev/doc/install) for your operating system

8. Install [poetry](https://python-poetry.org/docs/) for your operating system

9. Install all the dependencies with poetry

```shell
poetry install
```

10. Run this once to initialize the project

```shell
poetry run bash scripts/bash/initial_setup_run_once.sh
```

11. Build the database, this can take up to an hour the first time.

```shell
export PYTHONPATH=`pwd`
poetry run bash scripts/bash/build_db.sh
python db/bold_definitions/extract_bold_definitions.py
poetry run bash scripts/bash/build_db.sh
```

That should create an SQLite database `dpd.db` in the root folder which can be accessed with [DB Browser](https://sqlitebrowser.org/), [DBeaver](https://dbeaver.io/), through [SQLAlechmy](https://www.sqlalchemy.org/) or your preferred method.

12. Now, generate Pali grammar dictionar

```shell
mkdir pali_grammar/output
mkdir pali_grammar/share
python pali_grammar/pali_grammar.py
```

The dictionaries are located in `pali_grammar/share` folder. Copy them to your favourite dictionary program in the same way as DPD dictionaries.

Enjoy!

# Command line

```
python3 build.py build    [--data DIR] [--out DIR] [--base-path PATH]
python3 build.py validate [--data DIR]
python3 build.py links    --url URL [--data DIR]
python3 build.py token    [--prefix NAME]
```

`python3 build.py --help` and `python3 build.py <command> --help` describe
the options. Python 3.10 or newer is enough: the builder uses the standard
library only.

## Commands

| Command | What it does |
|---|---|
| `build` | Checks the data, renders a page for every guest record and for the staff record, checks the finished output and writes it into `--out`. |
| `validate` | Checks the data and works out what every page shows, without rendering or writing anything; then prints a summary. |
| `links` | Checks the data like `validate` and prints the address of every page. For local use only. |
| `token` | Prints a new token for a record. Reads no data. |

### build

```
python3 build.py build
python3 build.py build --data ../my-dinner --out ../my-dinner-pages --base-path /menu
```

The output holds `<token>/index.html` for every guest record and for the
staff record, and `assets/` with `app.css`, `app.js` and a `favicon.svg`
generated from the colours of the style sheet. Nothing else: the build
refuses an output with any other file.

The output is assembled in a new directory next to `--out` and checked
there:

- only the expected files;
- no external resources, and no inline scripts or styles;
- every local address on a page resolves inside the output and lies under
  the base path;
- every link of a page leads to a part of the same page;
- no file holds a record's token: a token is only the name of its page
  directory.

Only when every check has passed does the new output replace `--out`. A
failed build leaves the previous output as it was. Two builds of the same
data are identical byte for byte.

The log shows counts and paths, never the data, and hides the page
directories. `python3 build.py build` in the root of the repository prints:

```
build: 12 guest record(s) + staff validated (data: examples/data)
build: wrote 13 page(s) to ./dist/<token>/
build: base path /: the pages are at /<token>/, the shared files at /assets/
build: copied 2 asset file(s) to ./dist/assets/, favicon.svg generated from the design tokens
build: OK -> ./dist (13 page(s), 16 file(s) in total, 247.0 KiB)
```

### validate

```
python3 build.py validate
python3 build.py validate --data examples/data-plain
```

On success it prints one line:

```
validate: OK - 19 seat(s), 12 guest record(s) + staff, 8 dish(es), 2 set(s), 5 drink(s)
```

Warnings come before it, on stderr. They point at what is probably a
mistake but does not stop the build: a free seat, a dish that no page shows,
a dish without allergen information on the staff page.

### links

```
python3 build.py links --url https://example.org/menu
```

Prints a line per guest record, in the order of `guests.json`: the record's
`name`, a tab and `URL/<token>/`. The staff page comes last, after the word
`staff`. Nothing is printed unless the whole data set is valid.

`--url` is the address where the contents of `--out` are published: `http`
or `https`, without credentials, a query or a fragment. A trailing `/` is
dropped.

The lines hold names and the secret addresses. The command is meant for
sending the links by hand, and it refuses to run when the environment
variable `CI` or `GITHUB_ACTIONS` is set.

### token

```
python3 build.py token
python3 build.py token --prefix Greta
```

Without `--prefix`, a fully random token of 22 characters, as the staff
record needs. With `--prefix NAME`, a readable token `NAME-xxxx`: the name
and a random tail of four characters without the easily confused ones
(`0`/`o`, `1`/`l`/`i`). `NAME` holds A-Z, a-z, 0-9, `_` and `-`.

## Options

| Option | Commands | Default | Meaning |
|---|---|---|---|
| `--data DIR` | `build`, `validate`, `links` | `examples/data` next to `build.py` | The directory with `menu.json` and `guests.json`. |
| `--out DIR` | `build` | `dist` in the current directory | The output directory, replaced on every build. |
| `--base-path PATH` | `build` | `/` | The path under which the contents of `--out` are published, such as `/menu`: every URL in the output starts with it, and a page is at `PATH/<token>/`. |
| `--url URL` | `links`, required | | The published address of the contents of `--out`. |
| `--prefix NAME` | `token` | | The readable start of a token. |

`--base-path` is `/` or segments of A-Z, a-z, 0-9, `_` and `-`, each after a
single `/`. A local address on a page outside it is an error: the pages lead
nowhere else on the site.

## The output directory

The build replaces `--out` as a whole, so it refuses an `--out` whose
replacement would destroy anything:

- the code directory, the data directory or the working directory, or a
  parent of one of them;
- a directory inside the data directory or inside the code's `assets/`;
- the home directory or the file system root;
- a symbolic link, or a file;
- an existing directory that is neither empty nor the output of a previous
  build.

## Messages

Warnings and errors go to stderr, errors all at once at the end. They name
the place in the data and never quote the data itself:

```
menu.json: field 'sections[2].nav' must not be empty: leave the field out for a section without a link in the navigation bar
guests.json: guest #4: field 'seats[1].name' is required for a seat that is not a +1 ('plusOne': true)
```

`guest #N` is the record's position in `guests.json`, from 1; the staff
record counts too. In `guests.json` a key is shown only when it is a field
name of the format or an id declared in `menu.json`; any other key may be a
name and is shown as `<unknown key>`. A token in a path is hidden.

An unexpected failure is reported by its type and its place in the code
only. Set `BUILD_DEBUG=1` to see the traceback.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success: `--help`, valid data, a finished build, the links, a token. |
| `1` | Errors in the data or in the finished output, an `--out` the build refuses to replace, or `links` in CI. |
| `2` | A bad command line: no command, an unknown option, a bad `--base-path`, `--url` or `--prefix`. |

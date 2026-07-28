# Recipe: datacubes, books, and newspapers  [DX]

Datacubes, books, and newspapers are placed `DeusExDecoration` information devices, set up the same
way: they point at a named text resource compiled into a package. (Emails are computer content, not a
placed decoration.) A datacube copies its text into the player's Notes when read; books and
newspapers are read-and-forget. Use a datacube to hand out a door code or a story beat with a
mechanical payoff.

> Authoring the text is a package-build step, not a uedcli verb. The text lives in `.txt` files
> compiled into a `.u` package with `ucc make` (`#exec DEUSEXTEXT IMPORT FILE=…`), outside uedcli.
> uedcli places the device and points it at the compiled text via `textTag` + `TextPackage`.

## Procedure

1. Write the text (pipeline step, outside uedcli). Create e.g. `16_DataCube01.txt`; the naming
   convention is `<missionNumber>_DataCube<NN>.txt` (`_Book<NN>`, `_Newspaper<NN>`). Use the DX markup
   (below). Import it with a `#exec DEUSEXTEXT IMPORT` line and `ucc make` the package.
2. Place the device — a `DataCube`, book, or newspaper under `DeusExDecoration → InformationDevices`.
3. Point it at the text — set `textTag` to the filename without `.txt` (e.g. `16_DataCube01`) and
   `TextPackage` to your package name.
4. Optional: set `imageClass` to a `DataVaultImage` subclass to show a picture alongside the text.

## With uedcli

```bash
# 2-4. Place a datacube and point it at compiled text (text was built with ucc make).
actor build DeusEx.DataCube \
  --prop textTag=16_DataCube01 \
  --prop TextPackage=MyMissionText \
  --at 256,256,48 | actor add -

# A book and a newspaper are identical apart from the class and text file:
actor build DeusEx.BookOpen --prop textTag=16_Book01 --prop TextPackage=MyMissionText --at 300,256,40 | actor add -
actor build DeusEx.Newspaper --prop textTag=16_Newspaper01 --prop TextPackage=MyMissionText --at 340,256,4 | actor add -
```

> List the info-device class names with
> `class list --subclass-of DeusEx.DeusExDecoration` (meshes vary — `BookOpen`, `BookClosed`,
> `Newspaper`, `NewspaperOpen`, etc.).

## DX text markup

Plain text with a few HTML-like tags. The formatting tags `<B>`, `<I>`, `<U>` do nothing. What works:

| Tag                    | Effect                                                 | Where |
| ---------------------- | ------------------------------------------------------ | --- |
| `<P>`                  | Paragraph break; a line with just `<P>` = a blank line | everywhere |
| `<COMMENT>…</COMMENT>` | Author note, never shown to the player                 | everywhere |
| `<DC=r,g,b>`           | Colour the next line (e.g. `<DC=255,255,0>` = yellow)  | datacubes/books/newspapers only |
| `<JC>…</JC>`           | Centre the text                                        | datacubes/books/newspapers only |

Example datacube text (`16_DataCube01.txt`):

```
<P>2501. That can be our secret password.
<P>
<P>Major Kusanagi
```

Example newspaper with a centred red headline:

```
<DC=255,0,0>
<P><JC>G7 Says Growth on Track</JC>
<P>
<P>The Group of Seven rich nations shrugged off a dimming outlook for world growth...
```

## Properties reference

| Property      | Meaning |
| ------------- | --- |
| `textTag`     | The compiled text resource name (filename **without `.txt`**) |
| `TextPackage` | The package the text was compiled into |
| `imageClass`  | Optional `DataVaultImage` subclass shown with the text |

## Caveats and gotchas

- `textTag` omits the extension — `16_DataCube01`, not `16_DataCube01.txt`.
- Keep the mission number in the filename consistent with your `DeusExLevelInfo.missionNumber` — the
  convention ties text to a mission.
- Only datacubes write to Notes. Use a datacube (not a book) when the text is a clue the player should
  re-read, e.g. a keypad code.
- Reserve `<DC>` colour for headlines; on everything it reads as noise.

## See also

- [`keypad-and-locks.md`](keypad-and-locks.md) — the codes a datacube commonly hands out.
- [`../classes.md`](../classes.md) — the `DeusExDecoration` information-device family.
- [`../`](../) — the DX design philosophy on environmental storytelling.

# Test-only font

`lato-regular.woff2` and `lato-bold.woff2` are Lato 2.015 as MkDocs ships them in its `readthedocs` theme
(`mkdocs/themes/readthedocs/css/fonts/lato-normal.woff2`, `lato-bold.woff2`), copied unchanged.

Copyright (c) 2011-2015 by tyPoland Lukasz Dziedzic (http://www.typoland.com/) with Reserved Font Name "Lato".
Licensed under the SIL Open Font License, Version 1.1 (http://scripts.sil.org/OFL): the notice the fonts carry in
their own `name` table. The licence's full text is in `OFL.txt` beside them (from the Lato release in google/fonts).

The browser tests load them through `tests/_slow.py` so every machine lays a page out in the same sans font. Nothing in
the product, the package or a built site uses them.

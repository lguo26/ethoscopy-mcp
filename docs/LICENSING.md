# Licensing decision

Decision recorded 21 September 2026: `ethoscopy-mcp` is licensed under the
**GNU General Public License version 3 only**, using the SPDX identifier
`GPL-3.0-only`.

## Why GPL-3.0-only

Ethoscopy is distributed as GPLv3 software. This package imports Ethoscopy
directly, invokes its Python methods, subclasses or manipulates its specialized
dataframe objects, and is designed specifically to expose its analysis engine.
The conservative distribution position is therefore to treat the two packages
as a combined GPL work rather than relying on a claim that they are unrelated
programs.

`GPL-3.0-only` matches the exact version identified by the upstream repository
without asserting that Ethoscopy grants an “or any later version” option. A
future change to `GPL-3.0-or-later` would require a separate rights and
compatibility review.

## Scope

The GPL applies to the code and redistributable examples in this repository.
Third-party dependencies retain their own copyright and license terms.

The following are deliberately not distributed in this repository and are not
granted rights by this software license:

- private experimental pickle files, databases, recordings, and metadata;
- generated analysis runs and research artifacts.

Merely placing separately licensed data next to the program does not relicense
that data. Generated scientific tables and figures require their own ownership,
privacy, and publication decisions.

## Distribution obligations

Anyone distributing this program or a combined derivative must comply with the
GPLv3 terms, including providing the corresponding source and license notices
when required. There is no warranty under the terms stated in `LICENSE`.

Contributors must have the right to submit their work and should understand
that accepted contributions are distributed under `GPL-3.0-only`. A formal
Developer Certificate of Origin or contributor agreement can be added if the
project later needs more structured contribution governance.

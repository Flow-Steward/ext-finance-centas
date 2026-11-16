# Branding

`icon.png` is a neutral placeholder drawn for this extension: a document sheet and a coin
on a blue rounded square. It carries no mark, name or artwork of Centas or of its
developer.

## Source

- Centas publishes no logo of its own that could be used: on 2026-11-16 the favicon of
  ws.centas.lt was empty (0 bytes), its sign-in page shows no logo image, and the
  developer's site (edlonta.lt, which centas.lt redirects to) shows only the developer's
  own mark and a photograph of a 1-centas coin.
- So no third-party asset was used. The icon is drawn from plain shapes by
  `tests/reference/make_icon.py` (Python standard library only), which produces the same
  file on every run.

## What was done

- `python3 tests/reference/make_icon.py` writes a 128 × 128 RGBA PNG.
- SHA-256 of `icon.png`: `3c313d17534efd370515997920fc93a4c324a8a4a47b7e33a1de45c22f3562e6`.

## Use

Centas is a product of Edlonta, UAB. The name is used only to say which program this
integration connects to; it does not imply endorsement by Edlonta, UAB. The icon is this
extension's own and may be replaced by an official Centas mark when one is available
with permission to use it.

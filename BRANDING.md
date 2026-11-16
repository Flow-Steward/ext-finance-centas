# Branding

`icon.png` is the round mark of Centas WS — a white cent sign (¢) on a blue disc — taken
from Centas WS's own published artwork, used only to identify this integration with
Centas WS in Flow Steward.

## Source

- Product: Centas WS, the web exchange of the Centas accounting program, by Edlonta, UAB —
  <https://ws.centas.lt/>.
- Official asset: the share image (`og:image`) of the Centas WS home page
  <https://ws.centas.lt/l/>:
  <https://ws.centas.lt/l/wp-content/uploads/2020/05/dfghdgfhdfgh.png>
  (1200 × 630 PNG: the round ¢ mark next to the CENTASWS wordmark on white).
- SHA-256 of the source: `06f56e880972a8ae4b3ee120bdda62f0a8b7fcd6fa2ef3d4d129455a498cd8e7`
  (downloaded 2026-11-16).

The same mark appears in the Centas WS logo served at
<https://ws.centas.lt/assets/img/logo.png> (570 × 150), where it is smaller. The Centas
program's own window icon was not found published at a usable size, and Edlonta's own
mark names the developer rather than the product, so the Centas WS mark is used.

## What was done

- Only the round mark was used: the disc (170 × 170 pixels in the source, found as the
  blue pixels left of the wordmark) was cut out on its circle and reduced to 128 × 128
  by area averaging (4 × 4 samples a pixel), the area outside the circle made
  transparent. No colour, stroke or shape was changed. Done with a short Python script
  using only the standard library (the PNG decoded and encoded with `zlib`).
- SHA-256 of `icon.png`: `a172394b035307b66c692c3f6da432a9917c9aca7b7b709b6f9d13e36a9ea7e3`.

## Use

Centas and Centas WS belong to Edlonta, UAB. ws.centas.lt and edlonta.lt publish no brand
or logo usage guidelines (checked 2026-11-16). The mark is used unaltered, only to show
which product this integration connects to; it does not imply endorsement by Edlonta, UAB.

# Changelog

## 0.1.0 — 2026-11-16

- First release: steps for Centas WS (ws.centas.lt), the web exchange of the Centas
  accounting program, covering its whole documented API.
- Send a sales invoice, a purchase invoice or a customer order with its lines; send bank
  payments and product cards in batches. Totals are checked against the lines, or computed
  from them, before anything is sent; amounts are limited to 15 whole digits.
- Send bank payments first reads Centas WS's payment export: when it already lists one of
  the references, or cannot be read, the step stops and sends nothing.
- Get products, find a product by code or barcode, get stock levels by warehouse and get
  payments, one page at a time, from what the Centas program uploaded to Centas WS.
- The key is sent only to https://ws.centas.lt, in the body of every write; it is removed
  from everything the steps return.

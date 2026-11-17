# Changelog

## 0.1.1 — 2026-11-17

- The take steps remove the key from the saved queue file also where Centas WS writes it with XML character references (`&#65;`, `&#x41;`). An answer that cannot be cleaned is not saved; its records are returned in the step output with a warning, as when the file cannot be saved.
- Send an invoice to another company's Centas warns when the purchase or document row counts differ from the lines sent or are missing, and when an e-mail was asked for but is not reported as sent. The invoice is never sent again by the step.
- A response too large for the step output keeps the write's facts and the result's short values.

## 0.1.0 — 2026-11-16

- First release: steps for Centas WS (ws.centas.lt), the web exchange of the Centas
  accounting program, covering every operation of its API specification.
- Send sales invoices, customer orders, purchase invoices and invoices to other companies with
  their lines; send payments, products, clients and suppliers and consignment notes in
  batches; update, record payments against or delete sales documents.
- Totals are checked against the lines, or computed from them, before anything is sent;
  amounts are limited to 15 whole digits. A document number Centas WS already has stops the
  step with a conflict.
- Read products, prices and stock, product cards, gallery links, clients and suppliers, sales
  documents by number, date or unpaid status, purchases of a date range, an order's invoice
  PDF and counts of new records.
- Take new sales documents, orders, purchases and payments from the Centas WS queue; each
  answer is also saved whole as a workflow file.
- Test the connection shows until when the WS key is valid and warns 30 days before it
  expires. The key is sent only to https://ws.centas.lt and is removed from everything the
  steps return.

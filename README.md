# Centas for Flow Steward

Workflow steps for [Centas WS](https://ws.centas.lt), the web exchange of the Centas
accounting and business program (Lithuania).

- **Send a sales invoice to Centas**, **Send a customer order to Centas**, **Send a purchase
  invoice to Centas** — a document with its lines. Totals are checked against the lines, or
  computed from them, before anything is sent.
- **Send bank payments to Centas**, **Send products to Centas** — batches of up to 500.
- **Get products**, **Find a product by code or barcode**, **Get stock levels**, **Get
  payments** — what the Centas program uploaded to Centas WS, one page at a time.
- **Test the connection**.

What a step sends waits in Centas WS until an accountant imports it in Centas (menu
ws.centas.lt). The steps follow the
[Centas API documentation](https://centas.gitbook.io/docs); the extension's **Coverage**
page lists every documented field and where it goes.

## Setup

1. In Centas, open **Parametrai → Nustatymai → Bendrieji → III** and copy **WS raktas**.
2. In Flow Steward, open the extension's **Connection** page, add a connection with that key
   and press **Test connection**.

The steps connect only to `https://ws.centas.lt`. The key is sent in the body of every
write and, as the API requires, in the query of the two exports; it is removed from
everything the steps return.

## Development

```bash
python3 tests/reference/build_contracts.py   # regenerate contracts and pages from tests/reference/op_specs.py
python3 -m pytest -q tests                   # tests, no network
```

The extension uses the Python standard library and the Flow Steward extension SDK only.

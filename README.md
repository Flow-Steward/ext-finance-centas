# Centas for Flow Steward

Workflow steps for [Centas WS](https://ws.centas.lt), the web exchange of the Centas
accounting and business program (Lithuania), covering its whole documented API
([Centas WS API documentation](https://ws.centas.lt/api-docs/)).

- **Sales** — send a sales invoice, get one by number, get them by date or unpaid, update
  their payment status, record payments against them, delete them.
- **Orders** — send a customer order, get the invoice PDF of an order.
- **Purchases** — send a purchase invoice, send an invoice to another company's Centas, get
  purchases of a date range.
- **Payments, products, clients and suppliers, consignment notes** — send them in batches;
  get products, prices, stock, product cards, gallery links, clients and suppliers; find a
  company by its code.
- **Queue** — when a workflow plays the Centas program's part, *Take new …* steps collect new
  sales documents, orders, purchases and payments from Centas WS. Centas WS marks what they
  take, so the Centas program no longer sees those records as new.
- **Connection** — test the key and its expiry, count new records, check the service.

Totals of invoices and orders are checked against their lines, or computed from them, before
anything is sent. The extension's **Coverage** page lists every operation and field of the
API and where it goes.

## Setup

1. In Centas, open **Parametrai → Nustatymai → Bendrieji → III** and copy **WS raktas**.
2. In Flow Steward, open the extension's **Connection** page, add a connection with that key
   and press **Test connection**: it shows until when the key is valid.

The steps connect only to `https://ws.centas.lt`. The key is sent in the body of every write
and, as the API requires, in the query of every read; it is removed from everything the steps
return.

## Development

```bash
python3 tests/reference/build_contracts.py   # regenerate contracts and pages from tests/reference/op_specs.py
python3 -m pytest -q tests                   # tests, no network
```

The extension uses the Python standard library and the Flow Steward extension SDK only.

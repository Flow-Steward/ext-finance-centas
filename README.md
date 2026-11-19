# Centas integration for Flow Steward

<img src="icon.png" width="96" alt="Centas integration for Flow Steward">

[![CI](https://img.shields.io/github/actions/workflow/status/Flow-Steward/ext-finance-centas/ci.yml?branch=main&label=CI)](https://github.com/Flow-Steward/ext-finance-centas/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/Flow-Steward/ext-finance-centas)](https://github.com/Flow-Steward/ext-finance-centas/releases/latest)

Automate Centas with Flow Steward workflows and AI agents: send invoices, orders and payments, read products, prices and stock — without writing code.

This Flow Steward extension is an accounting integration for companies in Lithuania that keep
their books (apskaita) in Centas. It connects Centas to workflow automation through the Centas WS
API: documents and data from your shop, CRM or bank reach Centas without retyping, ready for
document import.

## What is this

Centas is a Lithuanian accounting and business program by Edlonta, UAB; Centas WS (ws.centas.lt)
is its web exchange, where documents wait until Centas imports them. This extension is a
connector: it adds ready workflow steps to Flow Steward, and the same steps are available as tools
for AI agents. Learn more about Flow Steward at
[docs.flowsteward.org](https://docs.flowsteward.org).

## What you can automate

- Send sales invoices to Centas from orders in your shop or CRM — no retyping.
- Pass supplier invoices to Centas as purchases.
- Send customer orders to Centas and get back the PDF of the invoice issued for them.
- Send bank and cash payments to Centas in one batch, or record payments against sales documents.
- Publish Centas prices and stock to your online shop.
- Keep clients, suppliers and products the same in Centas and your other systems.
- Send your invoice straight to a customer who also uses Centas, optionally with its PDF and an e-mail.

## Why teams use it

- **Totals that add up.** Invoice and order totals are checked against their lines, or computed from them, before anything is sent.
- **Exact amounts.** Amounts are handled as exact decimals, never rounded through floating point.
- **A change is never sent twice.** Each write is sent at most once and never retried.
- **A test run changes nothing.** Every send is skipped in test runs, so you can try a workflow safely.
- **The whole API.** The 29 steps cover the whole documented Centas WS API (31 operations; two of them only answer that POST is required).
- **The key stays secret.** It is stored encrypted and removed from everything the steps return.

## What's inside

Everyday steps:

- **Send a sales invoice to Centas** — with its lines; returns the document ID.
- **Send a purchase invoice to Centas** — a supplier's invoice with its lines.
- **Send a customer order to Centas**, **Get the invoice PDF of an order** — order in, invoice PDF out.
- **Send bank and cash payments to Centas** — one batch.
- **Get product prices and stock** — price, cost and stock by warehouse, optionally for one barcode.
- **Send clients and suppliers to Centas**, **Send products to Centas** — create new ones and update known ones.
- **Test the connection** — checks the key and shows until when it is valid.

All 29 steps cover sales documents, orders, purchases, payments, products, clients and suppliers, consignment notes and the Centas WS queue.

## Get started

1. In Flow Steward, open **Extensions → Catalog** and install **Centas**.
2. Get your Centas WS key: sign in at [ws.centas.lt](https://ws.centas.lt/interface/login), or find it in the Centas program under **Parametrai → Nustatymai → Bendrieji → III**, field **WS raktas**. In the extension's **Connection** page, add a connection named after the company and paste the key.
3. Press **Test connection**: it shows until when the key is valid.
4. Build your first workflow, for example **Send a sales invoice to Centas** from a new shop order.

## Requirements

- Centas WS active for your company, and Centas set up to work with it.
- A Centas WS key. It is valid until a date; **Test connection** warns 30 days before it expires.
- Sent invoices, orders and payments wait in Centas WS until they are imported in Centas through the **ws.centas.lt** menu.
- The read steps see what Centas uploads to Centas WS: set Centas to upload stock and product cards if workflows read them.
- The *Take new …* steps collect new records the way the Centas program does, and Centas then no longer sees them as new. Use them only in a workflow that plays the program's part.
- Flow Steward 0.9.16 or later.

## FAQ

**How do I send invoices from an online shop to Centas automatically?**
Add **Send a sales invoice to Centas** to a workflow triggered by new orders. The invoice reaches Centas WS and is imported in Centas like any other WS document.

**Why does a sent invoice not appear in Centas right away?**
Centas WS keeps it until the Centas program imports it; success of the step means Centas WS received it.

**Does Centas WS check for repeated documents?**
It refuses a sales invoice number it already has. Other sends are not checked for repeats by Centas WS, so a workflow should send each record once.

**Can I read stock and prices from Centas for my e-shop?**
Yes. **Get product prices and stock** reads what Centas uploads to Centas WS, including stock by warehouse.

**Where do I find the Centas WS key?**
In Centas WS after signing in, or in the Centas program under **Parametrai → Nustatymai → Bendrieji → III**, field **WS raktas**.

## In your language

Centas integracija su Flow Steward per Centas WS API automatizuoja dokumentų mainus: pardavimo ir pirkimo sąskaitos, užsakymai ir mokėjimai patenka į Centas WS, o iš ten importuojami į apskaitą. Taip pat galima skaityti prekes, kainas ir likučius el. parduotuvei.

## Links

- [Flow Steward documentation](https://docs.flowsteward.org)
- [Flow Steward extension catalog](https://github.com/Flow-Steward/extensions)
- [Issues](https://github.com/Flow-Steward/ext-finance-centas/issues)
- [Centas WS API documentation](https://ws.centas.lt/api-docs/)

## For developers

The contracts and pages are generated from `tests/reference/op_specs.py`; do not edit them by hand.

```bash
python3 tests/reference/build_contracts.py   # regenerate contracts and pages
```

From a Flow Steward checkout:

```bash
./flow-steward extensions test flowsteward.centas --root <parent>
./core/entrypoints/cli/scripts/lint.sh --checks extension-static,extension-tests --extension-root <abs path>
```

The extension uses the Python standard library and the Flow Steward extension SDK only.

Centas, Centas WS and their marks belong to their owner; see [BRANDING.md](BRANDING.md).

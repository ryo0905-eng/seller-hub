# AGENTS.md

## Project

Seller Hub is a Django web app for Japanese resale sellers. It tracks purchased inventory, expected selling prices, fees, shipping, exchange rates, expected profit, and actual sales results.

The app started as an eBay profit tracker, but it should stay channel-flexible:

- Expected pricing can be entered in USD or JPY.
- Do not require or emphasize an expected/planned sales channel.
- Record the actual sales channel only after an item sells.
- Actual sales channel choices: eBay, Mercari, Yahoo Auctions, Rakuma, Other.

## Architecture

- Framework: Django
- Database: SQLite locally, PostgreSQL on Render
- Styling: Bootstrap 5 plus `static/css/app.css`
- Deployment: Render
- Static files: WhiteNoise
- Production server: Gunicorn

Render deploys from GitHub. `build.sh` installs dependencies, runs `collectstatic`, and applies migrations.

## Core Product Rules

Product records are primarily inventory and pricing judgment records.

Expected sale price:

- `expected_sale_price_usd` is optional.
- `expected_sale_price_jpy` is optional.
- At least one expected sale price must be present.
- If USD is present, JPY is derived from USD and exchange rate.
- If only JPY is present, exchange rate defaults to `1.00` for calculation purposes.

Fees:

- The field name `ebay_fee_rate` is legacy; UI should call it `販売手数料率`.
- The default is currently 15%.
- Actual fee field name `actual_ebay_fee_jpy` is also legacy; UI should call it `実販売手数料`.

Sales channels:

- Do not add a planned/expected channel back unless the user explicitly changes the product strategy.
- Use `actual_sales_channel` only for where the item actually sold.
- Show actual channel in listings only when it is set.

Deletion:

- Deletion should not be a one-click action from the pricing board.
- The delete action lives on the detail screen and goes through the confirmation page.

## Pricing Board UI

The product list is a pricing judgment board, not a full data table.

Keep the card focused on the core metrics the user wants to check daily:

- Purchase price
- Expected sale price
- Breakeven sale price
- Expected profit rate
- Expected ROI

Avoid adding too much secondary data back into the card. Put detailed data on the detail page.

The board should stay scannable on desktop and mobile. Prefer fewer, clearer cards over dense table-like layouts.

## Common Commands

Run these before committing meaningful changes:

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test
DEBUG=0 .venv/bin/python manage.py collectstatic --noinput
```

After model changes:

```bash
.venv/bin/python manage.py makemigrations
.venv/bin/python manage.py migrate
.venv/bin/python manage.py makemigrations --check --dry-run
```

Local server:

```bash
.venv/bin/python manage.py runserver
```

## Git / Deploy

- Commit focused changes.
- Push to GitHub after tests pass.
- Render should auto-deploy from the main branch.
- Render migrations run during build via `build.sh`.

## Coding Notes

- Preserve existing user data with migrations.
- Keep legacy DB field names when renaming would be risky; change labels in forms/templates instead.
- Prefer small, focused changes over broad refactors.
- Use Django forms, model properties, and migrations instead of ad hoc template-only logic when behavior affects saved data.
- Keep tests updated when changing form validation, calculated properties, or list/detail views.

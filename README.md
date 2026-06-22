# eBay Profit Tracker

日本人eBayセラー向けのDjango製利益計算アプリです。仕入れ商品を登録すると、想定売価USD・送料・為替・eBay手数料率から利益と利益率を自動計算します。

## ローカル起動

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

ブラウザで `http://127.0.0.1:8000/` を開き、作成したユーザーでログインしてください。管理画面は `http://127.0.0.1:8000/admin/` です。

## 主な機能

- ログイン必須の商品管理
- 商品の登録、一覧、編集、削除
- 商品詳細ページ
- 一覧からのクイック更新
- ステータス管理: 仕入れ済み / 出品中 / 売却済み / 発送済み
- 想定利益、実利益、想定との差額、ROIの自動計算
- 仕入れ日、出品日、売却日、発送日による販売日数・在庫日数の管理
- SKU、状態、数量、URL、販売先国、追跡番号の記録
- 商品画像URLによるサムネイル表示
- CSVインポート / エクスポート
- 実績分析ダッシュボード
  - 月別実利益グラフ
  - カテゴリ別実利益グラフ
  - ステータス別商品数グラフ
  - 期間フィルター
  - 赤字商品、長期在庫、仕入先別パフォーマンス
- Django管理画面
- Bootstrap 5によるスマホ対応画面

## 計算式

```text
sale_price_jpy = expected_sale_price_usd * exchange_rate
ebay_fee_jpy = sale_price_jpy * ebay_fee_rate / 100
profit_jpy = sale_price_jpy - ebay_fee_jpy - purchase_price_jpy - shipping_cost_jpy
profit_rate = profit_jpy / sale_price_jpy * 100
```

実売価格USDを入力すると、実際の為替・実送料・実eBay手数料を使って実利益も計算します。実eBay手数料が未入力の場合は、登録済みのeBay手数料率から概算します。

## Render向けメモ

`DATABASE_URL` がある場合はPostgreSQLを使い、未設定ならローカルSQLiteを使います。

RenderではPostgreSQLを作成し、Web Serviceに以下の環境変数を設定してください。

```text
DEBUG=0
SECRET_KEY=<強いランダム文字列>
ALLOWED_HOSTS=<your-service>.onrender.com
CSRF_TRUSTED_ORIGINS=https://<your-service>.onrender.com
DATABASE_URL=<Render PostgreSQL の Internal Database URL>
```

Renderのコマンド例:

```text
Build Command: ./build.sh
Start Command: gunicorn ebay_profit_tracker.wsgi:application
```

Pythonは `runtime.txt` で `python-3.12.8` に固定しています。

初回デプロイ後はRender Shellで管理ユーザーを作成してください。

```bash
python manage.py createsuperuser
```

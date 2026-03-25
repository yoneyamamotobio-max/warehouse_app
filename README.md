# Warehouse App

PySide6 で作る、地図操作メインの在庫管理アプリです。

## 方針

- 地図が主役
- 入力は `新規登録` ボタンを押した時だけダイアログ表示
- タブレットでのオフライン運用を想定
- 共有時だけ JSON を `Export / Import`

## 起動

1. Python 3.11 以上を用意
2. `python -m pip install -r requirements.txt`
3. `run_pyside.bat` を実行

## 主な機能

- 上面図マップで位置確認
- 細かいグリッドで多パレット配置に対応
- パレットをドラッグして移動
- パレットの向きを切り替え
- 拡大 / 縮小 / 等倍 とホイールズーム
- `新規登録` ボタンから必要な時だけ入力
- 1パレットに複数明細を登録
- `#38-LL10 S/S A 80` 形式に対応
- 左下45度ビューで積み高さを確認
- `在庫一覧` タブで集計在庫を確認
- ローカル保存と JSON の `Export / Import`

## ファイル

- `warehouse_app.py`: PySide6 アプリ本体
- `requirements.txt`: Python 依存
- `run_pyside.bat`: 起動スクリプト

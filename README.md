# 日刊しりとり最長チャレンジ

毎日16語が配られる、みんな共通の日刊しりとりパズル。しりとりで一番長くつなげられるかを競う。

- 無料・登録不要・バックエンドなし(静的HTML + JSON)
- 毎日決まった時刻に問題が切り替わる(日付ベースで自動選択)
- 結果は絵文字バー付きでシェアできる

## 遊び方

`index.html` を開くだけ。`puzzles.json` を fetch するため、`file://` で直接開くとブラウザにブロックされる場合がある。ローカルで試す場合はサーバー経由で開くこと。

```
python -m http.server 8000
```

## 問題の生成

`shiritori_gen.py` で問題を追加生成できる。

```
python shiritori_gen.py 30   # 30日分生成
```

## クレジット

単語データは [Mozc](https://github.com/google/mozc) の `dictionary_oss`(IPAdic準拠)を使用している。
IPAdic のライセンスは Mozc リポジトリの `dictionary_oss/README.txt` に記載のとおり。

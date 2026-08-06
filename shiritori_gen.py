"""
日刊しりとりパズルの問題生成器。

毎日、全員に同じ16語を配り「その中で作れる最長のしりとり」を競わせる。
問題を人が作る必要がないのが肝なので、辞書から自動生成して最長解を厳密に解く。

単語データ: Mozc の dictionary_oss (IPAdic 由来 / NAIST・BSD系ライセンス)。
利用時は出典表示が必要なので、公開時はクレジットを入れること。

最長チェーンは「有向グラフの最長パス」= 一般にはNP困難だが、
16語ならビットマスクDPで厳密に解ける(2^16 x 16 状態)。
"""
import json
import os
import random
import re
import sys
import urllib.request
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "mozc_dict_cache.txt")
POOL_PATH = os.path.join(HERE, "word_pool.json")
DICT_URLS = [
    f"https://raw.githubusercontent.com/google/mozc/master/src/data/dictionary_oss/dictionary0{i}.txt"
    for i in range(10)
]

NOUN_ID = 1851          # 名詞,一般
MAX_COST = 6000         # 小さいほど高頻度。珍しい固有名詞を落とすための閾値
WORDS_PER_PUZZLE = 16

HIRAGANA = re.compile(r"^[ぁ-ゖー]+$")

# しりとりの接続用にかなを正規化する(小書き→大書き、長音は直前の母音へ)
SMALL_MAP = str.maketrans("ぁぃぅぇぉっゃゅょゎ", "あいうえおつやゆよわ")
VOWEL_OF = {
    "あかさたなはまやらわがざだばぱ": "あ",
    "いきしちにひみりぎじぢびぴ": "い",
    "うくすつぬふむゆるぐずづぶぷ": "う",
    "えけせてねへめれげぜでべぺ": "え",
    "おこそとのほもよろごぞどぼぽ": "お",
}


def vowel_of(ch):
    for group, v in VOWEL_OF.items():
        if ch in group:
            return v
    return None


def head_kana(reading):
    return reading[0].translate(SMALL_MAP)


def tail_kana(reading):
    """語尾のかな。長音符は直前の母音に置き換える。"""
    s = reading.translate(SMALL_MAP)
    i = len(s) - 1
    while i >= 0 and s[i] == "ー":
        i -= 1
    if i < 0:
        return None
    ch = s[i]
    if len(s) - 1 > i:  # 末尾が長音だった
        return vowel_of(ch) or ch
    return ch


def download_dict():
    if os.path.exists(CACHE):
        return
    print("Mozc辞書をダウンロード中(初回のみ)...")
    with open(CACHE, "w", encoding="utf-8") as out:
        for i, url in enumerate(DICT_URLS):
            req = urllib.request.Request(url, headers={"User-Agent": "shiritori-gen/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                out.write(resp.read().decode("utf-8", errors="replace"))
            print(f"  [{i+1}/{len(DICT_URLS)}] 取得")


def build_pool():
    """辞書から、しりとりに使える一般名詞を抽出する。"""
    download_dict()
    seen = {}
    with open(CACHE, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            reading, lid, rid, cost, surface = parts[0], parts[1], parts[2], parts[3], parts[4]
            if lid != str(NOUN_ID) or rid != str(NOUN_ID):
                continue
            try:
                cost = int(cost)
            except ValueError:
                continue
            if cost > MAX_COST:
                continue
            if not (3 <= len(reading) <= 6) or not HIRAGANA.match(reading):
                continue
            if reading.endswith("ん"):       # しりとりが終わってしまうので除外
                continue
            if tail_kana(reading) is None:
                continue
            # 同じ読みは最も一般的(costが小さい)ものだけ残す
            if reading not in seen or cost < seen[reading]["cost"]:
                seen[reading] = {"reading": reading, "surface": surface, "cost": cost}
    pool = sorted(seen.values(), key=lambda w: w["cost"])
    with open(POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False)
    return pool


def load_pool():
    if os.path.exists(POOL_PATH):
        with open(POOL_PATH, encoding="utf-8") as f:
            return json.load(f)
    return build_pool()


def longest_chain(words):
    """ビットマスクDPで最長しりとりを厳密に求める。words は reading のリスト。"""
    n = len(words)
    heads = [head_kana(w) for w in words]
    tails = [tail_kana(w) for w in words]
    # adj[i] = i の次に繋げる単語のビットマスク
    adj = [0] * n
    for i in range(n):
        for j in range(n):
            if i != j and tails[i] == heads[j]:
                adj[i] |= 1 << j

    best_len, best_path = 0, []
    # dp[(mask, last)] = そこに至る最長経路(長さ, 経路)
    dp = {(1 << i, i): (1, [i]) for i in range(n)}
    frontier = list(dp.items())
    while frontier:
        nxt = []
        for (mask, last), (length, path) in frontier:
            if length > best_len:
                best_len, best_path = length, path
            cand = adj[last] & ~mask
            while cand:
                bit = cand & -cand
                j = bit.bit_length() - 1
                cand ^= bit
                key = (mask | bit, j)
                if key not in dp or dp[key][0] < length + 1:
                    dp[key] = (length + 1, path + [j])
                    nxt.append((key, dp[key]))
        frontier = nxt
    return best_len, best_path


def make_puzzle(pool, seed, size=WORDS_PER_PUZZLE, target_chain=8, tries=30):
    """その日の問題を作る。

    純粋なランダム抽選だと「16語中に長く繋がる部分列がある」確率が低く、
    生成の成功率も語の質も安定しない。そこで:
      1. まず target_chain 語のしりとり連鎖を、繋がる語を辿って意図的に構築する
      2. 残りを候補プールからランダムに埋める(埋め語同士がたまたま繋がって
         もっと長い解ができることもあるが、それは想定内でむしろ面白い)
    という順で組み立て、最後に longest_chain で本当の最長解を厳密に求め直す。
    """
    rng = random.Random(seed)
    kata = re.compile(r"^[ァ-ヴー]+$")
    has_ascii = re.compile(r"[A-Za-z0-9]")
    # 読みが長い(5〜6文字)語ほどビジネス/IT系の抽象語に偏る傾向があったので、
    # 3〜4文字の語だけに絞ることで日常語の割合を上げる。
    # その分母数が減るので、元プールはもっと広め(上位8000語)から取る。
    candidates = [w for w in pool
                  if not kata.match(w["surface"]) and not has_ascii.search(w["surface"])
                  and len(w["reading"]) in (3, 4)][:8000]

    by_head = {}
    for w in candidates:
        by_head.setdefault(head_kana(w["reading"]), []).append(w)

    for _ in range(tries):
        chain = [rng.choice(candidates)]
        used_readings = {chain[0]["reading"]}
        for _ in range(target_chain - 1):
            t = tail_kana(chain[-1]["reading"])
            opts = [w for w in by_head.get(t, []) if w["reading"] not in used_readings]
            if not opts:
                break
            nxt = rng.choice(opts)
            chain.append(nxt)
            used_readings.add(nxt["reading"])
        if len(chain) < target_chain:
            continue  # このシードでは連鎖が途切れた。作り直す

        remaining = [w for w in candidates if w["reading"] not in used_readings]
        filler = rng.sample(remaining, size - len(chain))
        picked = chain + filler
        rng.shuffle(picked)  # 出題順を混ぜて、どれが仕込みかを分からなくする

        readings = [w["reading"] for w in picked]
        best, path = longest_chain(readings)
        return {
            "words": [{"reading": w["reading"], "surface": w["surface"]} for w in picked],
            "best": best,
            "best_path": path,
        }
    return None


def main():
    pool = load_pool()
    print(f"単語プール: {len(pool)}語")
    print("上位20語(頻度順):", [w["surface"] for w in pool[:20]])
    print()

    days = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    puzzles = {}
    for d in range(days):
        key = f"day-{d}"
        p = make_puzzle(pool, seed=key)
        if not p:
            print(f"  {key}: 生成失敗")
            continue
        puzzles[key] = p
        chain = [p["words"][i]["reading"] for i in p["best_path"]]
        print(f"[{key}] 最長 {p['best']}語")
        print("  出題16語:", " / ".join(w["reading"] for w in p["words"]))
        print("  最長解  :", " → ".join(chain))
        print()

    with open(os.path.join(HERE, "puzzles.json"), "w", encoding="utf-8") as f:
        json.dump(puzzles, f, ensure_ascii=False, indent=2)
    print("puzzles.json に保存しました")


if __name__ == "__main__":
    main()

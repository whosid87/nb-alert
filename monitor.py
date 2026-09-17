"""
Joe's New Balance Outlet 재고 모니터
- 대상: Made in USA 993 (WR993BK), Wide (D), 사이즈 9 / 10
- 품절 -> 재고 입고로 바뀌는 순간에만 텔레그램 알림 (중복 알림 방지)

환경변수:
  TG_TOKEN    : 텔레그램 봇 토큰
  TG_CHAT_ID  : 알림 받을 chat id

사용:
  python monitor.py          # 1회 체크
  python monitor.py --test   # 텔레그램 테스트 메시지 + 현재 사이즈별 상태 출력
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

PID = "WR993V1-2382"
STYLE = "WR993BK"
WIDTH = "D"
TARGET_SIZES = ["9", "10"]

SITE = "https://www.joesnewbalanceoutlet.com"
VARIATION_URL = f"{SITE}/on/demandware.store/Sites-JNBO-Site/en_US/Product-Variation"
PAGE_URL = (f"{SITE}/pd/made-in-usa-993/{PID}.html"
            f"?dwvar_{PID}_style={STYLE}&dwvar_{PID}_width={WIDTH}")

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": PAGE_URL,
}


# ---------------- helpers ----------------
def http_get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON 응답이 아님 (봇 차단 가능성). 앞부분: {body[:200]!r}")


def variation_params(size_id=None):
    p = {
        f"dwvar_{PID}_style": STYLE,
        f"dwvar_{PID}_width": WIDTH,
        "pid": PID,
        "quantity": 1,
    }
    if size_id:
        p[f"dwvar_{PID}_size"] = size_id
    return VARIATION_URL + "?" + urllib.parse.urlencode(p)


def same_size(a, b):
    try:
        return float(str(a).strip()) == float(str(b).strip())
    except ValueError:
        return str(a).strip() == str(b).strip()


def send_telegram(text):
    token = os.environ["TG_TOKEN"]
    chat_id = os.environ["TG_CHAT_ID"]
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------- core ----------------
def check_stock():
    """{'9': {'in_stock': bool, 'msg': str}, '10': {...}} 반환"""
    data = http_get_json(variation_params())
    attrs = data["product"]["variationAttributes"]
    size_attr = next(a for a in attrs
                     if str(a.get("attributeId", a.get("id", ""))).lower() == "size")

    results = {}
    for target in TARGET_SIZES:
        val = next((v for v in size_attr["values"]
                    if same_size(v.get("displayValue", v.get("value")), target)), None)
        if val is None:
            results[target] = {"in_stock": False, "msg": "사이즈 옵션 없음"}
            continue

        selectable = bool(val.get("selectable"))
        # 사이즈까지 지정해서 한 번 더 조회 (정확한 주문 가능 여부)
        time.sleep(2)
        prod = http_get_json(variation_params(val["id"]))["product"]
        available = bool(prod.get("available"))
        msgs = [m for m in (prod.get("availability") or {}).get("messages", []) if m]

        results[target] = {
            "in_stock": selectable and available,
            "msg": " / ".join(msgs),
        }
    return results


def main():
    test_mode = "--test" in sys.argv
    state = load_state()

    try:
        results = check_stock()
    except Exception as e:
        print("체크 실패:", e)
        if not state.get("error"):  # 에러 알림은 연속 실패 시 1번만
            try:
                send_telegram(f"⚠️ 재고 모니터 오류\n{e}")
            except Exception as te:
                print("텔레그램 전송 실패:", te)
        state["error"] = str(e)
        save_state(state)
        return

    if state.get("error"):
        state.pop("error")

    print(json.dumps(results, ensure_ascii=False, indent=2))

    if test_mode:
        lines = [f"W{s} ({WIDTH}): {'재고 있음' if r['in_stock'] else '품절'} {r['msg']}"
                 for s, r in results.items()]
        send_telegram("✅ 테스트 메시지\n" + "\n".join(lines))

    for size, r in results.items():
        prev = state.get(size, False)
        if r["in_stock"] and not prev:
            send_telegram(
                f"👟 재고 입고!\nMade in USA 993 (WR993BK)\n"
                f"사이즈 {size} / Wide ({WIDTH})\n{r['msg']}\n\n{PAGE_URL}"
            )
        state[size] = r["in_stock"]

    save_state(state)


if __name__ == "__main__":
    main()

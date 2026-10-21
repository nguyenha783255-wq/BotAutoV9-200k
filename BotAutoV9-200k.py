# ==========================================================
# 👑 NESUX ROYAL BOT v9 — Anti-Burn · Anti-Spam · Deep AI
# Owners: @DENIUS09 & @deptrainhatvn
# ==========================================================

import telebot
import requests
import json
import time
import threading
import hashlib
import base64
import logging
import math
import socketio
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==================== WEBSOCKET DETECT ====================
try:
    import websocket
    HAS_WEBSOCKET = True
    WS_TRANSPORTS = ["websocket", "polling"]
    logger_init_ws = "websocket-client ✓"
except ImportError:
    HAS_WEBSOCKET = False
    WS_TRANSPORTS = ["polling"]
    logger_init_ws = "websocket-client ✗ (polling)"

# ==================== CONFIG ====================
BOT_TOKEN = "8952086579:AAEVBnz0qehsis7EHTe-kgWY4EzJZXl5dL8"
ALLOWED_USERNAMES = {"denius09", "deptrainhatvn"}
ALLOWED_IDS = {7749647263}

LOGIN_API = "https://apifo88daigia.tele68.com/api?c=3&un={username}&pw={pw_md5}&cp=R&cl=R&pf=web&at="
LOBBY_API = "https://wlb.tele68.com/v1/lobby/auth/login?cp=R&cl=R&pf=web&at="
HISTORY_API_MD5 = "https://wtxmd52.tele68.com/v1/txmd5/lite-sessions"
HISTORY_API_MD5_FB = "https://living-telecommunications-start-consoles.trycloudflare.com/api/txmd5"
WS_HOST = "https://wtxmd52.tele68.com"
WS_PATH = "txmd5/"
WS_NAMESPACE = "/txmd5"
PREDICT_API = "https://isa-bristol-investigate-outdoors.trycloudflare.com/lc79md5"
PREDICT_CACHE_TTL = 1.5

MAX_MARTINGALE = 6
API_STUCK_TIMEOUT = 3.5

# ==== V9 PROTECTION ====
LEVEL_QUALITY_GATE = {0: 0, 1: 30, 2: 40, 3: 50, 4: 60, 5: 70, 6: 80}
DRAWDOWN_WARN = 0.10        # 10%: giảm bet 30%
DRAWDOWN_REDUCE = 0.20      # 20%: giảm bet 60%
DRAWDOWN_STOP = 0.30        # 30%: dừng hoàn toàn
MAX_CONSECUTIVE_LOSSES = 6  # thua 6 phiên → dừng

# ==================== LOGGING ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Nesux")
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('socketio').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

bot = telebot.TeleBot(BOT_TOKEN)
_http = requests.Session()
_http.headers.update({"User-Agent": "Mozilla/5.0"})

user_state = {}
user_temp = {}
active_sockets = {}
active_states = {}
_predict_cache = {"data": None, "ts": 0}
_cache_lock = threading.Lock()


# ==================== AUTH ====================
def is_authorized(uid, username=None):
    if uid in ALLOWED_IDS: return True
    if username:
        un = str(username).lower().lstrip("@").strip()
        if un in ALLOWED_USERNAMES:
            ALLOWED_IDS.add(uid)
            logger.info(f"[AUTH] ✓ {uid} @{un}")
            return True
    return False

def msg_ok(m):
    try: return is_authorized(m.from_user.id, m.from_user.username)
    except: return False

def cq_ok(c):
    try: return is_authorized(c.from_user.id, c.from_user.username)
    except: return False


# ==================== FORMAT ====================
def _fmt(n):
    try: return f"{int(n):,}".replace(",", ".") + "đ"
    except: return str(n)

def _safe_delete(chat_id, msg_id):
    try: bot.delete_message(chat_id, msg_id)
    except: pass

def _normalize_pred(s):
    if not s: return None
    s = str(s).strip()
    if s in ("Tài", "TAI", "tài", "Tai", "tai"): return "Tài"
    if s in ("Xỉu", "XIU", "xỉu", "Xiu", "xiu"): return "Xỉu"
    return None

def _opposite(p): return "Xỉu" if p == "Tài" else "Tài"


# ==================== KEYBOARDS ====================
def kb_main():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("💎 AUTO BET TX MD5", callback_data="auto_start"))
    return kb

def kb_running():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🛑 DỪNG AUTO BET", callback_data="auto_stop"))
    return kb

def kb_home():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("👑 VỀ MENU", callback_data="home"))
    return kb


# ==================== WELCOME ====================
def welcome_text(first_name="Ông Chủ"):
    return (
        "╔══════════════════════╗\n"
        "     👑 <b>NESUX ROYAL</b> 👑\n"
        "╚══════════════════════╝\n\n"
        f"💎 Kính chào <b>{first_name}</b>,\n"
        "🏆 <b>Nesux v9</b> — <i>Anti-Burn Elite</i>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "♛ <b>Pattern Detection</b> — TXTXTX, TTXXTT\n"
        "♛ <b>Consensus Voting</b> — API + Market + Pattern\n"
        "♛ <b>Quality Gate</b> — gấp thếp thông minh\n"
        "♛ <b>Drawdown Shield</b> — bảo vệ vốn tự động\n"
        "♛ <b>Anti-Streak</b> — dừng khi thua 6 phiên\n"
        "♛ <b>Triple Lock</b> — 1 phiên = 1 cược\n"
        "♛ <b>No Spam</b> — không lặp tin nhắn\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 Bấm nút để bắt đầu"
    )


# ==================== HTTP APIs ====================
def fetch_predict(force=False):
    now = time.time()
    with _cache_lock:
        c = _predict_cache.get("data")
        ts = _predict_cache.get("ts", 0)
        if not force and c and (now - ts < PREDICT_CACHE_TTL):
            return c
    try:
        r = _http.get(PREDICT_API, timeout=6)
        r.raise_for_status()
        d = r.json()
        with _cache_lock:
            _predict_cache["data"] = d
            _predict_cache["ts"] = now
        return d
    except Exception as e:
        logger.warning(f"[PREDICT] {e}")
        if force: return {"_error": str(e)}
        with _cache_lock:
            c = _predict_cache.get("data")
        return c if c else {"_error": str(e)}

def fetch_history_md5(limit=60):
    for url in (HISTORY_API_MD5, HISTORY_API_MD5_FB):
        try:
            r = _http.get(url, headers={
                "User-Agent": "Mozilla/5.0", "Origin": "https://lc79b.bet"
            }, timeout=10)
            if r.status_code != 200: continue
            d = r.json()
            if not isinstance(d.get("list"), list): continue
            arr = sorted(d["list"], key=lambda x: x["id"])
            out = []
            for it in arr:
                p = it.get("point", sum(it.get("dices", [0, 0, 0])))
                rv = it.get("resultTruyenThong")
                if rv in ("TAI", "XIU"):
                    out.append({
                        "session": it["id"],
                        "dice": it.get("dices", [0, 0, 0]),
                        "total": p,
                        "result": rv,
                        "tx": "T" if p >= 11 else "X",
                    })
            if out: return out[-limit:]
        except Exception as e:
            logger.warning(f"[HIST] {url}: {e}")
    return []

def _md5(s): return hashlib.md5(s.encode()).hexdigest()

def lc_login_md5(username, pw_md5):
    try:
        url = LOGIN_API.format(username=username, pw_md5=pw_md5)
        r = requests.get(url, timeout=12).json()
        if not r.get("success"):
            return {"_error": "Sai TK/MK hoặc bị khoá"}
        if r.get("token") and not r.get("accessToken"):
            sk = r.get("sessionKey", "")
            try:
                nn = json.loads(base64.b64decode(
                    sk + "=" * ((4 - len(sk) % 4) % 4))).get("nickname") if sk else "user"
            except: nn = "user"
            return {"token": r["token"], "nickname": nn, "money": r.get("money", 0)}
        sk = r["sessionKey"] + "=" * ((4 - len(r["sessionKey"]) % 4) % 4)
        nn = json.loads(base64.b64decode(sk)).get("nickname")
        r2 = requests.post(LOBBY_API,
            json={"nickName": nn, "accessToken": r["accessToken"]}, timeout=12).json()
        if not r2.get("token"):
            return {"_error": "Không lấy token"}
        return {"token": r2["token"], "nickname": nn,
                "money": r2.get("remoteLoginResp", {}).get("money", 0)}
    except Exception as e:
        return {"_error": f"Lỗi: {e}"}

def lc_login(u, p):
    return lc_login_md5(u, _md5(p))


# ==========================================================
# 🧠 ANALYSIS v9 — Deep Intelligence
# ==========================================================

def _wilson_lower(wins, n, z=1.96):
    if n == 0: return 0.0
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - margin)

def _entropy(results):
    if not results: return 1.0
    pw = sum(1 for x in results if x == "T") / len(results)
    if pw <= 0 or pw >= 1: return 0.0
    return -(pw * math.log2(pw) + (1 - pw) * math.log2(1 - pw))

def _markov(results, order):
    if len(results) < order + 3: return None
    tgt = results[-order:]
    outs = []
    for i in range(len(results) - order):
        if results[i:i + order] == tgt:
            outs.append(results[i + order])
    if not outs: return None
    p_t = sum(1 for x in outs if x == "T") / len(outs)
    return {"p_t": p_t, "n": len(outs)}

def _streak_tx(results):
    if not results: return 0, 0
    ws_t = ws_x = 0
    for r in reversed(results):
        if r == "T":
            if ws_x > 0: break
            ws_t += 1
        else:
            if ws_t > 0: break
            ws_x += 1
    return ws_t, ws_x

def detect_pattern(raw_hist):
    """V9 NEW: Pattern detection TXTXTX, TTXXTT, TTTXXX."""
    if not raw_hist or len(raw_hist) < 6: return None
    results = [h["tx"] for h in raw_hist[-10:]]
    if len(results) < 6: return None
    last = results[-6:]

    # Alternating TXTXTX
    if all(last[i] != last[i-1] for i in range(1, 6)):
        return {"name": "alternating", "conf": 0.72,
                "next": "X" if last[-1] == "T" else "T"}

    # Double TTXXTT
    if last[0] == last[1] and last[2] == last[3] and last[4] == last[5]:
        if last[0] != last[2] and last[2] != last[4]:
            return {"name": "double", "conf": 0.62,
                    "next": "X" if last[-1] == "T" else "T"}

    # Triple TTTXXX
    if last[0] == last[1] == last[2] and last[3] == last[4] == last[5]:
        if last[0] != last[3]:
            return {"name": "triple_swap", "conf": 0.65,
                    "next": "X" if last[-1] == "T" else "T"}

    return None

def analyze_api_performance(lich_su):
    if not lich_su: return None
    settled = []
    for x in lich_su:
        if x.get("trang_thai") not in ("thang", "thua"): continue
        pred = x.get("du_doan")
        if pred not in ("Tài", "Xỉu"): continue
        settled.append({
            "session": x.get("phien", 0),
            "pred": pred,
            "correct": x["trang_thai"] == "thang",
            "conf": x.get("do_tin_cay", "0%"),
        })
    if len(settled) < 3: return None

    settled.sort(key=lambda x: x["session"], reverse=True)
    results = ["W" if x["correct"] else "L" for x in settled]

    total = len(results)
    wins = sum(1 for r in results if r == "W")
    overall_acc = wins / total
    wilson = _wilson_lower(wins, total)

    recent = results[:min(10, len(results))]
    recent_wins = sum(1 for r in recent if r == "W")
    recent_acc = recent_wins / len(recent) if recent else 0.5

    # V9: multi-window
    def acc_window(w):
        if len(results) < w: return None
        return sum(1 for r in results[:w] if r == "W") / w
    acc_5 = acc_window(5)
    acc_20 = acc_window(20)
    acc_50 = acc_window(50)

    ws = ls = 0
    for r in results:
        if r == "W":
            if ls > 0: break
            ws += 1
        else:
            if ws > 0: break
            ls += 1

    tai = [x for x in settled if x["pred"] == "Tài"]
    xiu = [x for x in settled if x["pred"] == "Xỉu"]
    acc_tai = sum(1 for x in tai if x["correct"]) / len(tai) if tai else 0.5
    acc_xiu = sum(1 for x in xiu if x["correct"]) / len(xiu) if xiu else 0.5

    buckets = {"60-70": [], "70-80": [], "80-90": [], "90-100": []}
    for x in settled:
        try:
            conf = float(str(x["conf"]).replace("%", "").strip())
        except: continue
        if conf >= 90: buckets["90-100"].append(x["correct"])
        elif conf >= 80: buckets["80-90"].append(x["correct"])
        elif conf >= 70: buckets["70-80"].append(x["correct"])
        elif conf >= 60: buckets["60-70"].append(x["correct"])
    calib = {b: {"n": len(v), "acc": (sum(v) / len(v)) if v else None}
             for b, v in buckets.items()}

    return {
        "overall_acc": overall_acc,
        "recent_acc": recent_acc,
        "wilson": wilson,
        "streak_w": ws, "streak_l": ls,
        "acc_5": acc_5, "acc_20": acc_20, "acc_50": acc_50,
        "acc_tai": acc_tai, "acc_xiu": acc_xiu,
        "n_tai": len(tai), "n_xiu": len(xiu), "n_total": total,
        "calib": calib,
    }

def analyze_market(raw_hist):
    if not raw_hist or len(raw_hist) < 10: return None
    results = [h["tx"] for h in raw_hist[-60:]]

    recent20 = results[-20:]
    wins_t = sum(1 for r in recent20 if r == "T")
    wilson_t = _wilson_lower(wins_t, len(recent20))

    mk2 = _markov(results, 2)
    mk3 = _markov(results, 3)
    ws_t, ws_x = _streak_tx(results)

    if len(results) >= 15:
        p_r = sum(1 for r in results[-5:] if r == "T") / 5
        p_o = sum(1 for r in results[-15:-5] if r == "T") / 10
        momentum = p_r - p_o
    else: momentum = 0.0

    ent = _entropy(results[-10:])

    if ent > 0.92: regime = "chaotic"
    elif ent < 0.35: regime = "calm"
    elif abs(momentum) > 0.20: regime = "trending"
    else: regime = "mixed"

    score_t = wilson_t * 100.0
    if mk2 and mk2["n"] >= 3:
        score_t += (mk2["p_t"] - 0.5) * 80 * min(1.0, mk2["n"] / 8)
    if mk3 and mk3["n"] >= 2:
        score_t += (mk3["p_t"] - 0.5) * 60 * min(1.0, mk3["n"] / 6)
    if ws_t >= 3:
        score_t += 15
        if ws_t >= 7: score_t -= 40
    elif ws_x >= 3:
        score_t -= 15
        if ws_x >= 7: score_t += 40
    score_t += momentum * 30

    market_t = max(0, min(100, score_t))
    market_pred = "T" if market_t > 50 else "X"
    market_conf = int(max(market_t, 100 - market_t))

    return {
        "market_pred": market_pred,
        "market_conf": market_conf,
        "regime": regime,
        "entropy": ent,
        "momentum": momentum,
        "streak_t": ws_t,
        "streak_x": ws_x,
    }

def get_consensus(api_pred, market, pattern):
    """V9 NEW: Vote consensus từ 3 nguồn."""
    votes = {}
    if api_pred:
        votes[api_pred] = votes.get(api_pred, 0) + 2.0
    if market:
        mp = "Tài" if market["market_pred"] == "T" else "Xỉu"
        votes[mp] = votes.get(mp, 0) + market["market_conf"] / 50
    if pattern:
        pp = "Tài" if pattern["next"] == "T" else "Xỉu"
        votes[pp] = votes.get(pp, 0) + pattern["conf"] * 2

    if not votes: return None
    top = max(votes.values())
    top_key = max(votes, key=votes.get)
    # Clear winner = top >= 1.5x second
    second = max((v for k, v in votes.items() if k != top_key), default=0)
    if second == 0 or top >= second * 1.4:
        return top_key
    return None


# ---------- DECISION v9 ----------
def decide_v9(api_data, raw_hist, state):
    """
    Returns dict:
    - {"stop": reason} if should stop
    - {"pause": reason} if should skip this session
    - {"pred","quality","mode","bet_amt","meta"} for normal bet
    - {"no_pred": True} if API no pred
    """
    # === EMERGENCY STOPS ===
    peak = state["peak_balance"]
    dd = (peak - state["balance"]) / max(1, peak)
    if dd >= DRAWDOWN_STOP:
        return {"stop": f"🛑 DRAWDOWN {dd*100:.0f}% ≥ {DRAWDOWN_STOP*100:.0f}%\n"
                        f"💎 Peak: {_fmt(peak)} · Hiện: {_fmt(state['balance'])}"}
    if state["streak_l"] >= MAX_CONSECUTIVE_LOSSES:
        return {"stop": f"🛑 THUA {state['streak_l']} PHIÊN LIÊN TIẾP\n"
                        f"💎 Số dư: {_fmt(state['balance'])}\n"
                        f"🛡 Dừng bảo vệ vốn!"}

    # === PRED ===
    api_pred = _normalize_pred(api_data.get("du_doan"))
    if not api_pred:
        return {"no_pred": True}

    try:
        cur_conf = float(str(api_data.get("do_tin_cay", "50")).replace("%", "").strip())
    except: cur_conf = 50

    perf = analyze_api_performance(api_data.get("lich_su", []))
    market = analyze_market(raw_hist)
    pattern = detect_pattern(raw_hist)

    # === MODE (FADE / FOLLOW) ===
    pred = api_pred
    mode = "follow"
    reason = ""

    if perf:
        side_acc = perf["acc_tai"] if api_pred == "Tài" else perf["acc_xiu"]
        side_n = perf["n_tai"] if api_pred == "Tài" else perf["n_xiu"]
        fade_reasons = []

        if perf["streak_l"] >= 4:
            fade_reasons.append(f"API thua {perf['streak_l']} phiên")
        elif perf["recent_acc"] < 0.30 and perf["streak_l"] >= 2:
            fade_reasons.append(f"Recent {perf['recent_acc']*100:.0f}%")
        if side_n >= 5 and side_acc < 0.30:
            fade_reasons.append(f"'{api_pred}' đúng {side_acc*100:.0f}%")
        if cur_conf >= 60:
            bk = None
            if cur_conf >= 90: bk = "90-100"
            elif cur_conf >= 80: bk = "80-90"
            elif cur_conf >= 70: bk = "70-80"
            elif cur_conf >= 60: bk = "60-70"
            if bk:
                b = perf["calib"].get(bk, {})
                if b.get("n", 0) >= 5 and b.get("acc") is not None:
                    if b["acc"] < (cur_conf/100) * 0.5:
                        fade_reasons.append(f"Conf {cur_conf:.0f}% thật {b['acc']*100:.0f}%")

        if fade_reasons:
            pred = _opposite(api_pred)
            mode = "fade"
            reason = " · ".join(fade_reasons[:2])
        elif perf["streak_w"] >= 3 and perf["recent_acc"] >= 0.65:
            mode = "follow_hot"
            reason = f"API nóng {perf['streak_w']}W · {perf['recent_acc']*100:.0f}%"
        else:
            reason = f"API {perf['overall_acc']*100:.0f}%"

    # === QUALITY ===
    q = 50.0
    if perf:
        q += (perf["wilson"] - 0.5) * 60
        q += (perf["recent_acc"] - 0.5) * 40
        side_acc = perf["acc_tai"] if api_pred == "Tài" else perf["acc_xiu"]
        q += (side_acc - 0.5) * 50
        if perf["streak_w"] >= 3: q += 12
        elif perf["streak_w"] == 2: q += 6
        if perf["streak_l"] >= 3: q -= 15
        elif perf["streak_l"] == 2: q -= 8

    if market:
        mp = "Tài" if market["market_pred"] == "T" else "Xỉu"
        if mp == pred:
            q += 15 * (market["market_conf"] / 100)
        else:
            q -= 10 * (market["market_conf"] / 100)
        if market["regime"] == "chaotic": q -= 12
        elif market["regime"] == "calm": q += 8

    # V9: pattern bonus
    if pattern:
        pp = "Tài" if pattern["next"] == "T" else "Xỉu"
        if pp == pred: q += 8
        else: q -= 5

    # V9: consensus check
    consensus = get_consensus(api_pred if mode != "fade" else pred, market, pattern)
    if consensus and consensus != pred: q -= 15
    elif consensus == pred: q += 10

    q += (cur_conf - 75) * 0.3
    q = max(0, min(100, int(q)))

    # === QUALITY GATE FOR MARTINGALE ===
    level = state["martingale"]
    required = LEVEL_QUALITY_GATE.get(level, 80)
    if level > 0 and q < required:
        return {"pause":
                f"⏸ PAUSE · Lv {level} cần quality ≥{required}\n"
                f"🛡 Quality hiện: {q} (thấp) — chờ phiên tốt hơn"}

    # === SMART BET SIZING ===
    level_cap = min(level, MAX_MARTINGALE)
    base_scale = 1.0
    if dd >= DRAWDOWN_REDUCE: base_scale = 0.4
    elif dd >= DRAWDOWN_WARN: base_scale = 0.7

    if level == 0:
        if q >= 75: q_scale = 1.0
        elif q >= 60: q_scale = 0.9
        elif q >= 50: q_scale = 0.75
        else: q_scale = 0.5
    else:
        q_scale = 1.0

    bet_amt = int(state["base_bet"] * (2 ** level_cap) * base_scale * q_scale)

    meta = {
        "perf": perf, "market": market, "pattern": pattern,
        "conf": cur_conf, "reason": reason, "consensus": consensus,
        "dd": dd, "base_scale": base_scale, "q_scale": q_scale,
    }
    logger.info(f"[DECIDE] mode={mode} pred={pred} q={q} dd={dd:.2f} "
                f"Lv={level} bet={bet_amt} pattern={pattern}")

    return {"pred": pred, "quality": q, "mode": mode,
            "bet_amt": bet_amt, "level": level_cap, "meta": meta}


def quality_label(q):
    if q >= 80: return "🔥 ELITE"
    if q >= 70: return "⚡ STRONG"
    if q >= 60: return "💪 GOOD"
    if q >= 50: return "🛡 CAUTIOUS"
    return "🧊 DEFENSIVE"

def mode_label(mode):
    return {"follow": "📊 FOLLOW", "follow_hot": "🔥 FOLLOW HOT",
            "fade": "🔄 FADE", "fallback": "⚠️ FALLBACK"}.get(mode, mode)


# ==================== BET EMIT ONCE (FIX SPAM) ====================
def _emit_bet_once(sio, side, amount, namespace):
    """Emit bet EXACTLY ONCE. No retry to prevent double-bet."""
    try:
        if sio is None or not sio.connected:
            logger.warning("[BET-EMIT] socket not connected")
            return False
        sio.emit("bet", {"type": side, "amount": amount}, namespace=namespace)
        logger.info(f"[BET-EMIT-OK] {side} {amount}")
        return True
    except Exception as e:
        logger.error(f"[BET-EMIT-FAIL] {e}")
        return False


# ==================== STOP ====================
def _stop_auto(uid, reason="", celebrate=False):
    st = active_states.get(uid)
    if st: st["running"] = False
    if uid in active_sockets:
        try: active_sockets[uid].disconnect()
        except: pass
    user_temp.pop(uid, None)
    user_state.pop(uid, None)
    if not reason: return
    try:
        if celebrate:
            bot.send_message(uid, reason, parse_mode="HTML", reply_markup=kb_main())
        else:
            bot.send_message(uid,
                f"🛑 <b>{reason}</b>\n"
                "╔══════════════════════╗\n"
                "   🛑 AUTO BET ĐÃ DỪNG\n"
                "╚══════════════════════╝",
                parse_mode="HTML", reply_markup=kb_main())
    except: pass

def _stop_async(uid, reason="", celebrate=False):
    def _run():
        time.sleep(0.3)
        _stop_auto(uid, reason, celebrate)
    threading.Thread(target=_run, daemon=True).start()


# ==========================================================
# 🎰 AUTO BET ENGINE v9
# ==========================================================
def start_auto_bet(uid, temp):
    if uid in active_sockets:
        try: active_sockets[uid].disconnect()
        except: pass
        active_sockets.pop(uid, None)

    state = {
        "running": True,
        "username": temp.get("username", ""),
        "pw_md5": temp.get("pw_md5", ""),
        "nickname": temp["nickname"],
        "start_balance": temp["money"],
        "peak_balance": temp["money"],
        "base_bet": temp["base_bet"],
        "target_profit": temp["target"],
        "martingale": 0,
        "balance": temp["money"],
        # === V9 ANTI-SPAM LOCKS ===
        "bet_lock": threading.Lock(),
        "emitted_sessions": set(),  # Session IDs đã bet
        "current_session_id": None,
        "last_result_session_id": None,
        "raw_hist": [],
        "betting_started_at": None,
        "prediction": None,
        "bet_amount": None,
        "quality_used": None,
        "mode_used": None,
        "display_session": None,
        "waiting_result": False,
        "wins": 0, "losses": 0, "refunds": 0, "pauses": 0,
        "total_profit": 0,
        "streak_w": 0, "streak_l": 0,
    }
    active_states[uid] = state

    try:
        init_hist = fetch_history_md5(60)
        if init_hist:
            state["raw_hist"] = init_hist
            logger.info(f"[INIT-HIST] {len(init_hist)} sessions")
    except: pass

    attempt = 0
    while state.get("running"):
        sio = None
        try:
            if attempt > 0:
                logger.info(f"[LOOP] re-login attempt {attempt}")
                if temp.get("username") and temp.get("pw_md5"):
                    res = lc_login_md5(temp["username"], temp["pw_md5"])
                    if "_error" not in res:
                        temp["token"] = res["token"]
                        state["balance"] = res.get("money", state["balance"])
                    else:
                        attempt += 1
                        if attempt > 6:
                            _stop_auto(uid, f"Re-login fail: {res['_error']}")
                            return
                        time.sleep(10); continue

            if uid in active_sockets:
                try: active_sockets[uid].disconnect()
                except: pass

            sio = socketio.Client(
                reconnection=True, reconnection_attempts=999,
                reconnection_delay=3, logger=False, engineio_logger=False,
            )
            active_sockets[uid] = sio

            # ============ CONNECT ============
            @sio.event(namespace=WS_NAMESPACE)
            def connect():
                if not state.get("running"): return
                logger.info(f"[CONNECT] uid={uid} transports={WS_TRANSPORTS}")
                try:
                    arr = fetch_history_md5(60)
                    if arr: state["raw_hist"] = arr
                except: pass
                try:
                    peak = state["peak_balance"]
                    dd = (peak - state["balance"]) / max(1, peak) if peak > 0 else 0
                    tn = "🌐 WebSocket" if HAS_WEBSOCKET else "🌐 Polling"
                    bot.send_message(uid,
                        "╔══════════════════════╗\n"
                        "   🟢 <b>NESUX v9 ONLINE</b>\n"
                        "╚══════════════════════╝\n"
                        f"👤 <b>{state['nickname']}</b>\n"
                        f"💰 Số dư: <b>{_fmt(state['balance'])}</b>\n"
                        f"🎯 Mục tiêu: <b>+{_fmt(state['target_profit'])}</b>\n"
                        f"💎 Vốn gốc: <b>{_fmt(state['base_bet'])}</b>\n"
                        f"🔁 Martingale: <b>Lv {state['martingale']}</b>\n"
                        f"📉 Drawdown: <b>{dd*100:.1f}%</b>\n"
                        f"🔌 {tn}\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "🛡 <b>Anti-Burn Shield</b> đã bật\n"
                        "⏳ <i>Chờ phiên...</i>",
                        parse_mode="HTML", reply_markup=kb_running())
                except: pass

            # ============ NEW SESSION ============
            @sio.on('new-session', namespace=WS_NAMESPACE)
            def on_new_session(data):
                if not state.get("running"): return
                try:
                    sid = data.get("id") or data.get("sessionId") or data.get("session_id")
                    if sid is None: return
                    if str(sid) == str(state.get("current_session_id")):
                        return  # duplicate
                    state["current_session_id"] = sid
                    state["display_session"] = sid
                    state["betting_started_at"] = None
                    state["prediction"] = None
                    state["bet_amount"] = None
                    state["waiting_result"] = False
                    logger.info(f"[NEW] sid={sid}")
                except Exception as e:
                    logger.error(f"[NEW] {e}")

            # ============ TICK — CORE BET LOGIC ============
            @sio.on('tick-update', namespace=WS_NAMESPACE)
            def on_tick(data):
                if not state.get("running"): return
                try:
                    if data.get("state") != "BETTING": return

                    # Sync session from tick if missed
                    tick_sid = data.get("sessionId") or data.get("id")
                    if tick_sid and str(tick_sid) != str(state.get("current_session_id")):
                        state["current_session_id"] = tick_sid
                        state["display_session"] = tick_sid
                        state["betting_started_at"] = None
                        state["waiting_result"] = False
                        logger.info(f"[TICK-NEW] sid={tick_sid}")

                    current_sid = state.get("current_session_id")
                    if current_sid is None: return
                    sid_str = str(current_sid)

                    # 🔒 V9 BULLETPROOF LOCK
                    with state["bet_lock"]:
                        # Check 1: already emitted for this session
                        if sid_str in state["emitted_sessions"]:
                            return
                        # Check 2: currently waiting result
                        if state.get("waiting_result"):
                            return

                        if state["betting_started_at"] is None:
                            state["betting_started_at"] = time.time()
                        elapsed = time.time() - state["betting_started_at"]

                        # === ANALYZE ===
                        api = fetch_predict(force=True)
                        api_ok = bool(api) and not api.get("_error")

                        if not api_ok:
                            if elapsed < API_STUCK_TIMEOUT:
                                return
                            # Fallback
                            pred = "Tài"
                            quality = 20
                            mode = "fallback"
                            bet_amt = int(state["base_bet"] * (2 ** min(state["martingale"], MAX_MARTINGALE)))
                            meta = None
                            logger.warning(f"[FALLBACK] pred={pred}")
                        else:
                            res = decide_v9(api, state["raw_hist"], state)
                            if "stop" in res:
                                _stop_async(uid, res["stop"])
                                return
                            if "pause" in res:
                                state["pauses"] += 1
                                state["emitted_sessions"].add(sid_str)  # đánh dấu đã xử lý
                                try:
                                    bot.send_message(uid,
                                        "╔══════════════════════╗\n"
                                        "   ⏸ <b>PAUSE PHIÊN</b>\n"
                                        "╚══════════════════════╝\n"
                                        f"🎲 Phiên: <code>#{sid_str}</code>\n"
                                        f"{res['pause']}\n"
                                        "━━━━━━━━━━━━━━━━━━\n"
                                        "🛡 <i>Không cược phiên này để bảo vệ vốn</i>",
                                        parse_mode="HTML", reply_markup=kb_running())
                                except: pass
                                return
                            if "no_pred" in res:
                                return
                            pred = res["pred"]
                            quality = res["quality"]
                            mode = res["mode"]
                            bet_amt = res["bet_amt"]
                            meta = res["meta"]

                        # === BALANCE CHECK ===
                        if bet_amt > state["balance"]:
                            _stop_async(uid,
                                f"⚠️ SỐ DƯ KHÔNG ĐỦ\n"
                                f"💰 Cần: {_fmt(bet_amt)} · Có: {_fmt(state['balance'])}")
                            return

                        # === EMIT ONCE (no retry) ===
                        side = "TAI" if pred == "Tài" else "XIU"
                        ok = _emit_bet_once(sio, side, bet_amt, WS_NAMESPACE)
                        if not ok:
                            logger.error("[TICK] emit failed — retry next tick")
                            return  # Don't add to emitted, allow retry

                        # === MARK EMITTED ===
                        state["emitted_sessions"].add(sid_str)
                        # Prune old sessions
                        if len(state["emitted_sessions"]) > 200:
                            keep = list(state["emitted_sessions"])[-100:]
                            state["emitted_sessions"] = set(keep)

                        state["prediction"] = pred
                        state["bet_amount"] = bet_amt
                        state["quality_used"] = quality
                        state["mode_used"] = mode
                        state["waiting_result"] = True

                    # === MESSAGE (outside lock) ===
                    level = state["martingale"]
                    emoji = "🔵" if pred == "Tài" else "🔴"
                    next_lv = min(level + 1, MAX_MARTINGALE)
                    next_bet = int(state["base_bet"] * (2 ** next_lv))

                    lines = [
                        "╔══════════════════════╗",
                        f"   💎 <b>ĐẶT CƯỢC</b> · <code>#{sid_str}</code>",
                        "╚══════════════════════╝",
                        f"🎯 Cửa: <b>{emoji} {pred.upper()}</b>",
                        f"🎖 Mode: <b>{mode_label(mode)}</b>",
                        f"🛡 Quality: <b>{quality}/100</b> — {quality_label(quality)}",
                        "━━━━━━━━━━━━━━━━━━",
                        f"💰 Cược: <b>{_fmt(bet_amt)}</b>",
                        f"🔁 Martingale: <b>Lv {level}</b> (× {2**level})",
                        f"📌 Nếu thua: Lv {next_lv} → {_fmt(next_bet)}",
                    ]
                    if meta and meta.get("perf"):
                        p = meta["perf"]
                        lines.append("━━━━━━━━━━━━━━━━━━")
                        lines.append(
                            f"🎖 API: <b>{p['overall_acc']*100:.0f}%</b> · "
                            f"Recent <b>{p['recent_acc']*100:.0f}%</b> · "
                            f"{p['streak_w']}W/{p['streak_l']}L")
                        lines.append(
                            f"📊 Side: T={p['acc_tai']*100:.0f}% · "
                            f"X={p['acc_xiu']*100:.0f}%")
                        if meta.get("pattern"):
                            pat = meta["pattern"]
                            lines.append(f"🎨 Pattern: <b>{pat['name']}</b> "
                                         f"(conf {pat['conf']*100:.0f}%)")
                        if mode == "fade":
                            lines.append(f"💡 <i>{meta['reason']}</i>")
                    lines.append("⏳ <i>Chờ kết quả...</i>")
                    try:
                        bot.send_message(uid, "\n".join(lines),
                                         parse_mode="HTML", reply_markup=kb_running())
                    except: pass

                except Exception as e:
                    logger.error(f"[TICK] {e}")

            # ============ BET RESULT ============
            @sio.on('bet-result', namespace=WS_NAMESPACE)
            def on_bet_result(data):
                if not state.get("running"): return
                try:
                    if "postBalance" in data:
                        state["balance"] = data["postBalance"]
                        if state["balance"] > state["peak_balance"]:
                            state["peak_balance"] = state["balance"]
                except: pass

            # ============ SESSION RESULT ============
            @sio.on('session-result', namespace=WS_NAMESPACE)
            def on_result(data):
                if not state.get("running"): return
                try:
                    if "postBalance" in data:
                        state["balance"] = data["postBalance"]
                        if state["balance"] > state["peak_balance"]:
                            state["peak_balance"] = state["balance"]

                    result_sid = data.get("id") or state.get("current_session_id")
                    if result_sid and str(result_sid) == str(state.get("last_result_session_id")):
                        return  # dedup

                    if not state.get("waiting_result"):
                        return

                    raw = (data.get("resultTruyenThong") or "").strip().upper()
                    dices = data.get("dices", [0, 0, 0])
                    dice_str = " - ".join(str(x) for x in dices)
                    total_dice = sum(dices)
                    sid = result_sid or state.get("display_session") or "?"

                    if raw == "TAI":
                        actual, is_refund = "Tài", False
                    elif raw == "XIU":
                        actual, is_refund = "Xỉu", False
                    elif raw:
                        actual, is_refund = "Hoàn tiền", True
                    else:
                        return

                    pred = state.get("prediction")
                    bet_amt = state.get("bet_amount", 0)
                    level_used = min(state["martingale"], MAX_MARTINGALE)
                    if not pred:
                        state["waiting_result"] = False
                        state["last_result_session_id"] = result_sid
                        return

                    if not is_refund:
                        state["raw_hist"].append({
                            "session": sid, "dice": dices,
                            "total": total_dice, "result": raw,
                            "tx": "T" if total_dice >= 11 else "X",
                        })
                        if len(state["raw_hist"]) > 500:
                            state["raw_hist"].pop(0)

                    # REFUND
                    if is_refund:
                        state["refunds"] += 1
                        state["waiting_result"] = False
                        state["last_result_session_id"] = result_sid
                        state["prediction"] = None
                        state["bet_amount"] = None
                        try:
                            bot.send_message(uid,
                                "╔══════════════════════╗\n"
                                f"   💚 <b>HOÀN TIỀN</b> · <code>#{sid}</code>\n"
                                "╚══════════════════════╝\n"
                                f"🎲 Xúc xắc: <b>{dice_str}</b> = <b>{total_dice}</b>\n"
                                f"📌 Kết quả: <b>HOÀN TIỀN</b>\n"
                                f"🎯 Cược: <b>{pred.upper()}</b>\n"
                                "━━━━━━━━━━━━━━━━━━\n"
                                f"💚 Hoàn: <b>{_fmt(bet_amt)}</b>\n"
                                f"🔁 Martingale: <b>Lv {level_used}</b> (giữ)\n"
                                f"💰 Số dư: <b>{_fmt(state['balance'])}</b>\n"
                                f"📊 Bot: {state['wins']}W · {state['losses']}L · {state['refunds']}R",
                                parse_mode="HTML", reply_markup=kb_running())
                        except: pass
                        return

                    win = (pred == actual)
                    state["waiting_result"] = False
                    state["last_result_session_id"] = result_sid

                    if win:
                        profit = int(bet_amt * 0.98)
                        state["wins"] += 1
                        state["streak_w"] += 1
                        state["streak_l"] = 0
                        state["total_profit"] += profit
                        state["martingale"] = 0
                        lines = [
                            "╔══════════════════════╗",
                            f"   🏆 <b>THẮNG</b> · <code>#{sid}</code>",
                            "╚══════════════════════╝",
                            f"🎲 Xúc xắc: <b>{dice_str}</b> = <b>{total_dice}</b>",
                            f"📌 Kết quả: <b>{actual.upper()}</b>",
                            f"🎯 Cược: <b>{pred.upper()}</b> · Lv {level_used}",
                            "━━━━━━━━━━━━━━━━━━",
                            f"✅ <b>+{_fmt(profit)}</b> 💰",
                            f"💰 Số dư: <b>{_fmt(state['balance'])}</b>",
                            f"🔁 Martingale: <b>Lv {level_used} → 0</b> ✅",
                            f"🔥 Chuỗi thắng: <b>{state['streak_w']}</b>",
                            f"📊 Bot: {state['wins']}W · {state['losses']}L · {state['refunds']}R",
                            f"📈 Tổng lãi: <b>{_fmt(state['total_profit'])}</b>",
                        ]
                    else:
                        state["losses"] += 1
                        state["streak_l"] += 1
                        state["streak_w"] = 0
                        state["total_profit"] -= bet_amt
                        state["martingale"] = min(state["martingale"] + 1, MAX_MARTINGALE)
                        new_lv = state["martingale"]
                        next_bet = int(state["base_bet"] * (2 ** new_lv))
                        peak = state["peak_balance"]
                        dd = (peak - state["balance"]) / max(1, peak)
                        lines = [
                            "╔══════════════════════╗",
                            f"   💔 <b>THUA</b> · <code>#{sid}</code>",
                            "╚══════════════════════╝",
                            f"🎲 Xúc xắc: <b>{dice_str}</b> = <b>{total_dice}</b>",
                            f"📌 Kết quả: <b>{actual.upper()}</b>",
                            f"🎯 Cược: <b>{pred.upper()}</b> · Lv {level_used}",
                            "━━━━━━━━━━━━━━━━━━",
                            f"❌ <b>-{_fmt(bet_amt)}</b>",
                            f"💰 Số dư: <b>{_fmt(state['balance'])}</b>",
                            f"🔁 Martingale: <b>Lv {level_used} → {new_lv}</b>",
                            f"📌 Phiên tới: <b>{_fmt(next_bet)}</b>",
                            f"💀 Chuỗi thua: <b>{state['streak_l']}</b>",
                            f"📉 Drawdown: <b>{dd*100:.1f}%</b>",
                            f"📊 Bot: {state['wins']}W · {state['losses']}L · {state['refunds']}R",
                            f"📉 Tổng: <b>{_fmt(state['total_profit'])}</b>",
                        ]

                    state["prediction"] = None
                    state["bet_amount"] = None

                    try:
                        bot.send_message(uid, "\n".join(lines),
                                         parse_mode="HTML", reply_markup=kb_running())
                    except: pass

                    # === STOP CONDITIONS ===
                    target = state["start_balance"] + state["target_profit"]
                    if state["balance"] >= target:
                        profit = state["balance"] - state["start_balance"]
                        _stop_async(uid,
                            "╔══════════════════════╗\n"
                            "   🎉 <b>CHỐT LÃI THÀNH CÔNG</b> 🎉\n"
                            "╚══════════════════════╝\n\n"
                            f"👑 Chúc mừng <b>{state['nickname']}</b>!\n"
                            "━━━━━━━━━━━━━━━━━━\n"
                            f"💰 Vốn đầu: <b>{_fmt(state['start_balance'])}</b>\n"
                            f"💎 Số dư: <b>{_fmt(state['balance'])}</b>\n"
                            f"🏆 Lợi nhuận: <b>+{_fmt(profit)}</b>\n"
                            f"🎯 Mục tiêu: <b>{_fmt(state['target_profit'])}</b>\n"
                            "━━━━━━━━━━━━━━━━━━\n"
                            f"✅ Thắng: <b>{state['wins']}</b> · "
                            f"❌ Thua: <b>{state['losses']}</b> · "
                            f"💚 Hoàn: <b>{state['refunds']}</b> · "
                            f"⏸ Pause: <b>{state['pauses']}</b>\n"
                            "━━━━━━━━━━━━━━━━━━\n"
                            "🥂 <i>Dừng an toàn — bảo toàn lợi nhuận!</i>",
                            celebrate=True)
                        return

                    # V9: DRAWDOWN CHECK
                    dd_now = (state["peak_balance"] - state["balance"]) / max(1, state["peak_balance"])
                    if dd_now >= DRAWDOWN_STOP:
                        _stop_async(uid,
                            f"🛑 <b>DRAWDOWN SHIELD KÍCH HOẠT</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"📉 Drawdown: <b>{dd_now*100:.1f}%</b> (ngưỡng {DRAWDOWN_STOP*100:.0f}%)\n"
                            f"💎 Peak: <b>{_fmt(state['peak_balance'])}</b>\n"
                            f"💰 Hiện: <b>{_fmt(state['balance'])}</b>\n"
                            f"📊 Bot: {state['wins']}W · {state['losses']}L · {state['refunds']}R\n"
                            "🛡 Dừng để bảo vệ vốn!")
                        return

                    if state["streak_l"] >= MAX_CONSECUTIVE_LOSSES:
                        _stop_async(uid,
                            f"🛑 <b>ANTI-STREAK KÍCH HOẠT</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"💀 Thua liên tiếp: <b>{state['streak_l']} phiên</b>\n"
                            f"💎 Số dư: <b>{_fmt(state['balance'])}</b>\n"
                            "🛡 Dừng chờ API ấm lại!")
                        return

                    if not win and state["martingale"] >= MAX_MARTINGALE:
                        _stop_async(uid,
                            f"🛑 <b>MAX MARTINGALE</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"⚠️ Đã thua ở Lv {level_used} (×{2**level_used})\n"
                            f"💎 Số dư: <b>{_fmt(state['balance'])}</b>\n"
                            f"📉 Tổng lỗ: <b>{_fmt(state['total_profit'])}</b>\n"
                            "🛡 Dừng để bảo vệ vốn!")
                        return

                    next_check = int(state["base_bet"] * (2 ** min(state["martingale"], MAX_MARTINGALE)))
                    if state["balance"] < next_check:
                        _stop_async(uid,
                            f"⚠️ SỐ DƯ KHÔNG ĐỦ\n"
                            f"💰 Cần max: {_fmt(next_check)}\n"
                            f"💎 Có: {_fmt(state['balance'])}")
                        return

                except Exception as e:
                    logger.error(f"[RESULT] {e}")

            @sio.event(namespace=WS_NAMESPACE)
            def connect_error(data):
                logger.error(f"[CE] uid={uid} {data}")

            @sio.event(namespace=WS_NAMESPACE)
            def disconnect():
                logger.info(f"[DC] uid={uid}")

            logger.info(f"[CONNECT-TRY] uid={uid} transports={WS_TRANSPORTS}")
            sio.connect(
                WS_HOST, socketio_path=WS_PATH,
                namespaces=[WS_NAMESPACE],
                transports=WS_TRANSPORTS,
                auth={"token": temp["token"]},
                wait_timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Origin": "https://lc79b.bet",
                    "Referer": "https://lc79b.bet/",
                }
            )
            attempt = 0
            sio.wait()
            logger.info(f"[LOOP] uid={uid} sio.wait() returned")

        except Exception as e:
            logger.error(f"[LOOP] uid={uid} exception: {e}")

        if not state.get("running"): break
        attempt += 1
        if attempt > 10:
            _stop_auto(uid, "Socket không ổn định")
            break
        logger.info(f"[LOOP] uid={uid} reconnect 5s")
        time.sleep(5)

    if active_sockets.get(uid) is sio:
        active_sockets.pop(uid, None)
    if active_states.get(uid) is state:
        active_states.pop(uid, None)
    logger.info(f"[LOOP] uid={uid} ended")


# ==================== HANDLERS ====================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if not msg_ok(message): return
    uid = message.from_user.id
    user_state.pop(uid, None); user_temp.pop(uid, None)
    if uid in active_states:
        try:
            bot.send_message(message.chat.id,
                "💎 <b>ĐANG AUTO BET</b>\nBấm 🛑 để dừng.",
                parse_mode="HTML", reply_markup=kb_running())
        except: pass
        return
    try:
        bot.send_message(message.chat.id,
            welcome_text(message.from_user.first_name or "Ông Chủ"),
            parse_mode="HTML", reply_markup=kb_main())
    except: pass


@bot.callback_query_handler(func=lambda c: True)
def on_callback(cq):
    if not cq_ok(cq): return
    try: bot.answer_callback_query(cq.id)
    except: pass

    uid = cq.from_user.id
    chat_id = cq.message.chat.id
    msg_id = cq.message.message_id
    data = cq.data

    if data == "home":
        user_state.pop(uid, None); user_temp.pop(uid, None)
        if uid in active_states:
            try:
                bot.edit_message_text("💎 <b>ĐANG AUTO BET</b>",
                    chat_id=chat_id, message_id=msg_id,
                    parse_mode="HTML", reply_markup=kb_running())
            except: pass
            return
        try:
            bot.edit_message_text(
                welcome_text(cq.from_user.first_name or "Ông Chủ"),
                chat_id=chat_id, message_id=msg_id,
                parse_mode="HTML", reply_markup=kb_main())
        except: pass
        return

    if data == "auto_start":
        if uid in active_states:
            try: bot.answer_callback_query(cq.id, "⚠️ Đang auto bet!", show_alert=True)
            except: pass
            return
        user_state[uid] = "login_username"
        user_temp[uid] = {}
        try:
            bot.edit_message_text(
                "╔══════════════════════╗\n"
                "   💎 <b>AUTO BET TX MD5</b> 💎\n"
                "╚══════════════════════╝\n\n"
                "🔐 <b>BƯỚC 1/4 — TÊN ĐĂNG NHẬP</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "👉 Gửi <b>tên đăng nhập</b> game.\n"
                "🛡 <i>Tin nhắn sẽ tự xoá.</i>",
                chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        except: pass
        return

    if data == "auto_stop":
        if uid not in active_states:
            try: bot.answer_callback_query(cq.id, "Không có phiên.", show_alert=True)
            except: pass
            return
        _stop_auto(uid, "BẠN ĐÃ DỪNG AUTO BET THỦ CÔNG")
        return


# ==================== STATE FLOW ====================
@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == "login_username",
                     content_types=["text"])
def h_username(message):
    if not msg_ok(message): return
    uid = message.from_user.id
    txt = (message.text or "").strip()
    if txt.startswith("/"):
        user_state.pop(uid, None); user_temp.pop(uid, None)
        cmd_start(message); return
    if not txt: return
    user_temp.setdefault(uid, {})["username"] = txt
    user_state[uid] = "login_password"
    _safe_delete(message.chat.id, message.message_id)
    try:
        bot.send_message(message.chat.id,
            "╔══════════════════════╗\n"
            "   💎 <b>AUTO BET TX MD5</b> 💎\n"
            "╚══════════════════════╝\n\n"
            "🔐 <b>BƯỚC 2/4 — MẬT KHẨU</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "👉 Gửi <b>mật khẩu</b> game.\n"
            "🛡 <i>Tin nhắn sẽ tự xoá.</i>",
            parse_mode="HTML")
    except: pass


@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == "login_password",
                     content_types=["text"])
def h_password(message):
    if not msg_ok(message): return
    uid = message.from_user.id
    pw = (message.text or "").strip()
    _safe_delete(message.chat.id, message.message_id)
    if not pw: return
    user_temp.setdefault(uid, {})["password"] = pw
    user_state[uid] = "base_bet"
    try:
        bot.send_message(message.chat.id,
            "╔══════════════════════╗\n"
            "   💎 <b>AUTO BET TX MD5</b> 💎\n"
            "╚══════════════════════╝\n\n"
            "💸 <b>BƯỚC 3/4 — VỐN GỐC</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "👉 Nhập <b>vốn gốc/phiên</b>\n"
            "💡 VD: <code>20000</code> (Lv 0 = 20k, Lv 1 = 40k...)",
            parse_mode="HTML")
    except: pass


@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == "base_bet",
                     content_types=["text"])
def h_basebet(message):
    if not msg_ok(message): return
    uid = message.from_user.id
    txt = (message.text or "").strip().replace(".", "").replace(",", "").replace("đ", "")
    try: val = int(txt)
    except ValueError:
        try: bot.reply_to(message, "❌ Số tiền không hợp lệ. Nhập lại:")
        except: pass
        return
    if val < 1000:
        try: bot.reply_to(message, "❌ Vốn tối thiểu <b>1.000đ</b>", parse_mode="HTML")
        except: pass
        return
    user_temp[uid]["base_bet"] = val
    user_state[uid] = "target"
    try:
        bot.send_message(message.chat.id,
            "╔══════════════════════╗\n"
            "   💎 <b>AUTO BET TX MD5</b> 💎\n"
            "╚══════════════════════╝\n\n"
            "🎯 <b>BƯỚC 4/4 — MỤC TIÊU LÃI</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "👉 Nhập <b>số tiền muốn chạm tới</b>\n"
            f"💎 Vốn gốc: <b>{_fmt(val)}</b>\n"
            f"🔁 Martingale: Lv 0 → 6 (× 1 → × 64)",
            parse_mode="HTML")
    except: pass


@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == "target",
                     content_types=["text"])
def h_target(message):
    if not msg_ok(message): return
    uid = message.from_user.id
    txt = (message.text or "").strip().replace(".", "").replace(",", "").replace("đ", "")
    try: val = int(txt)
    except ValueError:
        try: bot.reply_to(message, "❌ Số tiền không hợp lệ. Nhập lại:")
        except: pass
        return
    if val < 10000:
        try: bot.reply_to(message, "❌ Mục tiêu tối thiểu <b>10.000đ</b>", parse_mode="HTML")
        except: pass
        return

    temp = user_temp.get(uid, {})
    temp["target"] = val
    user_state.pop(uid, None)
    username = temp.get("username")
    password = temp.get("password")
    if not username or not password:
        user_temp.pop(uid, None)
        try: bot.send_message(message.chat.id, "❌ Dữ liệu lỗi. Bấm /start")
        except: pass
        return

    try:
        status_msg = bot.send_message(message.chat.id,
            "🔄 <b>ĐANG ĐĂNG NHẬP...</b>", parse_mode="HTML")
    except:
        user_temp.pop(uid, None); return

    res = lc_login(username, password)
    if "_error" in res:
        temp.pop("password", None); user_temp.pop(uid, None)
        try:
            bot.edit_message_text(
                "❌ <b>ĐĂNG NHẬP THẤT BẠI</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"<code>{res['_error']}</code>",
                chat_id=message.chat.id, message_id=status_msg.message_id,
                parse_mode="HTML", reply_markup=kb_home())
        except: pass
        return

    temp["pw_md5"] = _md5(password)
    temp.pop("password", None)
    temp.update({"token": res["token"], "nickname": res["nickname"], "money": res["money"]})

    try:
        bot.edit_message_text(
            "╔══════════════════════╗\n"
            "   ✅ <b>ĐĂNG NHẬP OK</b>\n"
            "╚══════════════════════╝\n"
            f"👤 <b>{res['nickname']}</b>\n"
            f"💰 Số dư: <b>{_fmt(res['money'])}</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💸 Vốn: <b>{_fmt(temp['base_bet'])}</b>\n"
            f"🎯 Mục tiêu: <b>+{_fmt(temp['target'])}</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🛡 <b>Anti-Burn Shield</b> sẽ bảo vệ bạn\n"
            "🚀 <i>Khởi động TX MD5...</i>",
            chat_id=message.chat.id, message_id=status_msg.message_id,
            parse_mode="HTML")
    except: pass

    threading.Thread(target=start_auto_bet, args=(uid, temp), daemon=True).start()


@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback(message):
    if not msg_ok(message): return
    uid = message.from_user.id
    if uid in active_states:
        try:
            bot.send_message(message.chat.id,
                "💎 <b>ĐANG AUTO BET</b>\nBấm nút để dừng.",
                parse_mode="HTML", reply_markup=kb_running())
        except: pass
        return
    cmd_start(message)


# ==================== MAIN ====================
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("👑 NESUX ROYAL BOT v9 — ONLINE 2026")
    logger.info(f"🔌 Transport: {logger_init_ws}")
    logger.info("🛡 Anti-Burn · Anti-Spam · Deep AI")
    logger.info("🔐 @DENIUS09 & @deptrainhatvn")
    logger.info("=" * 60)
    if not HAS_WEBSOCKET:
        logger.warning("⚠️  Cài WebSocket: pip install websocket-client")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=15)
        except Exception as e:
            logger.error(f"[POLL] {e}")
            time.sleep(10)
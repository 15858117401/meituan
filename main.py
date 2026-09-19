import re
import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator


app = FastAPI(title="技换 SkillSwap")


class MatchRequest(BaseModel):
    teach: str = Field(min_length=1, max_length=24)
    learn: str = Field(min_length=1, max_length=24)

    @field_validator("teach", "learn")
    @classmethod
    def clean_skill(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("技能不能为空")
        return cleaned


class ExchangeCreate(BaseModel):
    match_id: str = Field(min_length=1, max_length=32)
    teach: str = Field(min_length=1, max_length=24)
    learn: str = Field(min_length=1, max_length=24)


SKILL_ALIASES = {
    "python入门": "python",
    "python编程": "python",
    "编程": "python",
    "民谣吉他": "吉他",
    "弹吉他": "吉他",
    "短视频剪辑": "视频剪辑",
    "剪映": "视频剪辑",
    "剪辑": "视频剪辑",
    "人像摄影": "摄影",
    "拍照": "摄影",
    "英语口语": "英语",
    "口语": "英语",
    "健身训练": "健身",
    "力量训练": "健身",
}


PROFILES = (
    {
        "id": "u-lin",
        "name": "林知夏",
        "initial": "林",
        "city": "上海 · 3.2km",
        "teaches": ("民谣吉他", "摄影"),
        "wants": ("Python", "数据分析"),
        "time": "周三晚 / 周末下午",
        "color": "#dfff45",
        "reliability": 0.96,
    },
    {
        "id": "u-chen",
        "name": "陈一帆",
        "initial": "陈",
        "city": "线上交换",
        "teaches": ("吉他", "视频剪辑"),
        "wants": ("Python", "摄影"),
        "time": "工作日晚 20:00 后",
        "color": "#6ee7cf",
        "reliability": 0.92,
    },
    {
        "id": "u-zhou",
        "name": "周可然",
        "initial": "周",
        "city": "同城 · 5.8km",
        "teaches": ("吉他", "健身"),
        "wants": ("Python", "英语口语"),
        "time": "周六、周日上午",
        "color": "#ffb86b",
        "reliability": 0.89,
    },
    {
        "id": "u-shao",
        "name": "邵雨辰",
        "initial": "邵",
        "city": "线上交换",
        "teaches": ("视频剪辑", "健身"),
        "wants": ("摄影", "英语口语"),
        "time": "周二、周四晚",
        "color": "#b7a3ff",
        "reliability": 0.91,
    },
    {
        "id": "u-qin",
        "name": "秦悦",
        "initial": "秦",
        "city": "同城 · 7.1km",
        "teaches": ("视频剪辑", "吉他"),
        "wants": ("摄影", "Python"),
        "time": "周末全天",
        "color": "#ff93b3",
        "reliability": 0.87,
    },
    {
        "id": "u-gu",
        "name": "顾闻",
        "initial": "顾",
        "city": "线上交换",
        "teaches": ("健身", "视频剪辑"),
        "wants": ("英语口语", "Python"),
        "time": "工作日午休 / 周日",
        "color": "#91bfff",
        "reliability": 0.86,
    },
)


def canonical_skill(value: str) -> str:
    compact = re.sub(r"[\s\-_，,。.!！?？]+", "", value).lower()
    if compact in SKILL_ALIASES:
        return SKILL_ALIASES[compact]
    for alias, canonical in SKILL_ALIASES.items():
        if alias in compact or compact in alias:
            return canonical
    return compact


def skill_similarity(first: str, second: str) -> float:
    left, right = canonical_skill(first), canonical_skill(second)
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.88
    ratio = SequenceMatcher(None, left, right).ratio()
    return ratio if ratio >= 0.5 else 0.0


def best_skill(target: str, options: tuple[str, ...]) -> tuple[str, float]:
    ranked = [(option, skill_similarity(target, option)) for option in options]
    return max(ranked, key=lambda item: item[1])


def rank_matches(teach: str, learn: str, limit: int = 3) -> list[dict[str, object]]:
    ranked: list[dict[str, object]] = []
    for profile in PROFILES:
        offered_skill, offer_score = best_skill(learn, profile["teaches"])
        wanted_skill, want_score = best_skill(teach, profile["wants"])
        reciprocal_score = round(
            100 * (0.52 * offer_score + 0.40 * want_score + 0.08 * profile["reliability"])
        )
        if reciprocal_score < 45:
            continue
        ranked.append(
            {
                "id": profile["id"],
                "name": profile["name"],
                "initial": profile["initial"],
                "city": profile["city"],
                "score": min(reciprocal_score, 99),
                "time": profile["time"],
                "color": profile["color"],
                "teaches": offered_skill,
                "wants": wanted_skill,
                "is_reciprocal": offer_score >= 0.8 and want_score >= 0.8,
            }
        )
    ranked.sort(key=lambda item: (item["is_reciprocal"], item["score"]), reverse=True)
    return ranked[:limit]


@app.post("/api/matches")
async def match_skills(request: MatchRequest) -> dict[str, object]:
    if canonical_skill(request.teach) == canonical_skill(request.learn):
        raise HTTPException(status_code=422, detail="请填写两个不同的技能")
    matches = rank_matches(request.teach, request.learn)
    return {
        "query": {"teach": request.teach, "learn": request.learn},
        "count": len(matches),
        "matches": matches,
        "strategy": "reciprocal_skill_match_v1",
    }


@app.post("/api/exchanges", status_code=201)
async def create_exchange(request: ExchangeCreate) -> dict[str, str]:
    profile = next((item for item in PROFILES if item["id"] == request.match_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="匹配用户不存在")
    if canonical_skill(request.teach) == canonical_skill(request.learn):
        raise HTTPException(status_code=422, detail="交换技能不能相同")
    return {
        "request_id": f"SWAP-{uuid.uuid4().hex[:8].upper()}",
        "status": "pending",
        "partner_name": str(profile["name"]),
        "created_at": datetime.now(UTC).isoformat(),
    }


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="技换是一个用擅长技能交换想学技能的轻量互助平台。">
  <meta name="theme-color" content="#101310">
  <title>技换 SkillSwap｜用你会的，交换你想学的</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23dfff45'/%3E%3Cpath d='M18 23h25l-6-6m9 24H21l6 6' fill='none' stroke='%23101310' stroke-width='6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
  <style>
    :root {
      color-scheme: dark;
      --ink: #f4f7ef;
      --muted: #a8b0a4;
      --bg: #101310;
      --panel: #171b17;
      --panel-2: #1d221d;
      --line: #303730;
      --accent: #dfff45;
      --accent-ink: #151810;
      --cyan: #6ee7cf;
      --danger: #ff8a7a;
      --shadow: 0 28px 90px rgba(0, 0, 0, .34);
    }

    * { box-sizing: border-box; }

    html { scroll-behavior: smooth; }

    body {
      margin: 0;
      min-width: 320px;
      min-height: 100vh;
      background:
        radial-gradient(circle at 8% 8%, rgba(223, 255, 69, .09), transparent 24rem),
        radial-gradient(circle at 92% 38%, rgba(110, 231, 207, .07), transparent 28rem),
        var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      font-size: 16px;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }

    button, input { font: inherit; }
    button { cursor: pointer; }
    a { color: inherit; }

    .shell {
      width: min(1160px, calc(100% - 40px));
      margin: 0 auto;
    }

    .topbar {
      height: 76px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .brand {
      display: inline-flex;
      align-items: center;
      gap: 11px;
      font-weight: 800;
      letter-spacing: -.02em;
      text-decoration: none;
    }

    .brand-mark {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border-radius: 10px;
      color: var(--accent-ink);
      background: var(--accent);
      box-shadow: 0 0 0 5px rgba(223, 255, 69, .08);
    }

    .brand-mark svg { width: 21px; height: 21px; }

    .brand small {
      color: var(--muted);
      font-size: .76rem;
      font-weight: 600;
      letter-spacing: .08em;
      text-transform: uppercase;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 9px;
      color: var(--muted);
      font-size: .88rem;
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--cyan);
      box-shadow: 0 0 0 5px rgba(110, 231, 207, .1);
    }

    main { padding: 64px 0 70px; }

    .hero {
      display: grid;
      grid-template-columns: minmax(0, .9fr) minmax(430px, 1.1fr);
      align-items: center;
      gap: clamp(50px, 8vw, 112px);
    }

    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      margin: 0 0 19px;
      color: var(--accent);
      font-size: .84rem;
      font-weight: 760;
      letter-spacing: .12em;
      text-transform: uppercase;
    }

    .eyebrow::before {
      content: "";
      width: 30px;
      height: 1px;
      background: var(--accent);
    }

    h1 {
      max-width: 590px;
      margin: 0;
      font-size: clamp(3.2rem, 7vw, 6.6rem);
      line-height: .94;
      letter-spacing: -.075em;
    }

    h1 span {
      display: block;
      color: transparent;
      -webkit-text-stroke: 1.5px rgba(244, 247, 239, .7);
    }

    .lede {
      max-width: 490px;
      margin: 27px 0 0;
      color: var(--muted);
      font-size: clamp(1rem, 2vw, 1.16rem);
    }

    .loop-note {
      display: flex;
      align-items: center;
      gap: 13px;
      margin-top: 30px;
      color: #cdd3c8;
      font-size: .9rem;
    }

    .loop-note svg {
      width: 38px;
      height: 38px;
      padding: 9px;
      border: 1px solid var(--line);
      border-radius: 50%;
      color: var(--cyan);
    }

    .matcher {
      position: relative;
      padding: clamp(24px, 4vw, 38px);
      border: 1px solid var(--line);
      border-radius: 28px;
      background: linear-gradient(145deg, rgba(30, 35, 30, .98), rgba(20, 24, 20, .98));
      box-shadow: var(--shadow);
      isolation: isolate;
    }

    .matcher::before {
      content: "";
      position: absolute;
      inset: -1px -1px auto auto;
      width: 118px;
      height: 118px;
      border-radius: 0 28px 0 100%;
      background: repeating-linear-gradient(135deg, rgba(223,255,69,.14) 0 1px, transparent 1px 9px);
      z-index: -1;
    }

    .step {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 28px;
    }

    .step h2 {
      margin: 0;
      font-size: clamp(1.35rem, 3vw, 1.75rem);
      letter-spacing: -.04em;
    }

    .step-number {
      color: var(--muted);
      font-size: .84rem;
      letter-spacing: .1em;
    }

    .field + .field { margin-top: 22px; }
    label { display: block; margin-bottom: 9px; color: #dfe5db; font-size: .93rem; font-weight: 700; }
    .input-wrap { position: relative; }

    input {
      width: 100%;
      height: 60px;
      padding: 0 55px 0 17px;
      border: 1px solid #3a423a;
      border-radius: 15px;
      outline: none;
      color: var(--ink);
      background: #121612;
      transition: border-color .2s, box-shadow .2s, transform .2s;
    }

    input::placeholder { color: #697168; }
    input:hover { border-color: #535d52; }
    input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px rgba(223, 255, 69, .1); }

    .input-icon {
      position: absolute;
      top: 50%;
      right: 17px;
      width: 26px;
      height: 26px;
      display: grid;
      place-items: center;
      transform: translateY(-50%);
      border-radius: 8px;
      color: var(--cyan);
      background: rgba(110, 231, 207, .08);
      pointer-events: none;
    }

    .input-icon svg { width: 15px; height: 15px; }

    .quick-picks { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 13px; }
    .quick-label { margin-right: 2px; color: #778077; font-size: .8rem; }

    .chip {
      padding: 6px 10px;
      border: 1px solid #343b34;
      border-radius: 999px;
      color: #aeb6ab;
      background: transparent;
      font-size: .8rem;
      transition: color .18s, border-color .18s, background .18s;
    }

    .chip:hover, .chip:focus-visible { border-color: #677164; color: var(--ink); background: rgba(255, 255, 255, .04); outline: none; }
    .swap-divider { position: relative; height: 20px; margin: 8px 0; }
    .swap-divider::before { content: ""; position: absolute; top: 50%; right: 0; left: 0; height: 1px; background: var(--line); }

    .swap-symbol {
      position: absolute;
      top: 50%;
      left: 50%;
      width: 36px;
      height: 36px;
      display: grid;
      place-items: center;
      transform: translate(-50%, -50%) rotate(90deg);
      border: 1px solid var(--line);
      border-radius: 50%;
      color: var(--accent);
      background: var(--panel);
    }

    .swap-symbol svg { width: 17px; height: 17px; }
    .form-error { min-height: 24px; margin: 14px 0 0; color: var(--danger); font-size: .84rem; }

    .primary-button {
      width: 100%;
      min-height: 58px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      border: 0;
      border-radius: 15px;
      color: var(--accent-ink);
      background: var(--accent);
      font-weight: 820;
      box-shadow: 0 12px 28px rgba(223, 255, 69, .12);
      transition: transform .2s, box-shadow .2s, filter .2s;
    }

    .primary-button:hover { transform: translateY(-2px); box-shadow: 0 16px 34px rgba(223, 255, 69, .18); filter: brightness(1.04); }
    .primary-button:active { transform: translateY(0); }

    .primary-button:focus-visible, .exchange-button:focus-visible, .close-button:focus-visible {
      outline: 3px solid rgba(110, 231, 207, .6);
      outline-offset: 3px;
    }

    .primary-button svg { width: 18px; height: 18px; }
    .primary-button[aria-busy="true"] svg { animation: spin .7s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .privacy-note { margin: 13px 0 0; text-align: center; color: #727a71; font-size: .78rem; }

    .results { display: none; padding: 96px 0 18px; scroll-margin-top: 24px; }
    .results.visible { display: block; animation: rise .5s ease both; }
    @keyframes rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }

    .results-head { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
    .results h2 { margin: 0; font-size: clamp(1.8rem, 4vw, 2.8rem); letter-spacing: -.055em; }
    .results-copy { margin: 6px 0 0; color: var(--muted); }
    .result-count { flex: 0 0 auto; color: var(--accent); font-size: .9rem; font-weight: 700; }
    .cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }

    .empty-state {
      grid-column: 1 / -1;
      padding: 38px 24px;
      border: 1px dashed #465044;
      border-radius: 20px;
      color: var(--muted);
      background: rgba(255, 255, 255, .02);
      text-align: center;
    }

    .card {
      min-width: 0;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: var(--panel);
      transition: transform .2s, border-color .2s, background .2s;
    }

    .card:hover { transform: translateY(-4px); border-color: #4c574a; background: var(--panel-2); }
    .card-top { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
    .person { display: flex; align-items: center; min-width: 0; gap: 12px; }

    .avatar {
      width: 46px;
      height: 46px;
      flex: 0 0 auto;
      display: grid;
      place-items: center;
      border-radius: 14px;
      color: var(--accent-ink);
      background: var(--avatar, var(--cyan));
      font-weight: 850;
    }

    .person-name { overflow: hidden; margin: 0; font-size: 1rem; font-weight: 760; text-overflow: ellipsis; white-space: nowrap; }
    .person-meta { margin: 1px 0 0; color: var(--muted); font-size: .8rem; }
    .score { flex: 0 0 auto; color: var(--accent); font-size: 1.45rem; font-weight: 850; letter-spacing: -.04em; }
    .score small { margin-left: 2px; color: var(--muted); font-size: .68rem; font-weight: 600; }

    .trade { margin: 24px 0 20px; padding: 17px; border: 1px solid #303730; border-radius: 15px; background: #121612; }
    .trade-row { display: grid; grid-template-columns: 47px 1fr; align-items: center; gap: 10px; }
    .trade-row + .trade-row { margin-top: 12px; }
    .trade-key { color: #7e887d; font-size: .75rem; }
    .trade-value { min-width: 0; overflow: hidden; color: #e7ece3; font-size: .9rem; font-weight: 680; text-overflow: ellipsis; white-space: nowrap; }
    .trade-value.learn { color: var(--cyan); }

    .availability { display: flex; align-items: center; gap: 8px; margin-bottom: 18px; color: var(--muted); font-size: .82rem; }
    .availability svg { width: 15px; height: 15px; color: #889186; }

    .exchange-button {
      width: 100%;
      min-height: 44px;
      border: 1px solid #4b5549;
      border-radius: 12px;
      color: var(--ink);
      background: transparent;
      font-weight: 720;
      transition: color .18s, background .18s, border-color .18s;
    }

    .exchange-button:hover { border-color: var(--accent); color: var(--accent-ink); background: var(--accent); }
    .footer { padding: 30px 0 38px; color: #737c72; font-size: .82rem; text-align: center; }

    dialog {
      width: min(440px, calc(100% - 32px));
      padding: 0;
      border: 1px solid #414a40;
      border-radius: 24px;
      color: var(--ink);
      background: #1b201b;
      box-shadow: var(--shadow);
    }

    dialog::backdrop { background: rgba(3, 5, 3, .74); backdrop-filter: blur(5px); }
    .dialog-body { padding: 34px; text-align: center; }

    .success-icon {
      width: 58px;
      height: 58px;
      display: grid;
      place-items: center;
      margin: 0 auto 20px;
      border-radius: 18px;
      color: var(--accent-ink);
      background: var(--accent);
    }

    .success-icon svg { width: 28px; height: 28px; }
    .dialog-body h2 { margin: 0; font-size: 1.55rem; letter-spacing: -.035em; }
    .dialog-body p { margin: 12px 0 24px; color: var(--muted); }
    .close-button { min-width: 132px; min-height: 44px; border: 0; border-radius: 12px; color: var(--accent-ink); background: var(--accent); font-weight: 760; }

    .toast {
      position: fixed;
      right: 22px;
      bottom: 22px;
      z-index: 20;
      max-width: min(360px, calc(100% - 44px));
      padding: 13px 17px;
      border: 1px solid #465044;
      border-radius: 13px;
      color: var(--ink);
      background: #202620;
      box-shadow: 0 16px 40px rgba(0,0,0,.34);
      opacity: 0;
      transform: translateY(14px);
      pointer-events: none;
      transition: opacity .22s, transform .22s;
    }

    .toast.show { opacity: 1; transform: translateY(0); }

    @media (max-width: 900px) {
      main { padding-top: 34px; }
      .hero { grid-template-columns: 1fr; gap: 46px; }
      .hero-copy { text-align: center; }
      .eyebrow { justify-content: center; }
      h1, .lede { margin-right: auto; margin-left: auto; }
      .loop-note { justify-content: center; }
      .matcher { width: min(600px, 100%); margin: 0 auto; }
      .cards { grid-template-columns: 1fr; }
      .card { display: grid; grid-template-columns: 1fr auto; column-gap: 24px; }
      .card-top, .trade { grid-column: 1 / -1; }
      .availability { margin: 0; }
      .exchange-button { width: 150px; }
    }

    @media (max-width: 600px) {
      .shell { width: min(100% - 24px, 1160px); }
      .topbar { height: 64px; }
      .brand small, .status span { display: none; }
      main { padding-top: 28px; }
      h1 { font-size: clamp(3.15rem, 18vw, 5rem); }
      .lede { margin-top: 22px; }
      .loop-note { align-items: flex-start; text-align: left; }
      .matcher { padding: 22px 17px; border-radius: 22px; }
      .step { margin-bottom: 22px; }
      input { height: 56px; }
      .primary-button { min-height: 55px; }
      .results { padding-top: 70px; }
      .results-head { align-items: flex-start; flex-direction: column; gap: 8px; }
      .card { display: block; padding: 20px; }
      .availability { margin-bottom: 18px; }
      .exchange-button { width: 100%; }
      .dialog-body { padding: 28px 22px; }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        scroll-behavior: auto !important;
        animation-duration: .01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: .01ms !important;
      }
    }
  </style>
</head>
<body>
  <header class="shell topbar">
    <a class="brand" href="#top" aria-label="技换首页">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none"><path d="M4 8h15m0 0-4-4m4 4-4 4M20 16H5m0 0 4 4m-4-4 4-4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </span>
      <span>技换 <small>SkillSwap</small></span>
    </a>
    <div class="status" aria-label="平台状态正常">
      <i class="status-dot" aria-hidden="true"></i>
      <span>即时匹配开放中</span>
    </div>
  </header>

  <main id="top" class="shell">
    <section class="hero" aria-labelledby="page-title">
      <div class="hero-copy">
        <p class="eyebrow">技能不该闲置</p>
        <h1 id="page-title">用你会的<span>交换想学的</span></h1>
        <p class="lede">不报班，也不单打独斗。找到恰好需要你、也恰好能帮你的人，用一小时交换一小时。</p>
        <div class="loop-note">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M20 7h-9a4 4 0 0 0-4 4v0m-3 6h9a4 4 0 0 0 4-4v0M17 4l3 3-3 3M7 14l-3 3 3 3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span>双方技能互补，时间合适，即可开始交换。</span>
        </div>
      </div>

      <form class="matcher" id="match-form" novalidate>
        <div class="step">
          <h2>找到你的技能搭子</h2>
          <span class="step-number">01 / MATCH</span>
        </div>

        <div class="field">
          <label for="teach-skill">我能教</label>
          <div class="input-wrap">
            <input id="teach-skill" name="teach" type="text" maxlength="24" autocomplete="off" placeholder="例如：Python 入门" aria-describedby="form-error">
            <span class="input-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M12 3 2.5 8 12 13l9.5-5L12 3Z M6 10v5.5c2.8 2.6 9.2 2.6 12 0V10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          </div>
          <div class="quick-picks" aria-label="可快速选择擅长技能">
            <span class="quick-label">快速选择</span>
            <button class="chip" type="button" data-target="teach-skill">Python</button>
            <button class="chip" type="button" data-target="teach-skill">摄影</button>
            <button class="chip" type="button" data-target="teach-skill">英语口语</button>
          </div>
        </div>

        <div class="swap-divider" aria-hidden="true">
          <span class="swap-symbol"><svg viewBox="0 0 24 24" fill="none"><path d="M4 8h15m0 0-4-4m4 4-4 4M20 16H5m0 0 4 4m-4-4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
        </div>

        <div class="field">
          <label for="learn-skill">我想学</label>
          <div class="input-wrap">
            <input id="learn-skill" name="learn" type="text" maxlength="24" autocomplete="off" placeholder="例如：民谣吉他" aria-describedby="form-error">
            <span class="input-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4L16.5 3.5Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          </div>
          <div class="quick-picks" aria-label="可快速选择想学技能">
            <span class="quick-label">热门技能</span>
            <button class="chip" type="button" data-target="learn-skill">吉他</button>
            <button class="chip" type="button" data-target="learn-skill">视频剪辑</button>
            <button class="chip" type="button" data-target="learn-skill">健身</button>
          </div>
        </div>

        <p class="form-error" id="form-error" role="alert" aria-live="polite"></p>
        <button class="primary-button" id="match-button" type="submit">
          <span>智能匹配</span>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M5 12h14m-5-5 5 5-5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <p class="privacy-note">雏形体验，无需注册，不保存输入内容</p>
      </form>
    </section>

    <section class="results" id="results" aria-labelledby="results-title" aria-live="polite">
      <div class="results-head">
        <div>
          <h2 id="results-title">为你找到这些交换者</h2>
          <p class="results-copy" id="results-copy">根据技能互补度与可约时间排序</p>
        </div>
        <span class="result-count" id="result-count">3 个高匹配结果</span>
      </div>
      <div class="cards" id="cards"></div>
    </section>
  </main>

  <footer class="shell footer">技能有价，互助无界 · 技换 SkillSwap</footer>

  <dialog id="success-dialog" aria-labelledby="dialog-title">
    <div class="dialog-body">
      <div class="success-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="m5 12 4 4L19 6" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      <h2 id="dialog-title">交换邀请已发出</h2>
      <p id="dialog-copy">对方确认后，你们就可以约定第一次技能交换。</p>
      <button class="close-button" id="close-dialog" type="button">知道了</button>
    </div>
  </dialog>
  <div class="toast" id="toast" role="status" aria-live="polite">已为你生成匹配结果</div>

  <script>
    const form = document.querySelector('#match-form');
    const teachInput = document.querySelector('#teach-skill');
    const learnInput = document.querySelector('#learn-skill');
    const errorBox = document.querySelector('#form-error');
    const matchButton = document.querySelector('#match-button');
    const results = document.querySelector('#results');
    const resultsCopy = document.querySelector('#results-copy');
    const resultCount = document.querySelector('#result-count');
    const cards = document.querySelector('#cards');
    const dialog = document.querySelector('#success-dialog');
    const dialogCopy = document.querySelector('#dialog-copy');
    const toast = document.querySelector('#toast');

    document.querySelectorAll('.chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const input = document.getElementById(chip.dataset.target);
        input.value = chip.textContent.trim();
        input.focus();
        errorBox.textContent = '';
      });
    });

    function makeText(tag, className, value) {
      const element = document.createElement(tag);
      element.className = className;
      element.textContent = value;
      return element;
    }

    function createCard(person, teach, learn) {
      const card = document.createElement('article');
      card.className = 'card';
      const top = document.createElement('div');
      top.className = 'card-top';
      const personWrap = document.createElement('div');
      personWrap.className = 'person';
      const avatar = makeText('span', 'avatar', person.initial);
      avatar.style.setProperty('--avatar', person.color);
      const details = document.createElement('div');
      details.append(makeText('p', 'person-name', person.name), makeText('p', 'person-meta', person.city));
      personWrap.append(avatar, details);
      const score = makeText('div', 'score', String(person.score));
      score.append(makeText('small', '', '% 匹配'));
      top.append(personWrap, score);

      const trade = document.createElement('div');
      trade.className = 'trade';
      const teaching = document.createElement('div');
      teaching.className = 'trade-row';
      teaching.append(makeText('span', 'trade-key', 'TA 能教'), makeText('span', 'trade-value', person.teaches));
      const learning = document.createElement('div');
      learning.className = 'trade-row';
      learning.append(makeText('span', 'trade-key', 'TA 想学'), makeText('span', 'trade-value learn', person.wants));
      trade.append(teaching, learning);

      const availability = document.createElement('div');
      availability.className = 'availability';
      availability.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.7"/><path d="M12 7v5l3 2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      availability.append(makeText('span', '', person.time));

      const button = makeText('button', 'exchange-button', '发起交换');
      button.type = 'button';
      button.addEventListener('click', async () => {
        button.disabled = true;
        button.textContent = '发送中…';
        try {
          const response = await fetch('/api/exchanges', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ match_id: person.id, teach, learn })
          });
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.detail || '邀请发送失败，请稍后重试');
          dialogCopy.textContent = `已向 ${payload.partner_name} 发出「${teach} ⇄ ${learn}」交换邀请，编号 ${payload.request_id}。`;
          if (typeof dialog.showModal === 'function') dialog.showModal();
          else window.alert(dialogCopy.textContent);
        } catch (error) {
          showToast(error.message || '邀请发送失败，请稍后重试');
        } finally {
          button.disabled = false;
          button.textContent = '发起交换';
        }
      });

      card.append(top, trade, availability, button);
      return card;
    }

    function showToast(message) {
      toast.textContent = message;
      toast.classList.add('show');
      window.setTimeout(() => toast.classList.remove('show'), 2400);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const teach = teachInput.value.trim();
      const learn = learnInput.value.trim();

      if (!teach || !learn) {
        errorBox.textContent = '请先填写你能教和想学的技能。';
        (!teach ? teachInput : learnInput).focus();
        return;
      }

      if (teach.toLowerCase() === learn.toLowerCase()) {
        errorBox.textContent = '两个技能换着学会更有意思，试试填写不同技能。';
        learnInput.focus();
        return;
      }

      errorBox.textContent = '';
      matchButton.setAttribute('aria-busy', 'true');
      matchButton.disabled = true;
      matchButton.querySelector('span').textContent = '正在匹配';

      try {
        const response = await fetch('/api/matches', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ teach, learn })
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || '匹配服务暂时不可用');

        if (payload.matches.length) {
          cards.replaceChildren(...payload.matches.map((person) => createCard(person, teach, learn)));
        } else {
          cards.replaceChildren(makeText('div', 'empty-state', '暂时没有合适的互换伙伴，换一个更具体的技能试试。'));
        }
        resultsCopy.textContent = `正在寻找能教「${learn}」、想学「${teach}」的人`;
        resultCount.textContent = payload.count ? `${payload.count} 个匹配结果` : '等待新的技能组合';
        results.classList.add('visible');
        showToast(payload.count ? `已找到 ${payload.count} 位匹配交换者` : '这组技能暂时没有匹配');
        results.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (error) {
        errorBox.textContent = error.message || '匹配服务暂时不可用，请稍后重试。';
      } finally {
        matchButton.removeAttribute('aria-busy');
        matchButton.disabled = false;
        matchButton.querySelector('span').textContent = results.classList.contains('visible') ? '重新匹配' : '智能匹配';
      }
    });

    document.querySelector('#close-dialog').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
      const rect = dialog.getBoundingClientRect();
      const outside = event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
      if (outside) dialog.close();
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return PAGE

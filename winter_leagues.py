"""
Winter Leagues Auto-Verification Script
Verifies Brazil Serie A and Japan J1 API-Football IDs using auto-lookup
"""

import os
import json
import time
import hashlib
import requests
from typing import Optional, Tuple
from league_config import LEAGUE_REGISTRY, add_league, LeagueConfig

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

CACHE_DIR = "pgr_cache"
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(name):
    return os.path.join(CACHE_DIR, name)


def _load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _http_get(url, params=None, ttl_minutes=1440):
    """GET with file cache (default 24h)"""
    if params is None:
        params = {}
    key_raw = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    key = hashlib.md5(key_raw.encode()).hexdigest()
    path = _cache_path(f"http_{key}.json")

    # Cache hit?
    cached = _load_json(path)
    if cached and (time.time() - cached.get("_ts", 0) < ttl_minutes * 60):
        return cached["data"]

    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    _save_json(path, {"_ts": time.time(), "data": data})
    return data


def af_resolve_league_id(country_hint: str, name_hint: str, prefer_tier: Optional[int] = None) -> Tuple[Optional[int], Optional[int]]:
    """
    Resolve league_id via /leagues?search= and filter by country/name.
    prefer_tier: Choose top division if available (e.g., tier 1).
    Returns (league_id, season) or (None, None) if not found.
    """
    q = name_hint
    data = _http_get(f"{API_FOOTBALL_BASE}/leagues", params={"search": q}, ttl_minutes=720)
    results = data.get("response", [])
    
    # Basic filtering: country + approximate name
    candidates = []
    for item in results:
        lg = item.get("league", {}) or {}
        cn = item.get("country", {}) or {}
        lname = (lg.get("name") or "").lower()
        ccountry = (cn.get("name") or "").lower()
        
        if country_hint.lower() in ccountry and any(tok in lname for tok in name_hint.lower().split()):
            # Get latest season
            seasons = item.get("seasons", []) or []
            best_season = None
            for s in seasons:
                # Prefer active season if possible
                if s.get("current") is True:
                    best_season = s
                    break
            if not best_season and seasons:
                best_season = seasons[-1]
            
            if best_season:
                candidates.append({
                    "league_id": lg.get("id"),
                    "league_name": lg.get("name"),
                    "tier": (best_season.get("coverage") or {}).get("standings") and 1 or None,
                    "season": best_season.get("year")
                })
    
    if not candidates:
        return None, None

    # Choose candidates with tier=1 if desired
    if prefer_tier == 1:
        tier1 = [c for c in candidates if c["tier"] == 1]
        if tier1:
            candidates = tier1

    # Choose latest season
    candidates.sort(key=lambda x: (x["season"] or 0), reverse=True)
    return candidates[0]["league_id"], candidates[0]["season"]


def verify_winter_leagues():
    """
    Verify Brazil Serie A & Japan J1 League configurations
    Auto-corrects if API IDs or seasons are outdated
    """
    if not API_FOOTBALL_KEY:
        raise SystemExit("❌ Set API_FOOTBALL_KEY in environment variables (Replit Secrets)")
    
    print("\n❄️ WINTER LEAGUES VERIFICATION")
    print("=" * 60)
    
    # Check Brazil Serie A
    brazil_config = None
    for league in LEAGUE_REGISTRY:
        if league.name == "Brazilian Serie A":
            brazil_config = league
            break
    
    if brazil_config:
        print(f"\n🇧🇷 Brazil Serie A:")
        print(f"   Current Config: ID={brazil_config.api_football_id}, Season={brazil_config.season}")
        
        # Verify with API
        br_id, br_season = af_resolve_league_id(country_hint="Brazil", name_hint="Serie A", prefer_tier=1)
        if br_id and br_season:
            if br_id != brazil_config.api_football_id or br_season != brazil_config.season:
                print(f"   ⚠️ Mismatch! API shows: ID={br_id}, Season={br_season}")
                print(f"   🔄 Auto-updating configuration...")
                
                brazil_config.api_football_id = br_id
                brazil_config.season = br_season
                print(f"   ✅ Updated: ID={br_id}, Season={br_season}")
            else:
                print(f"   ✅ Verified: Configuration matches API")
        else:
            print(f"   ⚠️ Could not verify via API (using cached config)")
    else:
        print(f"\n❌ Brazil Serie A not found in registry!")
    
    # Check Japan J1 League
    japan_config = None
    for league in LEAGUE_REGISTRY:
        if league.name == "Japanese J1 League":
            japan_config = league
            break
    
    if japan_config:
        print(f"\n🇯🇵 Japan J1 League:")
        print(f"   Current Config: ID={japan_config.api_football_id}, Season={japan_config.season}")
        
        # Verify with API
        jp_id, jp_season = af_resolve_league_id(country_hint="Japan", name_hint="J1 League", prefer_tier=1)
        if not jp_id:
            # Fallback: try "J League" as search string
            jp_id, jp_season = af_resolve_league_id(country_hint="Japan", name_hint="J League", prefer_tier=1)
        
        if jp_id and jp_season:
            if jp_id != japan_config.api_football_id or jp_season != japan_config.season:
                print(f"   ⚠️ Mismatch! API shows: ID={jp_id}, Season={jp_season}")
                print(f"   🔄 Auto-updating configuration...")
                
                japan_config.api_football_id = jp_id
                japan_config.season = jp_season
                print(f"   ✅ Updated: ID={jp_id}, Season={jp_season}")
            else:
                print(f"   ✅ Verified: Configuration matches API")
        else:
            print(f"   ⚠️ Could not verify via API (using cached config)")
    else:
        print(f"\n❌ Japan J1 League not found in registry!")
    
    print("\n" + "=" * 60)
    print("✅ Winter leagues verification complete!")
    print(f"🌍 Total active leagues: {len([l for l in LEAGUE_REGISTRY if l.active])}")
    
    winter_leagues = [l for l in LEAGUE_REGISTRY if l.country in ["Brazil", "Japan", "Argentina", "South Korea", "Australia"]]
    print(f"❄️ Winter leagues configured: {len(winter_leagues)}")
    for league in winter_leagues:
        print(f"   • {league.name} ({league.odds_api_key}) - ID {league.api_football_id}")


if __name__ == "__main__":
    verify_winter_leagues()

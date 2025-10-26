#!/usr/bin/env python3
"""
Post Terms of Service and Legal Documents to Telegram Channel
"""

from telegram_sender import TelegramBroadcaster
from pathlib import Path

def read_legal_doc(filename):
    """Read legal document from file"""
    filepath = Path('legal') / filename
    if filepath.exists():
        return filepath.read_text(encoding='utf-8')
    return None

def create_short_tos_en():
    """Create short Terms of Service for Telegram"""
    return """📜 **TERMS OF SERVICE**

**Exact Score Predictions Service**

🔹 **Service:** Daily exact score predictions (5-10/day)
🔹 **Pricing:** 499 SEK/month (Standard), 999 SEK/month (VIP)
🔹 **Payment:** Monthly, non-refundable

⚠️ **IMPORTANT DISCLAIMERS:**

❌ **NO GUARANTEES** - We make zero guarantees of profit or win rate
📊 **Past performance ≠ Future results** 
💸 **Risk of loss** - You may lose all money staked
🎯 **Information only** - Not financial advice

✅ **YOUR RESPONSIBILITIES:**

• Must be 18+ years old
• Comply with gambling laws in your jurisdiction
• Bet only what you can afford to lose
• Do not share predictions publicly

📋 **FULL TERMS:**
Read complete Terms of Service at: [Link to full document]

**By subscribing, you agree to all terms and acknowledge gambling risks.**

🇸🇪 **Swedish Gambling Support:**
Stödlinjen: 020-819 100
stodlinjen.se

---
Premium Exact Score Predictions
Launching January 2026
"""

def create_short_tos_sv():
    """Create short Terms of Service for Telegram (Swedish)"""
    return """📜 **ANVÄNDARVILLKOR**

**Exact Score Predictions Tjänst**

🔹 **Tjänst:** Dagliga exakta resultatprognoser (5-10/dag)
🔹 **Pris:** 499 SEK/månad (Standard), 999 SEK/månad (VIP)
🔹 **Betalning:** Månadsvis, ej återbetalningsbar

⚠️ **VIKTIGA FRISKRIVNINGAR:**

❌ **INGA GARANTIER** - Vi ger noll garantier för vinst eller träffsäkerhet
📊 **Tidigare resultat ≠ Framtida resultat**
💸 **Risk för förlust** - Du kan förlora alla pengar du satsar
🎯 **Endast information** - Inte finansiell rådgivning

✅ **DITT ANSVAR:**

• Måste vara 18+ år
• Följa spellagar i din jurisdiktion
• Satsa endast vad du har råd att förlora
• Dela inte prognoser offentligt

📋 **FULLSTÄNDIGA VILLKOR:**
Läs fullständiga användarvillkor på: [Länk till fullständigt dokument]

**Genom att prenumerera godkänner du alla villkor och bekräftar spelrisker.**

🇸🇪 **Svenskt spelstöd:**
Stödlinjen: 020-819 100
stodlinjen.se

---
Premium Exact Score Predictions
Lanseras januari 2026
"""

def create_disclaimer_post_en():
    """Create risk disclaimer post"""
    return """⚠️ **RISK DISCLAIMER**

**READ BEFORE SUBSCRIBING**

🎰 **Gambling Involves Risk of Loss**

ALL predictions carry risk. You may lose money.

📊 **What We Provide:**
✅ Statistical analysis & predictions
✅ Real-time performance tracking
✅ Historical data & transparency
✅ Daily exact score tips (5-10/day)

❌ **What We DON'T Guarantee:**
• Future win rates
• Profitability
• ROI targets
• Individual prediction accuracy

💰 **Current Performance:**
We show LIVE stats on every prediction:
• Win rate percentage
• Total profit/loss
• ROI over time

**These are historical only - not future guarantees.**

🎯 **Your Responsibility:**

• You make all betting decisions
• You manage your bankroll
• You comply with local laws
• You accept risk of loss

⚡ **Responsible Gambling:**

✅ Only bet what you can afford to lose
✅ Set limits on your betting
✅ Never chase losses
✅ Seek help if needed

🇸🇪 **Help Available:**
Stödlinjen: 020-819 100

---

**18+ ONLY. GAMBLE RESPONSIBLY.**

By subscribing, you acknowledge all risks and accept full responsibility for your betting decisions.
"""

def create_disclaimer_post_sv():
    """Create risk disclaimer post (Swedish)"""
    return """⚠️ **RISKVARNING**

**LÄS INNAN DU PRENUMERERAR**

🎰 **Spel innebär risk för förlust**

ALLA prognoser innebär risk. Du kan förlora pengar.

📊 **Vad vi tillhandahåller:**
✅ Statistisk analys & prognoser
✅ Realtidsprestandaspårning
✅ Historiska data & transparens
✅ Dagliga exakta resultattips (5-10/dag)

❌ **Vad vi INTE garanterar:**
• Framtida träffsäkerhet
• Lönsamhet
• ROI-mål
• Individuell prognosnoggrannhet

💰 **Nuvarande prestanda:**
Vi visar LIVE-statistik på varje prognos:
• Träffsäkerhet i procent
• Total vinst/förlust
• ROI över tid

**Dessa är endast historiska - inte framtida garantier.**

🎯 **Ditt ansvar:**

• Du fattar alla spelbeslut
• Du hanterar din spelbudget
• Du följer lokala lagar
• Du accepterar risk för förlust

⚡ **Ansvarsfullt spelande:**

✅ Satsa endast vad du har råd att förlora
✅ Sätt gränser för ditt spelande
✅ Jaga aldrig förluster
✅ Sök hjälp om du behöver det

🇸🇪 **Hjälp finns:**
Stödlinjen: 020-819 100
stodlinjen.se

---

**ENDAST 18+. SPELA ANSVARSFULLT.**

Genom att prenumerera bekräftar du alla risker och accepterar fullt ansvar för dina spelbeslut.
"""

def main():
    """Post all legal documents to channel"""
    print("📜 Posting legal documents to Telegram channel...")
    
    broadcaster = TelegramBroadcaster()
    channel_id = broadcaster.get_channel()
    
    if not channel_id:
        print("❌ No channel configured")
        return
    
    # Post English version
    print("\n📤 Posting English Terms of Service...")
    tos_en = create_short_tos_en()
    if broadcaster.send_message(channel_id, tos_en):
        print("✅ English ToS posted")
    
    # Post Swedish version
    print("\n📤 Posting Swedish Användarvillkor...")
    tos_sv = create_short_tos_sv()
    if broadcaster.send_message(channel_id, tos_sv):
        print("✅ Swedish ToS posted")
    
    # Post English disclaimer
    print("\n📤 Posting English Risk Disclaimer...")
    disclaimer_en = create_disclaimer_post_en()
    if broadcaster.send_message(channel_id, disclaimer_en):
        print("✅ English Disclaimer posted")
    
    # Post Swedish disclaimer
    print("\n📤 Posting Swedish Riskvarning...")
    disclaimer_sv = create_disclaimer_post_sv()
    if broadcaster.send_message(channel_id, disclaimer_sv):
        print("✅ Swedish Disclaimer posted")
    
    print("\n✅ All legal documents posted to channel!")
    print(f"📱 Channel ID: {channel_id}")
    print("\n📋 Full legal documents saved in ./legal/ folder:")
    print("   - terms_of_service_en.md")
    print("   - terms_of_service_sv.md")
    print("   - disclaimer_en.md")
    print("   - disclaimer_sv.md")
    print("   - privacy_policy_en.md")
    print("   - privacy_policy_sv.md")

if __name__ == '__main__':
    main()

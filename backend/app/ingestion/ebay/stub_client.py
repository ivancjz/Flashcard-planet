from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from backend.app.ingestion.ebay.models import EbayListing


class StubEbayClient:
    async def fetch_sold_listings(self, category: str, limit: int = 100) -> list[EbayListing]:
        now = datetime.now(UTC).replace(microsecond=0)
        titles = [
            "Pokemon Charizard ex SAR 199/165 SV151 PSA 10 Graded Card NM",
            "WOW! Pikachu Full Art 25th Anniversary JP CGC 9.5 FREE SHIP!!!",
            "Mew ex 205/165 Special Illustration Rare SV151 English Near Mint",
            "Blastoise ex SIR 200/165 Scarlet & Violet 151 BGS 9.5",
            "Venusaur ex 198/165 SV151 Ultra Rare Raw Mint Pokemon Card",
            "Umbreon VMAX TG23/TG30 Brilliant Stars Trainer Gallery PSA 10",
            "Rayquaza VMAX Alt Art 218/203 Evolving Skies CGC 10 Pristine",
            "Gengar VMAX 271/264 Fusion Strike Secret Rare PSA 9",
            "Lugia V Alternate Art 186/195 Silver Tempest SGC 10",
            "Pikachu with Grey Felt Hat SVP085 Sealed Promo English",
            "Charizard Base Set 4/102 Unlimited Holo PSA 8 Pokemon",
            "Espeon VMAX Alt Art 270/264 Fusion Strike NM English",
            "Mewtwo VSTAR GG44/GG70 Crown Zenith Gold Card BGS 10",
            "Giratina V Alt Art 186/196 Lost Origin Raw NM",
            "Pikachu Illustrator Style Fan Art Proxy LOOK READ",
            "Dragonite V 192/203 Alternate Full Art Evolving Skies PSA 10",
            "Sylveon VMAX TG15/TG30 Brilliant Stars Trainer Gallery CGC 9",
            "Arceus VSTAR GG70/GG70 Crown Zenith Gold Secret Rare",
            "Magikarp IR 203/193 Paldea Evolved Japanese PSA 10",
            "Iono SAR 350/190 Shiny Treasure ex JP Mint",
            "Miriam 251/198 Scarlet & Violet Full Art Trainer PSA 10",
            "151 Master Ball Reverse Holo Pikachu Japanese 025/165",
            "Moltres Zapdos Articuno GX 44/68 Hidden Fates Promo Stained Glass",
            "Eevee & Snorlax GX SM169 Promo Tag Team PSA 9",
            "Charizard ex 006/165 Pokemon 151 regular ex lot card",
            "Pokemon Center Promo Yu Nagaba Pikachu 208/S-P Japanese NM",
            "Deoxys VMAX GG45/GG70 Crown Zenith PSA 10 GEM MINT",
            "Mew Gold Star Delta Species 101/101 Celebrations Classic Collection",
            "Cynthia Ambition GG60/GG70 Crown Zenith Full Art Trainer",
            "Ancient Mew 1999 Nintendo Promo Movie Card SEALED",
        ]
        listings: list[EbayListing] = []
        for index, title in enumerate(titles[:limit], start=1):
            listings.append(
                EbayListing(
                    source_listing_id=f"stub-ebay-{index:04d}",
                    raw_title=title,
                    price_usd=Decimal("10.00") + Decimal(index * 7),
                    sold_at=now - timedelta(minutes=index * 17),
                    currency_original="USD",
                    url=f"https://www.ebay.com/itm/stub-ebay-{index:04d}",
                )
            )
        return listings

"""Legal copy — inline fallback when LEGAL_*_URL not configured."""
from __future__ import annotations

TERMS_PL = """
### Regulamin (skrót)

Market Intel to narzędzie analityczne do badań nisz App Store. Nie stanowi porady
inwestycyjnej ani gwarancji sukcesu aplikacji.

- Kredyty odblokowują **konkretną niszę na stałe** (Analiza kategorii lub mikro-nisza).
- Plan Pro obejmuje subskrypcję miesięczną + kredyty wg opisu produktu.
- Zabronione jest udostępnianie konta wielu osobom i automatyczne scrapowanie panelu.

Pełny regulamin może być hostowany pod osobnym URL (ustaw `LEGAL_TERMS_URL`).
"""

PRIVACY_PL = """
### Polityka prywatności (skrót)

Przetwarzamy: adres e-mail (Supabase Auth), historię odblokowań i saldo kredytów
(w bazie aplikacji), dane płatności (Lemon Squeezy — my nie przechowujemy numerów kart).

Cel: świadczenie usługi, rozliczenia, wsparcie. Możesz poprosić o usunięcie konta
mailowo na adres wsparcia.

Pełna polityka może być hostowana pod `LEGAL_PRIVACY_URL`.
"""

REFUND_PL = """
### Zwroty

- **Kredyt zużyty** (odblokowana nisza) — zwrot co do zasady niedostępny (treść
  cyfrowa dostarczona natychmiast).
- **Nieużyty kredyt** — kontakt ze wsparciem w ciągu 14 dni; rozpatrujemy indywidualnie.
- **Subskrypcja Pro** — anuluj w portalu klienta Lemon Squeezy; dostęp do końca okresu.

Kontakt: zobacz `SUPPORT_EMAIL` w konfiguracji aplikacji.
"""

SUPPORT_PLAYBOOK_PL = """
### Płatność przeszła, brak kredytów?

1. Poczekaj **do 2 minut** i kliknij **Odśwież saldo** w panelu bocznym.
2. Upewnij się, że płatność była **po zalogowaniu** (checkout musi znać Twoje konto).
3. W Lemon Squeezy → Webhooks sprawdź, czy event `order_created` ma status **200**.
4. Jeśli webhook failed — skontaktuj się z nami podając e-mail konta i datę płatności.
   Support może ręcznie dodać kredyty (`python run.py grant-credits`).
"""

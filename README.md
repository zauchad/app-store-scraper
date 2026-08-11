# Market Research Intelligence Platform

Automatyczne wykrywanie **nisz w App Store**, w których istnieje popyt, a obecne
aplikacje zawodzą. System nie tylko zbiera dane — generuje **actionable insights**:
Executive Summary, główne problemy użytkowników, brakujące funkcje, sugerowany
kierunek rozwoju Twojej aplikacji oraz **ocenę wykonalności marketingowej** przy
Twoim budżecie.

## Dlaczego to działa (model dwupoziomowy)

```
POZIOM 1 (codziennie, tanio, bez LLM)
  Scraping rankingów + metadanych  ->  Opportunity Score dla WSZYSTKICH kategorii
  Sygnały: popyt, luka jakościowa, nasycenie, momentum
  + warstwa marketingu: ile instalacji kupisz za budżet, szansa sukcesu

POZIOM 2 (tylko TOP-K nisz, LLM)
  Recenzje (zwł. 1-3 gwiazdki)  ->  Gemini  ->  Executive Summary,
  pain points, brakujące funkcje, sugerowany kierunek dla Twojej apki
```

### Analizy bez LLM na pełnym korpusie recenzji

Niezależnie od LLM, system mieli **wszystkie** zebrane recenzje (100k+) w
deterministyczny pain-mining: leksykon tematów bólu (crashe, reklamy,
subskrypcje, synchronizacja, logowanie…), najczęstsze frazy (bigramy) z
negatywnych recenzji oraz ranking apek o najwyższym odsetku złych ocen.
To systematyczna wersja zasady „przeczytaj min. 100 recenzji konkurenta" —
wyniki trafiają też do promptu LLM jako twarde statystyki całego korpusu.

### Sygnały monetyzacji i płynności rynku

* **Monetyzacja (free→grossing)** — skanujemy `topfree` **i** `topgrossing`;
  odsetek top-free apek obecnych też w top-grossing = jedyny darmowy dowód,
  że użytkownicy w tej niszy realnie płacą. Zasila pytanie 3 checklisty.
* **Świeżość rynku** — odsetek top-apek wydanych <2 lata temu; nisko =
  rynek zabetonowany. Sekcja **Młodzi zwycięzcy** pokazuje konkretne nowe
  apki, które już się przebiły (dowód wykonalności + wzorce wejścia).
* **Instalacje/mies. per apka** — tempo przyrostu ocen między skanami →
  popyt DZIŚ, nie suma historyczna.

### Keyword discovery i geo-arbitraż (Mikro-nisze)

* **Crawl autocomplete Apple** (fraza + a–z) → long-tail frazy, które ludzie
  faktycznie wpisują — weryfikowalny popyt zamiast zgadywania.
* **Geo-radar** — ta sama fraza porównana w US/GB/DE/FR/PL: gdzie konkurencja
  najsłabsza, tam zlokalizowana wersja apki wchodzi najtaniej.

### Zewnętrzne sygnały popytu (opcjonalne, darmowe)

* **Apple Ads search popularity (5–100)** — oficjalny wolumen wyszukiwań;
  wymaga tylko **darmowego** konta Apple Ads (bez wydawania na reklamy).
  Ustaw `VOLUME_PROVIDER=asa` + klucze `ASA_*` w `.env` (instrukcja w
  `.env.example`). Od 10.2025 Apple zwraca score tylko dla fraz ≥35 —
  poniżej automatyczny fallback do darmowego proxy autocomplete.
* **Reddit demand mining** — posty „is there an app for…" to popyt widoczny
  ZANIM pojawi się w App Store. Darmowa aplikacja *script* na
  reddit.com/prefs/apps → `REDDIT_CLIENT_ID/SECRET`. Przycisk w Mikro-niszach.
* **Sensor Tower / data.ai — celowo pominięte**: $2–10k+/rok, a do *rankingu*
  nisz (nie wyceny firm) darmowe heurystyki wystarczają. Najtańsza realna
  walidacja to i tak mała kampania Apple Search Ads (200–500 zł) na frazę
  z Mikro-nisz — daje PRAWDZIWE CPI i konwersję.

### Eksport i raporty

* Eksport CSV tabel (Radar, Mikro-nisze) oraz **jednoklikowy raport niszy
  (.md)** łączący scoring, pain-mining, AI, kandydatów i checklist — gotowy
  artefakt do udostępnienia.

### Sygnały strukturalne niszy (darmowe, z iTunes Lookup)

* **Koncentracja wydawców** — czy niszę trzyma 10 firm, czy 1 firma z 10
  apkami (`artistId`); udział największego wydawcy w ocenach.
* **Luka lokalizacyjna** — odsetek dużych konkurentów wydających apkę tylko
  po angielsku (`languageCodesISO2A`) = otwarcie na rynki językowe.
* **Psujące się apki** — ocena bieżącej wersji vs lifetime
  (`averageUserRatingForCurrentVersion`): użytkownicy odwracają się TERAZ,
  bez czekania na historię skanów.
* **Release notes konkurencji** — co i jak szybko konkurenci wydają.
* **Checklist 5 pytań weryfikacji niszy** (dotkliwość problemu, przewaga,
  monetyzacja, wzrost, unikalna przewaga) — auto-wypełniany danymi
  w zakładce Analiza.

Nie musisz ręcznie wskazywać kategorii — lista kategorii App Store jest skończona,
więc system skanuje je **wszystkie automatycznie**. **Gry są domyślnie wykluczone**
(kapitałochłonna produkcja) — zmienisz to w `.env`.

### POZIOM 3 — Micro-Niche Explorer (poniżej top-chartów)

Top-charty każdej kategorii są z definicji własnością gigantów, więc na ich
poziomie „wszystko wygląda na nasycone". Prawdziwe okazje żyją niżej — na
poziomie słów kluczowych / długiego ogona. Pętla:

```
LLM proponuje konkretne mikro-nisze (np. "budgeting for couples")
   -> Search API zwraca apki realnie konkurujące o to zapytanie
   -> sygnał search-interest (autocomplete App Store) + zaangażowanie apek = POPYT
   -> ten sam scoring (Opportunity = atrakcyjność x contestability)
   -> ranking mikro-nisz z guardrailem gigantów
```

Przykład z żywych danych: kategoria *Finance* = 3/100 (rynek gigantów), ale
mikro-nisza *"budgeting for couples"* = **55/100** (zero gigantów, konkurencja
fatalnie oceniana). Tego nie widać na poziomie kategorii.

**Sygnał search-interest (popyt wyszukiwań).** Prawdziwy wolumen wyszukiwań to
domena płatnych API (Apple Search Ads popularity 5–100, AppTweak, Sensor Tower).
Domyślnie używamy **darmowego proxy**: autocomplete App Store (`MZSearchHints`),
które Apple sortuje ~wg popularności. Odpowiada na pytanie „czy ludzie w ogóle to
wyszukują?" (0..1). Dzięki temu odróżniamy nisze z realnym popytem (*"speech
therapy practice"*, *"adhd focus timer"* → ~1.0) od czystych luk jakości bez
ruchu (*"post surgery recovery"* → 0.05: świetna luka, ale cienki popyt).
Provider jest wymienny (`VOLUME_PROVIDER`) — podmienisz proxy na płatne ASO API
bez dotykania scoringu. Waga miksu popytu: `DEMAND_SEARCH_WEIGHT` (domyślnie 0.5).

```bash
# Waliduj własne pomysły na nisze:
python run.py keywords --genre 6015 --terms "budgeting for couples, invoice for freelancers"
# Albo pozwól LLM zaproponować kandydatów dla motywu:
python run.py keywords --generate --theme "personal finance for gig workers" --genre 6015 --n 15
```

**Automatyczne drążenie (Poziom 3 bez klikania).** `python run.py discover` bierze
najlepsze *kontestowalne* kategorie z Poziomu 1 (pomija rynki gigantów), LLM sam
generuje dla nich mikro-nisze, skanuje je i zapisuje (`source="auto"`). Odpala się
w codziennym cronie po `scan` + `deep-dive`, więc dashboard zawsze pokazuje świeże,
wygrywalne nisze bez ręcznej pracy.

```bash
python run.py discover                      # top kategorie -> auto mikro-nisze
python run.py discover --top-k 5 --per-category 12
```

W dashboardzie: zakładka **Micro-Niche Explorer** (generuj AI / wpisz ręcznie ->
ranking + szczegóły konkurentów + search-interest).

### Sygnały „jak w płatnych narzędziach" (za darmo)

Trzy dodatki zbliżające analizę do AppTweak / data.ai / Sensor Tower — wszystkie
z danych, które już przepływają przez system (zero płatnych zapytań):

- **Update cadence / porzucone forty** — z `currentVersionReleaseDate` (Lookup)
  liczymy, ile silnych apek nie było aktualizowanych >12 mies. Zaniedbany, duży
  incumbent = świeża okazja mimo starych recenzji. Widoczne w *Niche Deep Dive*.
- **Rank velocity / Breakout** — porównujemy pozycję w rankingu między skanami i
  pokazujemy apki najszybciej pnące się w górę (odpowiednik listy *Rising* z
  data.ai). Wpięte też w *momentum* score. Sekcja **Breakout** w *Opportunity
  Radar* (wymaga ≥2 dni historii).
- **Keyword difficulty (ASO)** — dla mikro-niszy liczymy trudność wyprzedzenia
  apek już rankujących (autorytet = wolumen ocen + twierdze). W parze z
  search-interest daje kwadrant AppTweak: **wysoki popyt + niska trudność = sweet
  spot**. Kolumny *Popyt wysz.* i *Trudność* w *Micro-Niche Explorer*.
- **Heurystyczne pasma instalacji/przychodów** — z liczby ocen szacujemy *rząd
  wielkości* instalacji (lifetime: `oceny / 1–3%`), pokazywany jako szerokie
  pasmo z etykietą `≈ … (heur.)`. To NIE są zmierzone pobrania (te wymagają
  paneli), ale do rankingu/filtrowania („hobby na 5k vs biznes na 500k")
  oddają ~80% wartości Sensor Tower. Przychód liczymy tylko dla apek płatnych
  (cena × instalacje); dla freemium/IAP uczciwie zostawiamy puste.
- **Trend jakości + spadki ocen** — z historii `avg_rating_top` rysujemy, czy
  jakość konkurencji rośnie czy spada (spadek = świeża luka). Sekcja
  *Spadki jakości* w *Opportunity Radar* wskazuje apki z osuwającą się oceną
  (użytkownicy niezadowoleni = okno na lepszy produkt). Wymaga ≥2 skanów.

### Warstwa trendów (zwrot z miesięcy zbierania danych)

Trzy rzeczy, które nabierają wartości dopiero z historią — dlatego warto zbierać
codziennie od teraz:

- **Wzrost N-tygodniowy** — zamiast szumu dzień-do-dnia liczymy medianę wzrostu
  zaangażowania (liczby ocen) w oknie N tygodni. Kolumna *Wzrost 4-tyg.* w
  *Opportunity Radar* (pokazuje `n/d` do czasu uzbierania historii). Kod:
  `src/analysis/trends.py`.
- **Retencja / downsampling** — `python run.py retention` (**domyślnie WYŁĄCZONA**,
  `RETENTION_ENABLED=false` → trzymamy wszystkie surowe snapshoty bezterminowo;
  uruchom ręcznie flagą `--force` albo włącz `RETENTION_ENABLED=true`). Gdy
  włączona: pełne dzienne snapshoty przez 60 dni (`RETENTION_DAILY_DAYS`), starsze
  redukowane do jednego na apkę na tydzień → baza pozostaje płaska.
  **Ważne — co retencja KASUJE, a co ZOSTAJE NA ZAWSZE:** rusza wyłącznie
  `app_snapshots` (surowa seria czasowa) i nawet tam nie usuwa całości —
  punkty tygodniowe zostają bezterminowo (trendy się nie urywają). **Nigdy** nie
  tyka "wniosków": `category_insights` (podsumowania LLM), `category_scores`
  (dzienna historia Opportunity), `keywords`/`keyword_scores` (mikro-nisze),
  `reviews` ani `apps` — te trzymamy w całości, na zawsze.
- **Cotygodniowy digest** — `python run.py digest` (i zakładka **Co się zmieniło**
  w dashboardzie) składa jeden brief: rosnące nisze, najlepsze osiągalne okazje,
  nowe mikro-nisze, breakouty, spadki jakości i porzucone forty. Zapisywany też
  do `data/digest_YYYYMMDD.md`.

### Limity darmowego LLM (Gemini)

Domyślny model to `gemini-flash-latest` (alias zawsze wskazujący aktualny model
Flash). **Uwaga:** stary `gemini-2.5-flash` zwraca dla nowych projektów API błąd
`404 „no longer available to new users"` — dlatego używamy aliasu. Darmowy tier
Flasha ma dzienny limit, więc pełny `all` uruchomiony **dwa razy tego samego dnia
może trafić na 429**. Zabezpieczenia w kodzie: throttling (`LLM_MIN_INTERVAL_
SECONDS`), retry na przejściowe 429 (`LLM_MAX_RETRIES`), *circuit breaker* po
wyczerpaniu limitu oraz wyłączone „myślenie" (thinking_budget=0) dla stabilnego
JSON.

**Pula kluczy (zwielokrotnienie limitu).** Ustaw `GEMINI_API_KEYS` na kilka kluczy
po przecinku — gdy jeden wyczerpie dzienny limit (429 PerDay), aplikacja
automatycznie rotuje na następny. Klucze z **różnych projektów Google Cloud** mają
niezależne pule (np. 3 klucze ≈ 60 zapytań/dzień). Circuit breaker aktywuje się
dopiero, gdy padną wszystkie. (Uwaga: mnożenie projektów wyłącznie dla obejścia
limitów bywa w szarej strefie ToS Google — na własną odpowiedzialność.)

Inne opcje: uruchamiaj `deep-dive`/`discover` **max raz dziennie**, ustaw
wyżej-limitowy/szybszy model (`GEMINI_MODEL`, np. `gemini-flash-lite-latest`),
albo włącz płatny plan.

## Architektura

```mermaid
flowchart LR
  A["Apple iTunes (RSS charts + Lookup + reviews)"] --> B[Scraper / Ingest]
  B --> C[(PostgreSQL / SQLite)]
  C --> D["Level 1: Metrics + Opportunity Score + Marketing"]
  C --> E["Level 2: LLM synthesis (Gemini)"]
  D --> F[Streamlit Dashboard]
  E --> F
  G["GitHub Actions (daily cron)"] --> B
```

## Stos technologiczny

| Warstwa       | Technologia                        | Hosting (darmowy MVP)          |
|---------------|------------------------------------|--------------------------------|
| Scraping      | `requests` + iTunes RSS/Lookup     | GitHub Actions (cron)          |
| Baza danych   | SQLAlchemy (SQLite / Postgres)     | Supabase (free Postgres)       |
| Analiza LLM   | Google Gemini (`google-genai`)     | Google AI Studio (free tier)   |
| Dashboard     | Streamlit + Plotly                 | Streamlit Community Cloud      |

Kod jest DB-agnostyczny: **lokalnie działa na SQLite bez żadnej instalacji**,
a na produkcji wystarczy podać `DATABASE_URL` do Supabase.

## Szybki start (lokalnie, ~5 min)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # opcjonalnie wpisz GEMINI_API_KEYS
python run.py scan            # Poziom 1: scrape + Opportunity Score (SQLite)
python run.py deep-dive       # Poziom 2: analiza LLM (wymaga GEMINI_API_KEYS)
streamlit run dashboard/app.py
```

Bez klucza LLM Poziom 1 (heatmapa okazji + marketing) działa w pełni; Deep Dive
pokaże instrukcję, jak go włączyć.

### Dashboard (dla laika)

Nawigacja to górny pasek „pigułek" (jak zwykły website), a nie sidebar-radio:

- **📡 Radar okazji** — ranking nisz, mapa popyt×jakość, rekomendacja na start,
  breakouty i spadki jakości.
- **🔬 Głęboka analiza** — dla wybranej niszy: problemy użytkowników, brakujące
  funkcje, trend jakości oraz **do 5 kandydatów „sklonuj i ulepsz"** (apki z
  udowodnionym popytem, ale wykorzystywalną słabością — z linkiem do App Store i
  konkretnym pomysłem „jak wygrać").
- **🎯 Mikro-nisze** — **klikasz wiersz** w rankingu, żeby zobaczyć szczegóły
  frazy + kandydatów do ulepszenia.
- **📈 Co się zmieniło** — cotygodniowy digest.

Dodatkowo: każda sekcja ma przycisk **„ℹ️ Na jakich danych?"** otwierający modal
ze źródłem i wzorem każdego wskaźnika (pełna transparentność), wszystkie apki są
podlinkowane do App Store, a w sidebarze jest **słowniczek pojęć**.

## CLI

```bash
python run.py init                  # utwórz schemat bazy
python run.py scan                  # Poziom 1 (codzienny)
python run.py scan --no-reviews     # szybciej, bez pobierania recenzji
python run.py deep-dive             # LLM dla TOP-K nisz
python run.py deep-dive --genre 6013
python run.py discover              # Poziom 3: auto-drążenie top kategorii w mikro-nisze
python run.py keywords --terms "..."  # ręczna walidacja mikro-nisz
python run.py retention            # downsampling starych snapshotów (płaska baza)
python run.py digest               # cotygodniowy brief "co się zmieniło"
python run.py all                   # scan + deep-dive + discover + retention (pełny job)
```

## Wdrożenie produkcyjne (darmowe) — krok po kroku

Architektura hostingu: **Supabase** (baza) + **GitHub Actions** (codzienny scan)
+ **Streamlit Cloud** (dashboard). Wszystko na darmowych tierach.

### 1. Baza danych — Supabase

1. Załóż projekt na [supabase.com](https://supabase.com) (free tier).
2. *Project Settings -> Database -> Connection string*. Wybierz **Connection
   pooler** (nie „Direct") — pooler ma adres **IPv4**, którego wymagają runnery
   GitHub Actions (direct `db.xxx.supabase.co` jest dziś IPv6-only).
3. Zbuduj `DATABASE_URL` w formacie SQLAlchemy (dopisz `+psycopg2` i `sslmode`):
   ```
   postgresql+psycopg2://postgres.PROJECTREF:HASLO@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
   ```
   (port `5432` = session pooler; działa najprościej z SQLAlchemy.)
4. Schemat utworzy się sam przy pierwszym `run.py scan` (`init_db()`), nie musisz
   ręcznie odpalać SQL.

### 2. LLM — Google AI Studio

Wygeneruj darmowy klucz (lub kilka) na [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
-> `GEMINI_API_KEYS` (po przecinku, jeśli pula).

### 3. Codzienny scan — GitHub Actions

1. Wypchnij repo na GitHub.
2. *Settings -> Secrets and variables -> Actions -> New repository secret*:
   - `DATABASE_URL` (string z kroku 1)
   - `GEMINI_API_KEYS` (jeden klucz albo kilka po przecinku)
   - (opcjonalnie) `RAPIDAPI_KEY` — jeśli chcesz MODE A.
3. (opcjonalnie) *Variables*: `STORE_COUNTRY`, `TOP_N_APPS`, `MARKETING_BUDGET_PLN`,
   `DEEP_DIVE_TOP_K`.
4. Workflow [.github/workflows/daily-scan.yml](.github/workflows/daily-scan.yml)
   uruchomi się codziennie (05:10 UTC) — albo ręcznie przez *Run workflow*.

### 4. Dashboard — Streamlit Community Cloud

1. Na [share.streamlit.io](https://share.streamlit.io) *New app* -> wskaż repo
   i plik `dashboard/app.py`. W *Advanced settings* wybierz **Python 3.11**.
2. W *Settings -> Secrets* wklej zawartość według
   [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example)
   (minimum `DATABASE_URL` + `GEMINI_API_KEYS`). Dashboard mostkuje sekrety do
   zmiennych środowiskowych automatycznie — zero zmian w kodzie.
3. Deploy. Dashboard czyta tę samą bazę Supabase, którą zasila cron.

### 5. Digest na Slacka / e-mail (żeby system raportował do Ciebie)

Cron po każdym skanie wysyła digest (`python run.py digest --send`) na
skonfigurowane kanały — wystarczy dodać sekrety w GitHub Actions:

* **Slack** (2 min): utwórz [Incoming Webhook](https://api.slack.com/messaging/webhooks)
  -> sekret `SLACK_WEBHOOK_URL`.
* **E-mail** (Gmail): włącz 2FA -> *App Passwords* -> sekrety `SMTP_HOST`
  (`smtp.gmail.com`), `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`
  (wielu odbiorców po przecinku).

Brak konfiguracji = krok jest pomijany bez błędu. Lokalnie przetestujesz przez
`python run.py digest --send`.

Kolejność uruchomienia: najpierw odpal raz workflow (żeby były dane), potem
otwórz dashboard.

## Jak czytać wyniki (perspektywa analityka)

- **Opportunity Score (0-100)** — łączy popyt, lukę jakościową, niskie nasycenie
  i momentum. Wysoki = strukturalnie atrakcyjna nisza.
- **Momentum** — najważniejszy filtr szumu. Na dzień 1 jest neutralny; wyostrza
  się z każdym kolejnym skanem. Nisza z rosnącym momentum > statyczna nisza.
- **Twierdze (strong incumbents)** — apki z oceną ≥4.5 i ≥5000 recenzji. Dużo
  twierdz = trudno wygryźć konkurencję nawet przy dobrym produkcie.
- **Szansa sukcesu** — łączy atrakcyjność niszy, potencjał organiczny (luka
  jakościowa) i realny zasięg płatny vs skala konkurencji przy Twoim budżecie.
- **CPI / instalacje** — benchmarki edytowalne w
  [src/scraper/categories.py](src/scraper/categories.py). To filtr „czy w ogóle
  Cię na to stać", nie prognoza.

## WAŻNE: dostęp do tekstu recenzji (stan 2026)

Zweryfikowane na żywo podczas budowy: **darmowy, anonimowy dostęp do TEKSTU
recenzji jest w 2026 martwy** — klasyczny RSS Apple (`.../rss/customerreviews/...`)
zwraca pusty feed dla wszystkich testowanych apek, a wewnętrzne AMP API wymaga
tokena, który Apple utwardziło. Dotyczy to też popularnych bibliotek (używają
tego samego martwego RSS).

Dlatego Poziom 2 (LLM) działa w **dwóch trybach**, wybieranych automatycznie:

- **MODE A — recenzje** (preferowany): pełne pain-pointy z recenzji 1-3 gwiazdki.
  Wymaga tekstu recenzji → podepnij tani provider (patrz niżej).
- **MODE B — pozycjonowanie konkurencji** (darmowy fallback, działa DZIŚ): LLM
  analizuje **opisy konkurentów** (darmowe z iTunes Lookup) + sygnały ilościowe
  i wnioskuje luki w pozycjonowaniu oraz słabe punkty liderów.

### Jak odblokować MODE A (pełne recenzje)

Warstwa providerów recenzji jest już wbudowana
([src/scraper/review_providers.py](src/scraper/review_providers.py)). Wystarczy
konfiguracja — zero zmian w kodzie pipeline'u/dashboardu.

**Opcja 1 — RapidAPI (rekomendowana, tania, headless):**

1. Wejdź na RapidAPI i zasubskrybuj dowolne API typu "App Store Reviews"
   (większość ma darmowy tier lub ~0-15 USD/mies.).
2. W `.env` (lub sekretach) ustaw:
   ```
   REVIEW_PROVIDER=rapidapi
   RAPIDAPI_KEY=twoj_klucz
   RAPIDAPI_HOST=host-z-rapidapi.p.rapidapi.com
   RAPIDAPI_REVIEWS_URL=https://host-z-rapidapi.p.rapidapi.com/reviews?app_id={app_id}&country={country}&page={page}
   ```
   Parser jest odporny — akceptuje typowe nazwy pól (`rating`/`score`,
   `review`/`body`/`content`/`text`, `author`/`userName`, ...), więc działa z
   wieloma różnymi API bez zmian w kodzie.
3. `python run.py scan` — recenzje wpadają do bazy, a `deep-dive` automatycznie
   przełącza się na MODE A.

**Opcja 2 — własny provider:** dodaj podklasę `ReviewProvider` i zwróć ją w
`get_review_provider()`. Reszta systemu pozostaje bez zmian.

## Ograniczenia (świadome, MVP)

- **Recenzje**: patrz sekcja wyżej — Poziom 2 działa na fallbacku bez dopłat.
- **CPI/prawdopodobieństwo**: heurystyki do rankowania, nie prognozy księgowe.
- **Momentum**: wymaga historii — wartość rośnie po kilku dniach skanów.

## Roadmap (faza 2+)

- FastAPI + React (gdy pojawi się potrzeba API/klientów zewnętrznych).
- Scraper recenzji z renderowanej strony (Playwright) jako fallback.
- Google Play jako drugie źródło (cross-platform walidacja niszy).
- Alerty (Slack/e-mail) gdy nowa nisza przekroczy próg Opportunity Score.
```
